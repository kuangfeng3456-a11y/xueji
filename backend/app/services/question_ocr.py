"""先检测题目区域，再把裁切图交给现有 OCR。检测失败时识别整页。"""

from typing import Dict, List

from . import cloud_services as ocr
from . import question_detect as detector


def extract_question_image(image: bytes, kind: str = "general") -> Dict:
    detection = detector.detect_regions(image)
    recognized: List[dict] = []
    texts: List[str] = []
    if detection.get("status") == detector.OK and detection.get("regions"):
        for region in detection["regions"]:
            try:
                crop = detector.crop_region(image, region["box"])
            except Exception as exc:  # noqa: BLE001
                recognized.append({**region, "text": "", "ocr_status": "error", "detail": type(exc).__name__})
                continue
            result = ocr.ocr_extract_text(crop, kind=kind)
            text = str(result.get("text") or "").strip()
            recognized.append({**region, "text": text, "ocr_status": result.get("status")})
            if text:
                texts.append(text)
    if texts:
        page = {
            "status": ocr.OK,
            "detail": f"已按 {len(texts)} 个题目区域识别",
            "text": "\n".join(texts),
            "blocks": len(texts),
        }
    else:
        page = ocr.ocr_extract_text(image, kind=kind)
        if detection.get("status") == detector.OK and detection.get("regions"):
            page["detail"] = "分区没有识别出文字，已改用整页识别"
    page["detection"] = {
        "status": detection.get("status"),
        "detail": detection.get("detail") or "",
        "regions": recognized if recognized else detection.get("regions") or [],
    }
    return page
