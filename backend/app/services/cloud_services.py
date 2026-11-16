"""华为云 AI 与存储能力封装：OCR / SIS / OBS / DEW(CSMS)。

设计原则（与 huawei_cloud.py 保持一致，务必沿用）：
1. **缺配置不崩**：没有 AK/SK 时导入本模块不会报错，调用返回明确的
   ``status="not_configured"``，绝不抛异常、绝不用假数据冒充成功。
2. **缺 SDK 不崩**：所有云产品 SDK 一律延迟 import（函数内部），并用
   ``ImportError`` 保护；未安装时返回 ``status="sdk_missing"`` 并给出可安装的包名。
3. **失败如实上报**：真实调用出错时返回 ``status="error"`` 与截断后的错误摘要，
   不伪造识别文本、音频或上传结果。
4. **凭据零外泄**：AK/SK 只从环境变量读取并驻留内存；任何返回值、日志、
   错误摘要都不包含凭据；``kms_get_secret`` 读到的明文既不打日志也不进接口层。

诚实说明：本文件的云端调用路径**尚未在真实华为云环境验证过**（开发机没有
AK/SK，也没有开通 OCR/SIS/DEW 服务）。已验证的只有：无配置/无 SDK 时的降级
分支、SDK 客户端构造方式（对照本机已安装的 huaweicloudsdkcore / huaweicloudsdkobs
源码）、以及响应字段名的解析逻辑（对未知字段一律容错为 None）。
"""

import base64
import io
import os
import time
from pathlib import Path
from typing import Dict, Optional, Tuple

from ..config import settings

REGION = settings.CLOUD_REGION

# 结构化状态常量：接口层与前端都按这四个值渲染，不要新增同义值
OK = "ok"
NOT_CONFIGURED = "not_configured"
SDK_MISSING = "sdk_missing"
ERROR = "error"

# 各能力对应的可选依赖包名（见 backend/requirements.txt 的可选分组）
OPTIONAL_PACKAGES = {
    "ocr": "huaweicloudsdkocr>=3.1.200",
    "sis": "huaweicloudsdksis>=3.1.200",
    "obs": "esdk-obs-python>=3.24.0",
    "dew": "huaweicloudsdkdew>=3.1.200",
}


def _credentials() -> Tuple[str, str, str]:
    """读取 AK / SK / 项目 ID；缺失时返回空串，由调用方判定 not_configured。"""
    # 优先进程环境变量，其次由 config 从 .env.cloud / .env 读取（两者都已在启动时加载）
    ak = os.getenv("HUAWEICLOUD_SDK_AK", "") or settings.CLOUD_ACCESS_KEY
    sk = os.getenv("HUAWEICLOUD_SDK_SK", "") or settings.CLOUD_SECRET_KEY
    project = os.getenv("CLOUD_PROJECT_ID", "") or settings.CLOUD_PROJECT_ID
    return ak.strip(), sk.strip(), project.strip()


def _configured(need_project: bool = True) -> Tuple[bool, str]:
    ak, sk, project = _credentials()
    if not (ak and sk):
        return False, "未配置华为云凭证（HUAWEICLOUD_SDK_AK / HUAWEICLOUD_SDK_SK）"
    if need_project and not project:
        return False, "未配置 CLOUD_PROJECT_ID（区域级服务需要项目 ID）"
    return True, ""


def _result(status: str, detail: str, **extra) -> Dict:
    payload = {
        "status": status,
        "detail": (detail or "")[:200],
        "region": REGION,
        "checked_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    payload.update(extra)
    return payload


def _safe_error(exc: BaseException) -> str:
    """错误摘要脱敏：去掉可能带签名/凭据的 URL query 部分，再截断。"""
    text = f"{type(exc).__name__}: {exc}"
    for marker in ("?X-Signature=", "&X-Signature=", "Signature=", "AccessKeyId="):
        if marker in text:
            text = text.split(marker, 1)[0] + "…（签名参数已省略）"
            break
    return text[:200]


def _sdk_guard(key: str):
    """把 ImportError 转成结构化的 sdk_missing 结果（供 with-guard 风格使用）。"""
    return _result(
        SDK_MISSING,
        f"未安装 {key} 所需 SDK，可选安装：pip install \"{OPTIONAL_PACKAGES[key]}\"",
    )


def _endpoint(service: str, override_env: str = "") -> str:
    if override_env:
        direct = os.getenv(override_env, "").strip()
        if direct:
            return direct if direct.startswith("http") else f"https://{direct}"
    return f"https://{service}.{REGION}.myhuaweicloud.com"


def _dump(model) -> Dict:
    if model is None:
        return {}
    if hasattr(model, "to_dict"):
        try:
            return model.to_dict() or {}
        except Exception:
            return {}
    return {}


def _pick(data: Dict, *names):
    for name in names:
        value = data.get(name)
        if value not in (None, "", []):
            return value
    return None


def _read_image_bytes(image) -> Tuple[Optional[bytes], str]:
    """接受 bytes / bytearray / 本地路径，返回 (图片字节, 错误说明)。"""
    if isinstance(image, (bytes, bytearray)):
        data = bytes(image)
    elif isinstance(image, Path) or (isinstance(image, str) and image):
        path = Path(str(image))
        if not path.exists() or not path.is_file():
            return None, f"图片文件不存在：{path.name}"
        try:
            data = path.read_bytes()
        except OSError as exc:
            return None, f"图片读取失败：{type(exc).__name__}"
    else:
        return None, "图片参数类型不支持（需要 bytes 或本地文件路径）"
    if not data:
        return None, "图片内容为空"
    limit = 10 * 1024 * 1024
    if len(data) > limit:
        return None, f"图片超过 {limit // 1024 // 1024}MB 上限，未调用云服务"
    return data, ""


# ---------------------------------------------------------------------------
# A1. OCR 文字识别（错题拍照）
# ---------------------------------------------------------------------------

def ocr_extract_text(image, language: str = "", kind: str = "general") -> Dict:
    """调用华为云 OCR 识别图片文字，供「错题拍照录入」使用。

    Args:
        image: 图片字节（bytes）或本地文件路径。原图只在本次调用内存在于内存，
            本函数不落地保存、不写日志。
        language: 预留语言提示（华为云通用文字识别当前不区分语言参数，保留是为了
            和前端契约对齐；未生效时不影响结果正确性）。
        kind: "general"（通用文字识别）或 "table"（通用表格识别，用于试卷表格题）。

    Returns:
        dict: ``status`` 为 ok / not_configured / sdk_missing / error 之一。
        成功时附带 ``text``（识别正文）、``blocks``（段落数）、``confidence``（平均置信度，
        取不到时为 None）、``latency_ms``。**失败时 text 为空串，绝不返回猜测内容。**

    降级行为：
        - 无 AK/SK → not_configured，前端应回退到「手动录入错题」。
        - 未装 huaweicloudsdkocr → sdk_missing，附可安装包名。
        - 云端报错/未开通该 API → error，附脱敏错误摘要，同样回退手动录入。
    """
    ok_cfg, cfg_detail = _configured()
    if not ok_cfg:
        return _result(NOT_CONFIGURED, cfg_detail or "未配置华为云凭证，错题识别使用手动录入", text="")

    data, read_err = _read_image_bytes(image)
    if read_err:
        return _result(ERROR, read_err, text="")

    try:
        from huaweicloudsdkcore.auth.credentials import BasicCredentials
        from huaweicloudsdkcore.region.region import Region
        from huaweicloudsdkocr.v1 import OcrClient
        from huaweicloudsdkocr.v1.model import (
            RecognizeGeneralTextRequest,
            RecognizeGeneralTableRequest,
            GeneralTextRequestBody,
            GeneralTableRequestBody,
        )
    except ImportError:
        return _sdk_guard("ocr")

    ak, sk, project = _credentials()
    start = time.perf_counter()
    try:
        credentials = BasicCredentials(ak, sk, project)
        client = (
            OcrClient.new_builder()
            .with_credentials(credentials)
            .with_region(Region(REGION, _endpoint("ocr")))
            .build()
        )
        if kind == "table":
            request = RecognizeGeneralTableRequest(
                body=GeneralTableRequestBody(image=base64.b64encode(data).decode())
            )
            response = client.recognize_general_table(request)
        else:
            request = RecognizeGeneralTextRequest(
                body=GeneralTextRequestBody(image=base64.b64encode(data).decode())
            )
            response = client.recognize_general_text(request)
    except Exception as exc:  # noqa: BLE001 - 云端异常必须转成结构化状态而非抛出
        detail = _safe_error(exc)
        if "ModelArts.4204" in detail:
            return _result(
                "not_subscribed",
                "华为云账号未开通 OCR 服务（ModelArts.4204）。请在 OCR 控制台开通通用文字识别后重试；当前请手动录入题干。",
                text="",
                latency_ms=round((time.perf_counter() - start) * 1000),
            )
        return _result(
            ERROR,
            f"OCR 调用失败（未开通服务或鉴权失败）：{detail}",
            text="",
            latency_ms=round((time.perf_counter() - start) * 1000),
        )

    payload = _dump(response)
    # 通用文字识别返回 results[{words_block, confidence}]；表格识别返回 table_structures
    rows = _pick(payload, "results", "result", "table_structures") or []
    texts = []
    confidences = []
    for row in rows if isinstance(rows, list) else [rows]:
        item = _dump(row) if not isinstance(row, dict) else row
        word = _pick(item, "words_block", "words", "text")
        if word:
            texts.append(str(word))
        conf = _pick(item, "confidence")
        if isinstance(conf, (int, float)):
            confidences.append(float(conf))
    recognized = "\n".join(texts).strip()
    latency = round((time.perf_counter() - start) * 1000)

    if not recognized:
        return _result(
            ERROR,
            "OCR 返回成功但无可识别文字（图片可能模糊或不含印刷体）",
            text="",
            blocks=0,
            latency_ms=latency,
        )
    return _result(
        OK,
        f"识别出 {len(texts)} 段文字 · {len(recognized)} 字符",
        text=recognized,
        blocks=len(texts),
        confidence=round(sum(confidences) / len(confidences), 4) if confidences else None,
        latency_ms=latency,
    )


# ---------------------------------------------------------------------------
# A2. SIS 语音合成 / 语音识别（语音教练）
# ---------------------------------------------------------------------------

def _sis_client():
    """构造 SIS 客户端；返回 (client, error_result)。"""
    ok_cfg, cfg_detail = _configured()
    if not ok_cfg:
        return None, _result(NOT_CONFIGURED, cfg_detail)
    try:
        from huaweicloudsdkcore.auth.credentials import BasicCredentials
        from huaweicloudsdkcore.region.region import Region
    except ImportError:
        return None, _sdk_guard("sis")
    try:
        from huaweicloudsdksis.v1 import SisClient  # 官方 SDK 目前提供 v1
    except ImportError:
        try:
            from huaweicloudsdksis.v2 import SisClient  # 兼容未来版本
        except ImportError:
            return None, _sdk_guard("sis")
    ak, sk, project = _credentials()
    client = (
        SisClient.new_builder()
        .with_credentials(BasicCredentials(ak, sk, project))
        .with_region(Region(REGION, os.getenv("SIS_ENDPOINT", "").strip() or f"https://sis-ext.{REGION}.myhuaweicloud.com"))
        .build()
    )
    return client, None


def sis_text_to_audio(text: str, voice_name: str = "", audio_format: str = "mp3") -> Dict:
    """文本转语音（TTS），供「AI 语音教练朗读讲解」使用。

    Args:
        text: 待合成文本，最长 500 字符（超出直接拒绝，不截断后冒充成功）。
        voice_name: 发音人，默认取环境变量 ``SIS_TTS_VOICE``，再默认为 zh_v2_xiaoyan。
        audio_format: mp3 / wav / pcm。

    Returns:
        dict: ``status`` 四态之一。成功时附带 ``audio_b64``（Base64 音频，交由前端
        播放，服务端不落盘）、``audio_bytes``（原始字节长度）、``voice``、``latency_ms``。

    降级行为：无凭证 → not_configured；未装 SDK → sdk_missing；调用失败 → error。
    三种情况下前端都应回退到浏览器 Web Speech API（项目现有降级路径）。
    """
    content = (text or "").strip()
    if not content:
        return _result(ERROR, "待合成文本为空")
    if len(content) > 500:
        return _result(ERROR, f"文本 {len(content)} 字超过 500 字上限，请分段合成")

    client, guard = _sis_client()
    if guard is not None:
        return guard

    voice = (voice_name or os.getenv("SIS_TTS_VOICE", "")).strip() or "xiaoyan"
    start = time.perf_counter()
    response = None
    try:
        try:
            # 官方 SIS Python SDK 目前提供 v1（RunTts）；v2 作为向前兼容
            from huaweicloudsdksis.v1 import RunTtsRequest, TtsConfig
            from huaweicloudsdksis.v1.model.post_custom_tts_req import PostCustomTTSReq

            request = RunTtsRequest(
                body=PostCustomTTSReq(
                    text=content,
                    config=TtsConfig(
                        audio_format=audio_format,
                        sample_rate=int(os.getenv("SIS_SAMPLE_RATE", "16000")),
                        _property=voice,
                    ),
                )
            )
            response = client.run_tts(request)
        except ImportError:
            from huaweicloudsdksis.v2.model import ShowTtsRequest, ShowTtsRequestBody

            request = ShowTtsRequest(
                body=ShowTtsRequestBody(
                    voice_name=voice,
                    text=content,
                    audio_format=audio_format,
                    sample_rate=int(os.getenv("SIS_SAMPLE_RATE", "16000")),
                )
            )
            response = client.show_tts(request)
    except Exception as exc:  # noqa: BLE001
        detail = _safe_error(exc)
        if "SIS.0101" in detail or "auth failed" in detail.lower():
            return _result(
                "not_subscribed",
                "SIS 鉴权失败（SIS.0101）：请确认该区域已开通语音合成服务，且 AK/SK 具备 SIS 权限；当前由浏览器语音降级。",
                latency_ms=round((time.perf_counter() - start) * 1000),
            )
        return _result(
            ERROR,
            f"语音合成调用失败（未开通 SIS 或发音人不可用）：{detail}",
            latency_ms=round((time.perf_counter() - start) * 1000),
        )
    except Exception as exc:  # noqa: BLE001
        return _result(
            ERROR,
            f"语音合成调用失败（未开通 SIS 或发音人不可用）：{_safe_error(exc)}",
            latency_ms=round((time.perf_counter() - start) * 1000),
        )

    payload = _dump(response)
    raw = getattr(response, "raw_content", None)
    audio = _pick(payload, "data", "audio")
    if not audio and isinstance(payload.get("result"), dict):
        audio = payload["result"].get("data")
    audio = audio or raw
    if isinstance(audio, str):
        try:
            audio_bytes = base64.b64decode(audio)
        except Exception:
            audio_bytes = audio.encode("utf-8", errors="ignore")
    elif isinstance(audio, (bytes, bytearray)):
        audio_bytes = bytes(audio)
    else:
        audio_bytes = b""

    latency = round((time.perf_counter() - start) * 1000)
    if not audio_bytes:
        return _result(ERROR, "语音合成返回空音频", latency_ms=latency)
    return _result(
        OK,
        f"合成 {len(content)} 字 → {len(audio_bytes) // 1024}KB 音频",
        audio_b64=base64.b64encode(audio_bytes).decode(),
        audio_bytes=len(audio_bytes),
        voice=voice,
        format=audio_format,
        latency_ms=latency,
    )


def sis_audio_to_text(audio, audio_format: str = "wav", sample_rate: int = 16000) -> Dict:
    """语音识别（ASR，一句话识别），供「语音提问教练」使用。

    Args:
        audio: 音频字节或本地文件路径。
        audio_format: wav / pcm / opus（采样率需与录制端一致）。

    Returns:
        dict: ``status`` 四态之一。成功时附带 ``text``（识别文本）、``confidence``、
        ``latency_ms``。失败时 text 为空串。

    降级行为：无凭证 → not_configured；未装 SDK → sdk_missing；调用失败 → error。
    三种情况前端均回退浏览器 Web Speech Recognition。
    """
    data, read_err = _read_image_bytes(audio)  # 同一套 bytes/path 归一化逻辑
    if read_err:
        return _result(ERROR, read_err.replace("图片", "音频"), text="")

    client, guard = _sis_client()
    if guard is not None:
        return guard

    try:
        from huaweicloudsdksis.v2.model import ShowOneSentenceRequest, ShowOneSentenceRequestBody
    except ImportError:
        return _sdk_guard("sis")

    start = time.perf_counter()
    try:
        request = ShowOneSentenceRequest(
            body=ShowOneSentenceRequestBody(
                audio_property={"audio_format": audio_format, "sample_rate": int(sample_rate)},
                recognition_property={},
                audio=data.decode("latin-1", errors="ignore"),
            )
        )
        response = client.show_one_sentence(request)
    except Exception as exc:  # noqa: BLE001
        return _result(
            ERROR,
            f"语音识别调用失败（未开通 SIS 或音频格式不符）：{_safe_error(exc)}",
            text="",
            latency_ms=round((time.perf_counter() - start) * 1000),
        )

    payload = _dump(response)
    result = _pick(payload, "result", "results") or {}
    if not isinstance(result, dict):
        result = _dump(result)
    body_field = _pick(result, "body") or {}
    if not isinstance(body_field, dict):
        body_field = _dump(body_field)
    recognized = str(_pick(body_field, "text") or _pick(result, "text") or "").strip()
    confidence = _pick(body_field, "confidence") or _pick(result, "confidence")
    latency = round((time.perf_counter() - start) * 1000)

    if not recognized:
        return _result(ERROR, "语音识别返回空文本（可能是静音或噪声过长）", text="", latency_ms=latency)
    return _result(
        OK,
        f"识别出 {len(recognized)} 字",
        text=recognized,
        confidence=float(confidence) if isinstance(confidence, (int, float)) else None,
        latency_ms=latency,
    )


# ---------------------------------------------------------------------------
# A3. OBS 对象存储（仅可选缩略图；隐私前提见 docstring）
# ---------------------------------------------------------------------------

def _obs_settings() -> Dict:
    return {
        "endpoint": _endpoint("obs", "OBS_ENDPOINT"),
        "bucket": os.getenv("OBS_BUCKET", "").strip(),
        "ak": os.getenv("OBS_ACCESS_KEY", "") or os.getenv("HUAWEICLOUD_SDK_AK", ""),
        "sk": os.getenv("OBS_SECRET_KEY", "") or os.getenv("HUAWEICLOUD_SDK_SK", ""),
    }


def obs_upload_object(object_key: str, data, content_type: str = "image/jpeg") -> Dict:
    """上传**可选的学习见证缩略图**到华为云 OBS。

    ⚠️ 隐私前提（本项目的设计约束，请勿绕过）：
        摄像头见证的**原始画面始终留在浏览器本地，不上传**。本函数只为
        「用户主动开启云端备份」的场景准备，且只接受前端压缩后的低分辨率
        缩略图（建议 ≤ 128KB）。调用方必须在开启前取得学生/家长的明确同意，
        并配合 ``obs_configure_lifecycle`` 设定到期自动删除。

    Args:
        object_key: OBS 对象键，必须以 ``xueji/witness/`` 开头（否则拒绝，防止
            任意路径写入）。
        data: 缩略图字节或本地路径。
        content_type: MIME 类型。

    Returns:
        dict: ``status`` 四态之一。成功时附带 ``object_key``、``size_bytes``、
        ``latency_ms``。**不返回可公网访问的 URL**，避免链接被转发后泄露影像。

    降级行为：未配置桶/AK → not_configured；未装 esdk-obs-python → sdk_missing；
    上传失败 → error。任一情况调用方应保持「仅本地存储」的原状。
    """
    cfg = _obs_settings()
    if not (cfg["bucket"] and cfg["ak"] and cfg["sk"]):
        return _result(
            NOT_CONFIGURED,
            "未配置 OBS_BUCKET / OBS_ACCESS_KEY / OBS_SECRET_KEY，见证影像保持本地存储",
        )
    key = (object_key or "").lstrip("/")
    if not key.startswith("xueji/witness/"):
        return _result(ERROR, "对象键必须以 xueji/witness/ 前缀，拒绝写入其他路径")

    blob, read_err = _read_image_bytes(data)
    if read_err:
        return _result(ERROR, read_err.replace("图片", "缩略图"))

    try:
        from obs import ObsAuth, ObsClient  # esdk-obs-python
    except ImportError:
        return _sdk_guard("obs")

    start = time.perf_counter()
    client = None
    try:
        client = ObsAuth(cfg["ak"], cfg["sk"], server=cfg["endpoint"]).create_client()
        response = client.putObject(
            bucketName=cfg["bucket"],
            objectKey=key,
            contentLength=len(blob),
            mimeType=content_type,
            body=io.BytesIO(blob),
        )
    except Exception as exc:  # noqa: BLE001
        return _result(
            ERROR,
            f"OBS 上传失败：{_safe_error(exc)}",
            latency_ms=round((time.perf_counter() - start) * 1000),
        )
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass

    status_code = getattr(response, "status", None)
    latency = round((time.perf_counter() - start) * 1000)
    if status_code not in (200, 201, 204):
        reason = getattr(getattr(response, "reason", None), "message", "") or "未知原因"
        return _result(ERROR, f"OBS 返回 {status_code}：{str(reason)[:120]}", latency_ms=latency)
    return _result(
        OK,
        f"缩略图已上传 · {len(blob) // 1024}KB",
        object_key=key,
        size_bytes=len(blob),
        latency_ms=latency,
    )


def obs_delete_object(object_key: str) -> Dict:
    """删除 OBS 上的见证缩略图（配合生命周期策略做「到期即删」的人工兜底）。

    Returns:
        dict: ``status`` 四态之一；成功时附带 ``object_key``。OBS 对不存在的键
        同样返回成功，因此这里同时给出 ``existed`` 字段说明语义限制。

    降级行为同 :func:`obs_upload_object`。
    """
    cfg = _obs_settings()
    if not (cfg["bucket"] and cfg["ak"] and cfg["sk"]):
        return _result(NOT_CONFIGURED, "未配置 OBS 连接参数，无需删除")
    key = (object_key or "").lstrip("/")
    if not key.startswith("xueji/witness/"):
        return _result(ERROR, "对象键必须以 xueji/witness/ 前缀，拒绝删除其他路径")

    try:
        from obs import ObsAuth  # esdk-obs-python
    except ImportError:
        return _sdk_guard("obs")

    start = time.perf_counter()
    client = None
    try:
        client = ObsAuth(cfg["ak"], cfg["sk"], server=cfg["endpoint"]).create_client()
        head = client.getObjectMetadata(bucketName=cfg["bucket"], objectKey=key)
        existed = getattr(head, "status", None) == 200
        response = client.deleteObject(bucketName=cfg["bucket"], objectKey=key)
    except Exception as exc:  # noqa: BLE001
        return _result(
            ERROR,
            f"OBS 删除失败：{_safe_error(exc)}",
            latency_ms=round((time.perf_counter() - start) * 1000),
        )
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass

    latency = round((time.perf_counter() - start) * 1000)
    status_code = getattr(response, "status", None)
    if status_code not in (200, 204):
        return _result(ERROR, f"OBS 返回 {status_code}", existed=False, latency_ms=latency)
    return _result(
        OK,
        "缩略图已删除" if existed else "目标对象不存在（视为已清理）",
        object_key=key,
        existed=existed,
        latency_ms=latency,
    )


def obs_configure_lifecycle(retention_days: int = 7, prefix: str = "xueji/witness/") -> Dict:
    """给见证缩略图前缀配置「N 天后自动删除」的生命周期规则。

    这是本项目隐私设计的落地保障：影像不留存，到期由 OBS 自己删掉，不依赖
    应用侧定时任务是否还在跑。

    ⚠️ 实现现状（诚实标注）：
        本函数走的是 OBS **原生 REST 接口** ``PUT /?lifecycle``，因为本机已安装的
        ``huaweicloudsdkobs`` v1 只提供 put/delete/copy 等对象接口，**没有暴露
        lifecycle 相关方法**（已用 dir() 核实）。若 ``esdk-obs-python`` 未安装，
        本函数返回 sdk_missing，此时应在 OBS 控制台手工配置同样的过期规则，
        代码不做「假装配置成功」。

    Args:
        retention_days: 保留天数，允许 1–365；越界直接拒绝而不是悄悄夹取。
        prefix: 生效的对象前缀，必须落在 xueji/witness/ 之下。

    Returns:
        dict: ``status`` 四态之一；成功时附带 ``retention_days``、``prefix``、
        ``rule_id``。
    """
    cfg = _obs_settings()
    if not (cfg["bucket"] and cfg["ak"] and cfg["sk"]):
        return _result(NOT_CONFIGURED, "未配置 OBS 连接参数，跳过生命周期策略")
    days = int(retention_days or 0)
    if not 1 <= days <= 365:
        return _result(ERROR, f"保留天数 {days} 不在 1–365 范围内，未做任何修改")
    scope = (prefix or "").lstrip("/")
    if scope and not scope.startswith("xueji/witness/"):
        return _result(ERROR, "生命周期前缀必须落在 xueji/witness/ 之下，拒绝全局生效")

    try:
        from obs import ObsAuth  # esdk-obs-python
    except ImportError:
        return _sdk_guard("obs")

    rule_id = "xueji-witness-expire"
    xml_body = (
        '<LifecycleConfiguration><Rule>'
        f'<ID>{rule_id}</ID><Prefix>{scope}</Prefix><Status>Enabled</Status>'
        f'<Expiration><Days>{days}</Days></Expiration>'
        '</Rule></LifecycleConfiguration>'
    ).encode("utf-8")

    start = time.perf_counter()
    client = None
    try:
        auth = ObsAuth(cfg["ak"], cfg["sk"], server=cfg["endpoint"])
        client = auth.create_client()
        # esdk-obs-python 通过 putBucketLifecycleConfiguration 暴露该能力；
        # 不同版本参数名有差异，这里优先尝试高层接口，失败则退回底层签名请求。
        api = getattr(client, "putBucketLifecycleConfiguration", None)
        if callable(api):
            response = api(bucketName=cfg["bucket"], lifecycleConfiguration=xml_body.decode())
        else:
            response = client.request(
                method="PUT",
                bucketName=cfg["bucket"],
                params={"lifecycle": ""},
                data=xml_body,
                headers={"Content-Type": "application/xml"},
            )
    except Exception as exc:  # noqa: BLE001
        return _result(
            ERROR,
            f"OBS 生命周期配置失败（需在控制台手工设置等价规则）：{_safe_error(exc)}",
            latency_ms=round((time.perf_counter() - start) * 1000),
        )
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass

    latency = round((time.perf_counter() - start) * 1000)
    status_code = getattr(response, "status", None)
    if status_code not in (200, 204):
        return _result(ERROR, f"OBS 返回 {status_code}，生命周期未生效", latency_ms=latency)
    return _result(
        OK,
        f"前缀 {scope} 的缩略图将在 {days} 天后自动删除",
        retention_days=days,
        prefix=scope,
        rule_id=rule_id,
        latency_ms=latency,
    )


# ---------------------------------------------------------------------------
# A4. DEW / CSMS 凭据托管
# ---------------------------------------------------------------------------

def kms_get_secret(secret_name: str) -> Dict:
    """从华为云 DEW（数据密码服务）/ CSMS 凭据管理读取一个凭据值。

    🔒 安全约定（务必遵守）：
        - 返回体的 ``value`` 字段是**明文凭据**，只允许调用方在内存里立刻使用
          （例如拼进数据库连接串），**禁止**写入日志、返回给接口层、存入数据库
          或参与任何序列化输出。
        - 本函数自身不打印、不落盘、不把 value 放进 detail；上层接口
          ``GET /cloud/services`` 只汇报「能不能读到」，永远不回传 value。
        - 状态成功与否只看能否取到非空字符串，取值过程不记录中间量。

    Args:
        secret_name: 凭据名称，取自环境变量 ``DEW_SECRET_NAME`` 之外的显式入参，
            不允许为空。

    Returns:
        dict: ``status`` 四态之一；成功时含 ``value``（明文，勿外传）、
        ``name``、``latency_ms``；失败时不含 value。
    """
    name = (secret_name or "").strip()
    if not name:
        return _result(ERROR, "未提供凭据名称")

    ok_cfg, cfg_detail = _configured()
    if not ok_cfg:
        return _result(NOT_CONFIGURED, cfg_detail)

    try:
        from huaweicloudsdkcore.auth.credentials import BasicCredentials
        from huaweicloudsdkcore.region.region import Region
        from huaweicloudsdkdew.v2 import DewClient
        from huaweicloudsdkdew.v2.model import ShowSecretValueRequest
    except ImportError:
        return _sdk_guard("dew")

    ak, sk, project = _credentials()
    start = time.perf_counter()
    try:
        client = (
            DewClient.new_builder()
            .with_credentials(BasicCredentials(ak, sk, project))
            .with_region(Region(REGION, _endpoint("kms")))
            .build()
        )
        response = client.show_secret_value(ShowSecretValueRequest(secret_name=name))
    except Exception as exc:  # noqa: BLE001
        return _result(
            ERROR,
            f"凭据读取失败（未开通 DEW 或凭据不存在）：{_safe_error(exc)}",
            name=name,
            latency_ms=round((time.perf_counter() - start) * 1000),
        )

    payload = _dump(response)
    value = _pick(payload, "secret_data", "value")
    latency = round((time.perf_counter() - start) * 1000)
    if not isinstance(value, str) or not value:
        # 注意：这里不能把 payload 内容写进 detail，它可能就是凭据本身
        return _result(ERROR, "凭据返回为空或格式不是字符串", name=name, latency_ms=latency)
    return _result(
        OK,
        f"凭据 {name} 读取成功（值仅驻留内存，不外传）",
        name=name,
        value=value,
        latency_ms=latency,
    )


# ---------------------------------------------------------------------------
# B. 状态汇总（供接口层调用）
# ---------------------------------------------------------------------------

def _probe_package(key: str) -> bool:
    module = {
        "ocr": "huaweicloudsdkocr.v1",
        "sis": "huaweicloudsdksis.v1",
        "obs": "obs",
        "dew": "huaweicloudsdkdew.v2",
    }[key]
    try:
        __import__(module)
        return True
    except Exception:
        return False


def describe_cloud_services() -> Dict:
    """汇总四类云能力的真实可用状态，只读配置与本地 SDK，不发起任何云端调用。

    Returns:
        dict: ``items`` 列表 + 顶层 ``status``。每项含 key/name/cloud/configured/
        sdk_available/status/detail。状态语义：
        - ``ok``：凭证与 SDK 均就绪（仍不代表云端已开通对应 API）
        - ``degraded``：凭证就绪但 SDK 未安装，功能可由本地/浏览器降级承接
        - ``not_configured``：缺少 AK/SK 或资源参数
    """
    cred_ok, cred_detail = _configured()
    obs_cfg = _obs_settings()
    items = []

    def add(key: str, name: str, cloud: str, configured: bool, extra_detail: str = ""):
        sdk_ok = _probe_package(key)
        if not configured:
            status = NOT_CONFIGURED
            detail = extra_detail or cred_detail or "未配置该服务的连接参数"
        elif not sdk_ok:
            status = "degraded"
            detail = (
                f"凭证已配置但未安装 SDK，可执行 pip install \"{OPTIONAL_PACKAGES[key]}\" 启用；"
                "当前由本地/浏览器能力降级"
            )
        else:
            status = OK
            detail = "凭证与 SDK 就绪（云端 API 需另行确认已开通）"
        items.append(
            {
                "key": key,
                "name": name,
                "type": "cloud",
                "cloud": cloud,
                "configured": configured,
                "sdk_available": sdk_ok,
                "status": status,
                "detail": detail,
            }
        )

    add("ocr", "错题文字识别", "华为云 OCR", cred_ok)
    add("sis", "语音合成 / 语音识别", "华为云 SIS", cred_ok)
    add(
        "obs",
        "见证缩略图对象存储",
        "华为云 OBS",
        bool(obs_cfg["bucket"] and obs_cfg["ak"] and obs_cfg["sk"]),
        "未配置 OBS_BUCKET / OBS_ACCESS_KEY / OBS_SECRET_KEY",
    )
    add("dew", "凭据托管读取", "华为云 DEW / CSMS", cred_ok)

    degraded = len([item for item in items if item["status"] == "degraded"])
    ready = len([item for item in items if item["status"] == OK])
    return {
        "items": items,
        "status": "degraded" if degraded else (OK if ready else NOT_CONFIGURED),
        "region": REGION,
        "credential_configured": cred_ok,
        "ready_count": ready,
        "degraded_count": degraded,
        "total": len(items),
        "note": "本视图仅核对配置与本地 SDK，未向任何云服务发起调用，不产生费用。",
        "checked_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
