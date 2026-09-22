# Architecture

image2svg 将栅格截图解析为统一的 Scene IR，再从同一份场景数据导出 SVG、PPTX 和审阅页面。

## Current pipeline

```text
PNG / JPG / WebP
  -> GroundingDINO: panels, cards and visual objects
  -> MinerU: page layout, text blocks and image regions
  -> PaddleOCR: editable text and source coordinates
  -> SAM3: photos, logos and complex visual regions
  -> VTracer: simple flat graphics
  -> merge, deduplication, z-order and text fitting
  -> Scene IR
  -> SVG / PPTX / review HTML / QA render
```

## Scene IR

`Scene` 保存画布尺寸、背景和 `SceneElement` 列表。每个元素包含：

- 类型与原始坐标框
- 样式和层级
- 文本、路径、点集或局部图像
- 导出所需的可编辑属性

后端只负责产生结构化元素，不直接维护整页 SVG。这样可以让 SVG、PPTX 和 HTML 共用相同布局与清理规则。

## Runtime boundary

轻量环境负责 CLI、GUI、Scene IR、导出与 QA。模型推理在独立 AI 环境中执行，桥接脚本通过 JSON 交换结果。

```text
lightweight process -> bridge script -> AI environment -> JSON -> Scene IR
```

模型目录由 `IMAGE2SVG_MODEL_ROOT` 或 `--model-root` 指定，模型权重不进入源码仓库或 GUI 安装包。

## Reconstruction policy

- 文字恢复为原生文本元素。
- 矩形、圆角矩形、圆和椭圆优先恢复为基础图形。
- 简单纯色图标使用局部矢量化。
- 照片、点云、热力图和复杂多色图形保留原始局部裁剪。
- 禁止用整页截图冒充可编辑结果。
- 当前不恢复箭头和连接关系。

## Presets

`balanced` 用于常规流程图和信息图，组合 GroundingDINO、MinerU 与 PaddleOCR。

`paper` 在平衡模式基础上启用 SAM3，并使用 `photo`、`image`、`diagram`、`chart`、`point cloud` 和 `tactile` 提示词保留复杂科研子图。
