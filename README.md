# image2svg

**Raster image → clean, editable, structured SVG**

`image2svg` 是一个面向栅格图像矢量重建的项目。

项目的当前目标不是生成一个“扩展名为 `.svg` 的图片”，而是尽可能从 PNG、JPG、WebP 或截图中恢复：

- 可编辑文字；
- 基础矢量图形；
- 清晰的路径；
- 合理的图层和分组；
- 简洁、可维护的 SVG 结构。

当前阶段专注于：

> **Image → Editable SVG**

PowerPoint、HTML、Canvas 等格式可以在 SVG 和中间表示稳定以后继续扩展，但不属于当前 MVP 的核心目标。

---

## Quick Start

```bash
# 安装核心转换能力
pip install -e .

# 如需 --qa 渲染与对比
pip install -e ".[qa]"

# 开发环境
pip install -e ".[dev,qa]"

# 基础转换
image2svg input.png -o output.svg

# 生成 render/comparison/audit/metrics
image2svg input.png -o output.svg --qa

# 严格禁止 raster/external image 资源
image2svg input.png --vector-only
```

QA 输出位于：

```text
output.qa/
├── audit.json
├── render.png
├── comparison.png
└── metrics.json
```

---

## 为什么做 image2svg

传统 raster-to-vector 工具擅长：

```text
pixels
  ↓
contours
  ↓
paths
```

这种方式可以获得视觉相似的 SVG，但经常产生：

- 大量细碎 path；
- 文字被轮廓化；
- 简单矩形变成复杂曲线；
- 图层缺少语义；
- SVG 虽然“可以编辑”，但实际上很难修改。

`image2svg` 希望进一步完成：

```text
Raster Image
      ↓
Visual Analysis
      ↓
Element Reconstruction
      ↓
Structured Scene Representation
      ↓
Editable SVG
```

例如原图中的一个圆角矩形：

```text
传统 tracing
→ 一个复杂 <path>
```

更理想的结果：

```xml
<rect
  x="120"
  y="80"
  width="320"
  height="160"
  rx="24"
  fill="#F3F4F6"
/>
```

---

# 当前目标

第一阶段主要支持以下图像：

- icon；
- logo；
- 简单插画；
- 信息图；
- 流程图；
- 科研示意图；
- UI / PPT 风格平面图形；
- 带少量文字的组合图形。

暂时不以以下内容为主要目标：

- 普通摄影照片；
- 高度写实图像；
- 极复杂纹理；
- 超复杂艺术插画；
- 完整 PowerPoint 原生重建。

---

# 什么叫“可编辑 SVG”

本项目不把“成功保存为 `.svg`”视为完成。

SVG 应尽量满足以下原则。

## 1. Native Vector

严格矢量模式下：

```xml
<image href="data:image/png;base64,...">
```

不应被用来伪装成 SVG。

真正的输出应主要由：

```text
path
rect
circle
ellipse
line
polyline
polygon
text
g
gradient
mask
clipPath
```

等 SVG 元素组成。

## 2. Semantic Geometry

能够用基础图元表达的内容，不应无理由转换成复杂 path。

例如：

```text
矩形 → rect
圆形 → circle
椭圆 → ellipse
直线 → line
文字 → text
```

复杂轮廓才使用 `path`。

## 3. Editable Text

能够识别出的文字优先恢复为 `<text>`，而不是把文字转成轮廓 path。

## 4. Structured Layers

相关元素应该合理分组：

```xml
<g id="background">
<g id="graphics">
<g id="icons">
<g id="text">
```

避免生成无法理解的大量随机 path。

---

# 系统架构

```text
Input Image
     │
     ▼
Image Normalization
     │
     ▼
Scene Analysis
     │
     ▼
Strategy Router
     │
     ├── Primitive Reconstruction
     ├── Text Reconstruction
     ├── Traditional Vector Tracing
     └── Generative SVG Backend
     │
     ▼
SVG Scene IR
     │
     ▼
SVG Renderer
     │
     ▼
SVG Audit
     │
     ▼
Render Comparison
     │
     ▼
Final SVG
```

系统采用：

> deterministic reconstruction + AI reconstruction

的混合策略。

当前 v0.1 只实现其中最小闭环：

```text
CLI
 ↓
Pipeline
 ↓
VTracerBackend
 ↓
SVG Audit
 ↓
SVG Output
 ↓ optional --qa
Render + Comparison
```

---

# Reconstruction Modes

## Trace Mode

适用于：

- 单色图；
- 扁平图形；
- 简单插画；
- 复杂自由轮廓。

可使用 VTracer、Potrace、ImageTracer 等传统算法。

## Semantic Mode

适用于 icon、logo、流程图、科研示意图、UI / PPT 风格图形。

系统尝试识别：

```text
rect
circle
line
arrow
text
group
path
```

并重新构造 SVG。

## Generative Mode

对于传统方法难以恢复的复杂视觉元素，可调用可插拔 SVG 生成模型，例如 StarVector、OmniSVG 或未来模型。

模型只作为 backend，而不是项目架构的一部分。

## Auto Mode

未来默认模式，根据图像特征自动选择：

```text
trace
semantic
generative
hybrid
```

---

# SVG Scene IR

系统不会让不同模块直接拼接 SVG 字符串。

后续结果将统一进入中间表示，例如：

```json
{
  "canvas": {
    "width": 1024,
    "height": 1024,
    "background": "transparent"
  },
  "elements": [
    {
      "id": "shape_001",
      "type": "rect",
      "bbox": [100, 100, 300, 200],
      "style": {
        "fill": "#2563EB",
        "radius": 24
      },
      "z_index": 1
    }
  ]
}
```

随后统一：

```text
Scene IR
   ↓
SVG Builder
   ↓
output.svg
```

---

# Quality Loop

SVG 生成后可以重新渲染并与输入图比较：

```text
Reference Image
      │
      ├──────────────┐
      │              │
      ▼              ▼
 Reconstruction    SVG
                     │
                     ▼
                SVG Render
                     │
                     ▼
              Comparison
```

当前 QA 会输出：

- SVG XML / viewBox 审计；
- embedded raster 数量；
- external resource 数量；
- node / path 数量；
- render preview；
- pixel error；
- edge difference；
- visual similarity。

视觉相似度只是指标之一。一个结构简单、易编辑的 SVG，有时比拥有更高像素分数但包含数千个 path 的 SVG 更有价值。

---

# Roadmap

## v0.1 — Reliable Vectorization

当前正在实现：

- [x] Python package skeleton；
- [x] CLI；
- [x] backend abstraction；
- [x] VTracer backend；
- [x] SVG audit；
- [x] SVG render 接口；
- [x] render comparison；
- [x] pytest 基础测试；
- [x] GitHub Actions CI；
- [ ] benchmark examples；
- [ ] 更多真实图片回归测试。

## v0.2 — Structured SVG

增加：

- rect；
- circle；
- ellipse；
- line；
- primitive detection；
- grouping；
- SVG Scene IR。

## v0.3 — Editable Text

增加：

- OCR；
- text bbox；
- `<text>` reconstruction；
- basic font/style estimation。

## v0.4 — Intelligent Reconstruction

增加：

- Vision / VLM analysis；
- element router；
- StarVector adapter；
- OmniSVG adapter；
- candidate selection。

## v0.5 — Compound Figures

支持流程图、科研示意图、信息图、PPT / UI 风格图片。

## Future

当 SVG 重建质量稳定以后，再考虑：

```text
SVG Scene IR
      ├── SVG
      ├── PPTX
      ├── HTML
      └── Canvas
```

PPTX 是潜在输出格式之一，而不是当前 image2svg MVP 的前置条件。

---

# Design Principle

> **Use the simplest editable vector structure that can faithfully explain the source image.**

不是生成最多的 path，也不是调用最大的模型，而是在：

```text
Visual Fidelity
Editability
Structural Simplicity
```

三者之间取得平衡。

详细开发设计见 [`DEVELOPMENT.md`](DEVELOPMENT.md)。
