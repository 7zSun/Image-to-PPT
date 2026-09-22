# Examples

`input/` 保存本地回归图片，`output/` 保存生成结果。输出目录中的 SVG、PPTX、HTML、PNG 和 JSON 默认被 Git 忽略。

最小示例：

```bash
image2svg examples/input/demo.png \
  -o examples/output/demo.svg \
  --pptx examples/output/demo.pptx \
  --qa
```

常规 AI 重建示例：

```bash
image2svg examples/input/5.png \
  -o examples/output/5.svg \
  --pptx examples/output/5.pptx \
  --html examples/output/5.review.html \
  --preset balanced \
  --qa
```

论文和复杂多面板图片：

```bash
image2svg examples/input/arti/arti_2.png \
  -o examples/output/arti/02.svg \
  --pptx examples/output/arti/02.pptx \
  --html examples/output/arti/02.review.html \
  --preset paper \
  --qa
```

已挑选的公开样例位于 `docs/assets/showcase/`，完整输入与重建对照见 [`docs/SHOWCASE.md`](../docs/SHOWCASE.md)。当前展示选自 `input_chatgpt`、`input3`、`input4` 和 `arti`，只保留视觉效果较好的代表案例。

当前不重建箭头和连接关系。

典型输出：

```text
examples/output/
  5.svg
  5.pptx
  5.review.html
  5.qa/
    render.png
    comparison.png
    metrics.json
```

准备公开示例时，请确认输入图片拥有展示和再分发权限。大型 PPTX、审查页面或视频建议放在 GitHub Releases，而不是直接提交到源码仓库。
