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

例如原图中的一个圆角矩形，传统 tracing 可能得到一个复杂 `<path>`，而更理想的结果是：

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

## 当前目标

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

## 什么叫“可编辑 SVG”

本项目不把“成功保存为 `.svg`”视为完成。

SVG 应尽量满足以下原则。

### 1. Native Vector

严格矢量模式下，不应使用 `<image href="data:image/png;base64,...">` 来伪装成 SVG。

真正的输出应主要由以下元素组成：

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

### 2. Semantic Geometry

能够用基础图元表达的内容，不应无理由转换成复杂 path。

```text
矩形 → rect
圆形 → circle
椭圆 → ellipse
直线 → line
文字 → text
复杂轮廓 → path
```

### 3. Editable Text

能够识别出的文字优先恢复为 `<text>`，而不是把文字转成轮廓 path。

### 4. Structured Layers

相关元素应该合理分组，例如：

```xml
<g id="background">
<g id="graphics">
<g id="icons">
<g id="text">
```

避免生成无法理解的大量随机 path。

---

## 系统架构

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

---

## Reconstruction Modes

### Trace Mode

适用于单色图、扁平图形、简单插画和复杂自由轮廓。

可使用：

```text
VTracer
Potrace
ImageTracer
```

等传统算法。

### Semantic Mode

适用于 icon、logo、图标组合、流程图、科研示意图、UI / PPT 风格图形。

系统尝试识别并重新构造：

```text
rect
circle
line
arrow
text
group
path
```

### Generative Mode

对于传统方法难以恢复的复杂视觉元素，可调用可插拔 SVG 生成模型，例如：

```text
StarVector
OmniSVG
future SVG models
```

模型只作为 backend，而不是项目架构的一部分。

### Auto Mode

默认模式。系统根据图像特征自动选择：

```text
trace
semantic
generative
hybrid
```

---

## SVG Scene IR

系统不会让不同模块直接拼接 SVG 字符串，所有结果先进入统一中间表示。

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
    },
    {
      "id": "text_001",
      "type": "text",
      "bbox": [140, 150, 220, 60],
      "text": "image2svg",
      "style": {
        "font_size": 32,
        "fill": "#FFFFFF"
      },
      "z_index": 2
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

## Quality Loop

SVG 生成后必须重新渲染并检查：

```text
Reference Image
      │
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
                     │
                     ▼
                Refinement
```

评价内容包括：

- 前景范围；
- 边缘位置；
- 几何比例；
- 颜色；
- 留白；
- 对齐；
- 图层关系；
- SVG 复杂度。

视觉相似度只是指标之一。一个结构简单、易编辑的 SVG，有时比拥有更高像素分数但包含数千个 path 的 SVG 更有价值。

---

## Roadmap

### v0.1 — Reliable Vectorization

目标：

```text
image → SVG
```

完成：

- 图片读取；
- 透明背景处理；
- VTracer backend；
- SVG render；
- SVG audit；
- render comparison；
- CLI。

### v0.2 — Structured SVG

目标：

```text
image → structured SVG
```

增加：

- rect；
- circle；
- ellipse；
- line；
- primitive detection；
- grouping；
- SVG Scene IR。

### v0.3 — Editable Text

增加：

- OCR；
- text bbox；
- `<text>` reconstruction；
- basic font/style estimation。

### v0.4 — Intelligent Reconstruction

增加：

- Vision / VLM analysis；
- element router；
- StarVector adapter；
- OmniSVG adapter；
- candidate selection。

### v0.5 — Compound Figures

支持：

- 流程图；
- 科研示意图；
- 信息图；
- PPT / UI 风格图片。

重点提升：

```text
layout
layer
text
arrow
icon
group
```

### Future

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

## Project Status

当前处于：

> **Architecture & MVP implementation stage**

优先任务：

- [ ] 建立 CLI；
- [ ] 建立统一 IR；
- [ ] 接入 VTracer；
- [ ] 建立 SVG renderer；
- [ ] 建立 SVG audit；
- [ ] 建立 render comparison；
- [ ] 完成第一批 benchmark；
- [ ] 再逐步加入 semantic reconstruction。

详细开发计划见 [`DEVELOPMENT.md`](./DEVELOPMENT.md)。

原有 PPT 长期方案保留在 [`Slide2Edit_image_to_editable_ppt_plan.md`](./Slide2Edit_image_to_editable_ppt_plan.md)。

---

## Design Principle

项目最重要的原则是：

> **Use the simplest editable vector structure that can faithfully explain the source image.**

不是生成最多的 path，也不是调用最大的模型，更不是单纯追求像素级相似。

需要在以下三者之间取得平衡：

```text
Visual Fidelity
Editability
Structural Simplicity
```

---

## License

Research prototype.
