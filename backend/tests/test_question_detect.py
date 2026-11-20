"""题目区域检测：有框则分区识别，缺失或失败则整页识别。"""

import app.services.question_detect as detect
import app.services.question_ocr as question_ocr


def test_decode_prefers_explicit_boxes_and_drops_low_score():
    rows = [[
        [10, 10, 110, 60, 0.9, 1],
        [10, 10, 110, 60, 0.2, 1],
        [200, 20, 300, 80, 0.8, 2],
    ]]
    regions = detect.decode_predictions(rows, (1, 3, 6), width=640, height=640)
    assert [item["label"] for item in regions] == ["stem", "option"]
    assert regions[0]["box"][0] == 10


def test_channels_first_finds_one_box():
    width_anchors = 8
    channels = [
        [320] * width_anchors,
        [320] * width_anchors,
        [80] * width_anchors,
        [40] * width_anchors,
        [0.01] * width_anchors,
        [0.95] + [0.1] * (width_anchors - 1),
    ]
    regions = detect.decode_predictions([channels], (1, 6, width_anchors), width=640, height=640)
    assert len(regions) == 1
    assert regions[0]["label"] == "stem"
    assert regions[0]["score"] == 0.95


def test_missing_weight_falls_back_to_full_page(monkeypatch):
    monkeypatch.setattr(detect, "detect_regions", lambda image: {"status": "model_missing", "detail": "未放置", "regions": []})
    calls = []

    def fake_ocr(image, kind="general"):
        calls.append(image)
        return {"status": "ok", "text": "整页题干", "detail": "ok"}

    monkeypatch.setattr(question_ocr.ocr, "ocr_extract_text", fake_ocr)
    result = question_ocr.extract_question_image(b"full-image")
    assert result["text"] == "整页题干"
    assert result["detection"]["status"] == "model_missing"
    assert calls == [b"full-image"]


def test_detected_regions_are_cropped_before_ocr(monkeypatch):
    monkeypatch.setattr(
        question_ocr.detector,
        "detect_regions",
        lambda image: {
            "status": "ok",
            "detail": "检出 2 个区域",
            "regions": [
                {"label": "stem", "score": 0.9, "box": [0, 0, 10, 10]},
                {"label": "option", "score": 0.8, "box": [10, 10, 20, 20]},
            ],
        },
    )
    monkeypatch.setattr(question_ocr.detector, "crop_region", lambda image, box: b"crop-" + str(box[0]).encode())
    seen = []

    def fake_ocr(image, kind="general"):
        seen.append(image)
        text = "题干" if image.startswith(b"crop-0") else "选项"
        return {"status": "ok", "text": text, "detail": "ok"}

    monkeypatch.setattr(question_ocr.ocr, "ocr_extract_text", fake_ocr)
    result = question_ocr.extract_question_image(b"full-image")
    assert result["status"] == "ok"
    assert result["text"] == "题干\n选项"
    assert [item["text"] for item in result["detection"]["regions"]] == ["题干", "选项"]
    assert b"full-image" not in seen


def test_inference_error_uses_full_page(monkeypatch):
    monkeypatch.setattr(
        question_ocr.detector,
        "detect_regions",
        lambda image: {"status": "error", "detail": "题目区域检测失败", "regions": []},
    )
    monkeypatch.setattr(
        question_ocr.ocr,
        "ocr_extract_text",
        lambda image, kind="general": {"status": "ok", "text": "整页", "detail": "ok"},
    )
    result = question_ocr.extract_question_image(b"full-image")
    assert result["text"] == "整页"
    assert result["detection"]["status"] == "error"


def test_ocr_endpoint_keeps_contract_when_detector_missing(api, auth, monkeypatch):
    monkeypatch.setattr(
        "app.services.question_ocr.extract_question_image",
        lambda image, kind="general": {
            "status": "not_configured",
            "detail": "未配置华为云凭证",
            "text": "",
            "detection": {"status": "model_missing", "detail": "未放置题目检测权重", "regions": []},
        },
    )
    response = api(
        "POST",
        "/api/cloud/ocr/extract",
        token=auth["token"],
        files={"file": ("q.jpg", b"jpeg-bytes", "image/jpeg")},
        data={"kind": "general"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "not_configured"
    assert body["text"] == ""
    assert body["detection"]["status"] == "model_missing"
    assert body["filename"] == "q.jpg"


def test_real_detector_without_weight_does_not_claim_success(tmp_path, monkeypatch):
    monkeypatch.setenv("QUESTION_DETECT_MODEL", str(tmp_path / "absent.onnx"))
    detect.reset_session()
    result = detect.detect_regions(b"not-an-image")
    assert result["status"] == "model_missing"
    assert result["regions"] == []
