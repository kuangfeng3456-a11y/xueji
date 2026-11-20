"""拍题前的题目区域检测。

只负责定位，不代替文字识别。权重使用 ONNX，运行时是 MIT 许可的
ONNX Runtime；不依赖 Ultralytics。权重不随仓库分发。
模型缺失、运行时缺失或推理失败时，调用方应退回整页识别。
"""

import os
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

DEFAULT_LABELS = ("page", "stem", "option", "handwriting")
INPUT_SIZE = 640
MODEL_MISSING = "model_missing"
RUNTIME_MISSING = "runtime_missing"
ERROR = "error"
OK = "ok"

_SESSION = None
_SESSION_PATH = ""


def labels() -> Tuple[str, ...]:
    raw = os.getenv("QUESTION_DETECT_LABELS", "").strip()
    if not raw:
        return DEFAULT_LABELS
    names = tuple(part.strip() for part in raw.split(",") if part.strip())
    return names or DEFAULT_LABELS


def model_path() -> Path:
    configured = os.getenv("QUESTION_DETECT_MODEL", "").strip()
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[2] / "models" / "question-detect.onnx"


def confidence_threshold() -> float:
    try:
        return float(os.getenv("QUESTION_DETECT_CONF", "0.35"))
    except ValueError:
        return 0.35


def detect_regions(image: bytes) -> Dict:
    """返回题目区域。失败时 regions 为空，并给出原因，不编造框。"""
    path = model_path()
    if not path.is_file():
        return {
            "status": MODEL_MISSING,
            "detail": "未放置题目检测权重，已改用整页识别",
            "regions": [],
        }
    try:
        import onnxruntime  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError:
        return {
            "status": RUNTIME_MISSING,
            "detail": "未安装 onnxruntime 或 Pillow，已改用整页识别",
            "regions": [],
        }
    try:
        regions = _infer(path, image)
    except Exception as exc:  # noqa: BLE001
        return {
            "status": ERROR,
            "detail": f"题目区域检测失败，已改用整页识别：{type(exc).__name__}"[:180],
            "regions": [],
        }
    return {
        "status": OK,
        "detail": f"检出 {len(regions)} 个区域",
        "regions": regions,
    }


def crop_region(image: bytes, box: Sequence[float]) -> bytes:
    import io

    from PIL import Image

    picture = Image.open(io.BytesIO(image)).convert("RGB")
    width, height = picture.size
    x1 = max(0, min(width - 1, int(box[0])))
    y1 = max(0, min(height - 1, int(box[1])))
    x2 = max(x1 + 1, min(width, int(box[2])))
    y2 = max(y1 + 1, min(height, int(box[3])))
    buffer = io.BytesIO()
    picture.crop((x1, y1, x2, y2)).save(buffer, format="JPEG", quality=90)
    return buffer.getvalue()


def _session(path: Path):
    global _SESSION, _SESSION_PATH
    key = str(path.resolve())
    if _SESSION is not None and _SESSION_PATH == key:
        return _SESSION
    import onnxruntime as ort

    _SESSION = ort.InferenceSession(key, providers=["CPUExecutionProvider"])
    _SESSION_PATH = key
    return _SESSION


def _infer(path: Path, image: bytes) -> List[dict]:
    import io

    import numpy as np
    from PIL import Image

    picture = Image.open(io.BytesIO(image)).convert("RGB")
    width, height = picture.size
    resized = picture.resize((INPUT_SIZE, INPUT_SIZE))
    array = np.asarray(resized, dtype=np.float32) / 255.0
    blob = np.transpose(array, (2, 0, 1))[None, ...]
    session = _session(path)
    name = session.get_inputs()[0].name
    output = session.run(None, {name: blob})[0]
    return decode_predictions(output.tolist(), tuple(output.shape), width, height)


def decode_predictions(values, shape: Tuple[int, ...], width: int, height: int) -> List[dict]:
    """解析常见的已解码框、YOLOv8 或 YOLOv5 ONNX 输出。坐标映射回原图。"""
    if len(shape) != 3:
        raise ValueError("检测输出维度无法识别")
    threshold = confidence_threshold()
    names = labels()
    if shape[-1] == 6:
        boxes = _decoded_boxes(values[0], width, height, INPUT_SIZE, threshold, names)
    elif shape[1] < shape[2] and shape[1] >= 5:
        boxes = _channels_first(values[0], width, height, threshold, names)
    elif shape[2] > 6:
        boxes = _rows_last(values[0], width, height, threshold, names)
    else:
        raise ValueError("检测输出形状无法识别")
    return _nms(boxes, 0.45)[:8]


def _decoded_boxes(rows, width, height, input_size, threshold, names) -> List[dict]:
    scale_x = width / float(input_size)
    scale_y = height / float(input_size)
    found = []
    for row in rows:
        score = float(row[4])
        if score < threshold:
            continue
        class_id = int(row[5])
        found.append(
            _region(
                float(row[0]) * scale_x,
                float(row[1]) * scale_y,
                float(row[2]) * scale_x,
                float(row[3]) * scale_y,
                score,
                class_id,
                names,
                width,
                height,
            )
        )
    return found


def _channels_first(channels, width, height, threshold, names) -> List[dict]:
    count = len(channels[0])
    found = []
    for index in range(count):
        cx = float(channels[0][index])
        cy = float(channels[1][index])
        bw = float(channels[2][index])
        bh = float(channels[3][index])
        scores = [float(channels[4 + cls][index]) for cls in range(len(channels) - 4)]
        class_id, score = _best(scores)
        if score < threshold:
            continue
        found.append(_xywh_region(cx, cy, bw, bh, score, class_id, names, width, height))
    return found


def _rows_last(rows, width, height, threshold, names) -> List[dict]:
    found = []
    for row in rows:
        objectness = float(row[4])
        scores = [float(value) * objectness for value in row[5:]]
        class_id, score = _best(scores)
        if score < threshold:
            continue
        found.append(
            _xywh_region(float(row[0]), float(row[1]), float(row[2]), float(row[3]), score, class_id, names, width, height)
        )
    return found


def _best(scores: List[float]) -> Tuple[int, float]:
    if not scores:
        return 0, 0.0
    class_id = max(range(len(scores)), key=lambda index: scores[index])
    return class_id, scores[class_id]


def _xywh_region(cx, cy, bw, bh, score, class_id, names, width, height) -> dict:
    return _region(cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2, score, class_id, names, width, height)


def _region(x1, y1, x2, y2, score, class_id, names, width, height) -> dict:
    box = [
        round(max(0.0, min(float(width), x1)), 1),
        round(max(0.0, min(float(height), y1)), 1),
        round(max(0.0, min(float(width), x2)), 1),
        round(max(0.0, min(float(height), y2)), 1),
    ]
    label = names[class_id] if 0 <= class_id < len(names) else f"class_{class_id}"
    return {"label": label, "score": round(score, 4), "box": box}


def _nms(regions: List[dict], iou_threshold: float) -> List[dict]:
    ordered = sorted(regions, key=lambda item: item["score"], reverse=True)
    kept: List[dict] = []
    while ordered:
        current = ordered.pop(0)
        kept.append(current)
        ordered = [item for item in ordered if _iou(current["box"], item["box"]) < iou_threshold]
    kept.sort(key=lambda item: (item["box"][1], item["box"][0]))
    return kept


def _iou(left: Sequence[float], right: Sequence[float]) -> float:
    x1 = max(left[0], right[0])
    y1 = max(left[1], right[1])
    x2 = min(left[2], right[2])
    y2 = min(left[3], right[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    if inter <= 0:
        return 0.0
    area_left = max(0.0, left[2] - left[0]) * max(0.0, left[3] - left[1])
    area_right = max(0.0, right[2] - right[0]) * max(0.0, right[3] - right[1])
    union = area_left + area_right - inter
    return inter / union if union else 0.0


def reset_session() -> None:
    global _SESSION, _SESSION_PATH
    _SESSION = None
    _SESSION_PATH = ""
