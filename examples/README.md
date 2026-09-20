# Examples

本目录提供最小可运行 demo，用于快速验证 `image2svg` 的完整链路：

```text
PNG 图片 → SVG → SVG audit → (--qa) 渲染 + 对比 + 指标
```

## 目录结构

```text
examples/
├── README.md
├── input/
│   └── demo.png        # 简单几何图形：圆角矩形 + 圆 + 三角形
└── output/             # 运行后生成，默认不纳入版本控制
```

## 运行方式

在项目根目录执行：

```bash
image2svg examples/input/demo.png -o examples/output/demo.svg --qa
```

`--qa` 需要先安装 QA 依赖：

```bash
pip install -e ".[qa]"
```

## 预期输出

```text
examples/output/
├── demo.svg
└── demo.qa/
    ├── audit.json
    ├── render.png
    ├── comparison.png
    └── metrics.json
```

`demo.svg` 是被审计后的可编辑 SVG；`demo.qa/` 保存渲染预览、对比图以及审计与指标 JSON。

## AI 重建（可选）

配置好专用 AI 环境后（见 [`../AI.md`](../AI.md)），可以用 SAM3 / PaddleOCR
直接重建可编辑元素：

```bash
# 几何图元（rect / circle / polygon）
image2svg examples/input/demo.png -o examples/output/demo_sam3.svg \
  --sam3 --prompt rectangle --prompt circle --prompt triangle \
  --ai-device cuda --ai-background "#FFFFFF" --qa

# 文字（<text>）
image2svg some_text_image.png -o examples/output/ocr_demo.svg \
  --ocr --ocr-lang en --ai-device cpu --ai-background "#FFFFFF" --qa
```

需要设置 `IMAGE2SVG_AI_PYTHON` 指向 AI 环境的 Python。

### 结构图示例（`input/figure.png`）

`figure.png` 是一张卡片 + 箭头 + 图标 + 文字的教学示意图，用来验证
"感知 → Scene IR → 矢量重建" 的完整链路：

```bash
image2svg examples/input/figure.png -o examples/output/figure_refined.svg \
  --sam3 --prompt "rounded rectangle" --prompt arrow --prompt icon --prompt circle \
  --ocr --ocr-lang en --ai-device cuda --ocr-device cpu --ai-refine trace --qa
```

产出：文字为可编辑 `<text>`；卡片/圆形为 `<rect>/<ellipse>`；图标/箭头等
小型部件用 **VTracer 局部精细矢量化**为 `<path>`（`--ai-refine trace`）。
实测 `visual_similarity≈0.97`、51 个 `<text>`、289 个局部 `<path>`、`editable_score=100`。


