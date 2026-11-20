# 拍题区域检测

拍题时先检测纸面上的题干、选项、手写答案或整页区域，再把裁切图交给已有的文字识别。检测不替代 OCR。

## 运行时与许可

- 推理使用 [ONNX Runtime](https://github.com/microsoft/onnxruntime)，许可证为 MIT。只使用 CPU。
- 裁切使用 Pillow。
- 主项目**不**依赖 Ultralytics。YOLOv8 及更新版本的代码与官方权重是 AGPL-3.0，不放进本仓库的依赖。
- 权重不提交到 git。推荐自行导出小型模型，或使用 Apache-2.0 的 [YOLOX](https://github.com/Megvii-BaseDetection/YOLOX)（Megvii）nano 权重，导出为下面约定的 ONNX。请在使用前核对你下载的那一版权重许可证。

可选安装：

```bash
pip install "onnxruntime>=1.16.0" "Pillow>=10.0.0"
```

## 放置权重

默认读取 `backend/models/question-detect.onnx`。也可以设置：

```bash
QUESTION_DETECT_MODEL=/path/to/question-detect.onnx
QUESTION_DETECT_LABELS=page,stem,option,handwriting
QUESTION_DETECT_CONF=0.35
```

类别顺序默认是 `page`、`stem`、`option`、`handwriting`。这是题目检测类别，不是通用物体类别；把只在 COCO 上训练的权重直接拿来，不能保证框出题干。

## 接受的 ONNX 输出

输入为 `1x3x640x640` 的 RGB，数值范围 0 到 1。输出三选一：

- `[1, N, 6]`：`x1,y1,x2,y2,score,class_id`，坐标在 640 输入图上
- `[1, 4+类别数, N]`：中心点、宽高和各类别分数
- `[1, N, 5+类别数]`：中心点、宽高、目标分数和各类别分数

没有权重、没有运行时，或推理报错时，接口仍对整页调用 OCR，并在 `detection.status` 中分别标为 `model_missing`、`runtime_missing` 或 `error`。
