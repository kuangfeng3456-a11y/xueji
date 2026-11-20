"""华为云能力接入状态与手动调用接口（文档 D3 / D4）。

设计约束：
1. ``GET /cloud/services`` 只读配置与本地 SDK 探测，**不发起任何云端调用**，
   无凭据也能正常返回，与 integrations.py 的「状态上报」定位一致。
2. 各能力的显式调用端点（OCR/SIS）要求登录，参数原样透传给
   services.cloud_services，由服务层返回 ok / not_configured / sdk_missing / error
   四态；接口层绝不伪造成功结果。
3. OBS 与凭据托管**不开放任意调用**：上传/删除/生命周期由服务端内部按
   同意（consent）流程触发；KMS 明文永远不进接口层，故此处不提供其端点。
"""

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile

from ..deps import get_current_user
from ..models import User
from ..services import cloud_services as cs
from ..services.question_ocr import extract_question_image

router = APIRouter(prefix="/cloud", tags=["华为云能力"])

# 单次上传走云 OCR 的硬上限（与服务层 _read_image_bytes 一致）
_MAX_IMAGE_BYTES = 10 * 1024 * 1024


@router.get("/services")
def services(user: User = Depends(get_current_user)) -> dict:
    """四类云能力（OCR/SIS/OBS/DEW）的配置与 SDK 就绪状态，不产生云端调用。"""
    return cs.describe_cloud_services()


@router.post("/ocr/extract")
async def ocr_extract(
    file: UploadFile = File(...),
    kind: str = Form("general"),
    user: User = Depends(get_current_user),
) -> dict:
    """错题拍照文字识别（显式调用，需已配置 AK/SK 与 OCR SDK）。

    未配置或未装 SDK 时返回对应降级状态，前端应回退到手动录入。
    """
    raw = await file.read()
    if len(raw) > _MAX_IMAGE_BYTES:
        return {
            "status": "error",
            "detail": f"图片超过 {_MAX_IMAGE_BYTES // 1024 // 1024}MB 上限，未调用云服务",
            "text": "",
        }
    result = extract_question_image(raw, kind=kind)
    result["filename"] = (file.filename or "")[:80]
    return result


@router.post("/sis/synthesize")
def sis_synthesize(
    text: str = Form(...),
    voice_name: str = Form(""),
    audio_format: str = Form("mp3"),
    user: User = Depends(get_current_user),
) -> dict:
    """语音合成（语音教练用）。返回音频字节走 base64 的体积过大，
    此端点仅返回状态与音频时长等元数据；成功时前端优先使用浏览器
    Web Speech，云端合成留作高质量音色场景。"""
    clean = (text or "").strip()
    if not clean:
        return {"status": "error", "detail": "文本为空", "audio_ready": False}
    if len(clean) > 500:
        clean = clean[:500]
    result = cs.sis_text_to_audio(clean, voice_name=voice_name, audio_format=audio_format)
    # 不把音频字节透传给接口层之外的存储；只报告是否就绪
    result["audio_ready"] = result.get("status") == cs.OK
    result.pop("audio_base64", None)
    result["chars"] = len(clean)
    if result.get("status") == cs.OK and result.get("audio_b64"):
        result["fallback"] = ""
        result["fallback_label"] = "云端语音合成"
    else:
        result["fallback"] = "device_speech"
        result["fallback_label"] = "云端语音合成不可用，请改用本机朗读"
        result.pop("audio_b64", None)
    return result


@router.post("/sis/recognize")
async def sis_recognize(
    file: UploadFile = File(...),
    audio_format: str = Form("wav"),
    sample_rate: int = Form(16000),
    user: User = Depends(get_current_user),
) -> dict:
    """一句话识别。未配置或调用失败时 text 为空，并标明应改用本机语音或文字。"""
    raw = await file.read()
    if len(raw) > 8 * 1024 * 1024:
        return {
            "status": "error",
            "detail": "音频超过 8MB 上限，未调用云服务",
            "text": "",
            "fallback": "device_or_text",
            "fallback_label": "请缩短录音，或改用文字输入",
        }
    result = cs.sis_audio_to_text(raw, audio_format=audio_format or "wav", sample_rate=sample_rate or 16000)
    result["text"] = result.get("text") or ""
    if result.get("status") == cs.OK and result["text"]:
        result["fallback"] = ""
        result["fallback_label"] = "云端语音识别"
    else:
        result["fallback"] = "device_or_text"
        result["fallback_label"] = "云端语音识别不可用，请改用本机语音或文字输入"
    return result
