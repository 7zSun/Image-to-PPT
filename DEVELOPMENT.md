# image2svg Development Plan

## 1. 当前阶段

当前只解决一个核心问题：

> 给定一张栅格图像，生成视觉上接近、结构合理、真正可编辑的 SVG。

当前开发范围：

```text
PNG / JPG / WebP
        ↓
Editable SVG
```

当前阶段不要求：

```text
SVG → PPTX
```

但系统设计不得阻碍未来增加 PPTX exporter。

---

## 2. 核心问题定义

Raster-to-SVG 实际上包含两个不同问题。

### Problem A：Pixel Vectorization

目标：

```text
pixel boundary → vector path
```

典型方案：

```text
VTracer
Potrace
ImageTracer
```

优点：

- 稳定；
- 快；
- 不依赖模型；
- 任意图像都可以运行。

缺点：

- 缺乏语义；
- path 可能很多；
- 简单图形也可能被复杂化；
- 文字无法真正恢复。

### Problem B：Visual Reconstruction

目标：

```text
视觉内容
↓
理解其结构
↓
重新构造 SVG
```

例如：

```text
蓝色矩形
文字
箭头
圆形 icon
```

恢复为：

```text
rect
text
line
circle
```

这种结果更加适合后续编辑。

---

## 3. 总体策略

image2svg 不选择其中一条路线，而采用：

```text
Hybrid Vector Reconstruction
```

即：

```text
                ┌─ traditional trace
                │
Image → Router ─┼─ primitive reconstruction
                │
                ├─ text reconstruction
                │
                └─ generative SVG
```

然后统一进入：

```text
Scene IR
```

---

## 4. 输入类型分类

第一版不要试图支持“所有图片”。系统首先判断输入属于哪一种。

### Type A：Flat Graphic

例如：

```text
icon
logo
symbol
simple illustration
```

推荐：

```text
primitive reconstruction
+
tracing
```

### Type B：Structured Graphic

例如：

```text
流程图
架构图
科研示意图
UI截图
PPT风格图片
```

推荐：

```text
layout analysis
+
text reconstruction
+
primitive reconstruction
+
local vectorization
```

### Type C：Complex Illustration

推荐：

```text
generative SVG
+
traditional trace fallback
```

### Type D：Natural Image

例如照片、真实场景。当前阶段不作为主要目标。

---

## 5. 系统模块

### 5.1 Input Normalizer

职责：

- 读取 PNG / JPG / WebP；
- EXIF orientation；
- alpha channel；
- color space；
- background detection；
- resize preview。

输出：

```python
NormalizedImage
```

### 5.2 Image Analyzer

分析：

```text
width
height
alpha
background
foreground bbox
dominant colors
edge density
color count
texture complexity
OCR likelihood
```

这些信息供 Router 使用。

---

## 6. Strategy Router

Router 输出：

```text
TRACE
SEMANTIC
GENERATIVE
HYBRID
```

第一版不需要训练 classifier，可以采用规则。

例如：

```text
低颜色数 + 大面积纯色 → semantic / trace
大量纹理 → generative / trace
OCR区域明显 → semantic
简单轮廓 → trace
```

以后再替换成 VLM classifier。

---

## 7. Backend 抽象

系统禁止把具体模型写死在 pipeline 中。

统一接口：

```python
class VectorBackend:
    def reconstruct(self, image, context) -> VectorResult:
        ...
```

实现：

```text
VTracerBackend
PotraceBackend
StarVectorBackend
OmniSVGBackend
AgentSvgBackend
```

这样模型发生变化时，pipeline 不需要改。

---

## 8. Scene IR

Scene IR 是项目的核心。

基础结构：

```json
{
  "canvas": {},
  "elements": []
}
```

Element：

```json
{
  "id": "e001",
  "type": "rect",
  "bbox": [0, 0, 100, 80],
  "z_index": 0,
  "style": {},
  "children": []
}
```

第一版 element type：

```text
rect
circle
ellipse
line
polyline
polygon
path
text
group
image
```

其中 `image` 只允许在 hybrid / fallback mode 使用。

在：

```text
--vector-only
```

模式中禁止 `<image>`。

---

## 9. SVG Builder

```text
Scene
↓
SVG Builder
↓
SVG XML
```

SVG Builder 负责：

- viewBox；
- namespaces；
- element IDs；
- transform；
- z-order；
- style；
- group；
- gradient；
- mask；
- clip path。

不得由各 backend 自己拼整页 SVG。backend 只负责返回 `VectorResult`。

---

## 10. SVG Audit

每个 SVG 必须经过自动审计。

检查：

```text
XML是否合法
viewBox是否存在
是否可以渲染
是否引用外部资源
是否包含base64 raster
是否存在非法元素
是否包含极深嵌套
path数量
node数量
group数量
```

严格模式：

```text
--vector-only
```

要求：

```text
embedded raster = 0
external resource = 0
render error = 0
```

---

## 11. Render Pipeline

必须提供：

```text
SVG → PNG
```

的标准渲染过程。

所有 QA 必须基于相同：

```text
width
height
background
renderer
```

否则不同 renderer 的 antialiasing 会影响比较。

---

## 12. Comparison

至少计算：

```text
foreground coverage
edge difference
color difference
pixel difference
SSIM
```

后续可加入：

```text
LPIPS
DINO similarity
```

但不能只看一个指标。

---

## 13. Structural Quality

需要单独评价 SVG 结构。

例如：

```text
node_count
path_count
group_count
max_depth
native_text_count
primitive_count
embedded_image_count
```

因此 SVG 质量应视为：

```text
Quality
=
Visual Fidelity
+
Editability
+
Structural Simplicity
```

而不是：

```text
Quality = SSIM
```

---

## 14. Candidate Selection

对于同一个局部元素允许存在多个候选。

例如：

```text
crop
 │
 ├── VTracer
 ├── StarVector
 └── OmniSVG
```

得到多个 candidate 后全部：

```text
render
↓
audit
↓
compare
```

最终选择 best candidate。

但 v0.1 暂时不实现多模型竞争，只预留接口。

---

## 15. Agent Skill 的角色

项目未来应该提供：

```text
SKILL.md
```

兼容：

```text
Codex
Claude Code
OpenCode
```

但 Skill 不应该代替实际程序。

正确关系：

```text
Agent Skill
     │
     ▼
 image2svg CLI
     │
     ▼
 deterministic pipeline
```

Skill 负责：

```text
分析图片
选择模式
调用工具
查看 QA
根据错误继续修正
```

核心转换逻辑仍然应该存在于 `src/`，而不是只写在 Prompt 中。

---

## 16. 推荐项目目录

```text
image2svg/
│
├── README.md
├── DEVELOPMENT.md
├── SKILL.md
├── pyproject.toml
│
├── src/
│   └── image2svg/
│       ├── cli.py
│       ├── pipeline.py
│       │
│       ├── core/
│       │   ├── image.py
│       │   ├── scene.py
│       │   ├── element.py
│       │   └── result.py
│       │
│       ├── analyze/
│       │   ├── background.py
│       │   ├── palette.py
│       │   ├── geometry.py
│       │   └── router.py
│       │
│       ├── backends/
│       │   ├── base.py
│       │   ├── vtracer.py
│       │   ├── potrace.py
│       │   ├── starvector.py
│       │   └── omnisvg.py
│       │
│       ├── reconstruct/
│       │   ├── primitives.py
│       │   ├── text.py
│       │   └── paths.py
│       │
│       ├── svg/
│       │   ├── builder.py
│       │   ├── renderer.py
│       │   └── audit.py
│       │
│       └── qa/
│           ├── compare.py
│           └── metrics.py
│
├── scripts/
│   ├── render_svg.py
│   ├── compare.py
│   └── benchmark.py
│
├── tests/
│
├── examples/
│   ├── icons/
│   ├── logos/
│   ├── diagrams/
│   └── illustrations/
│
└── benchmarks/
```

---

## 17. CLI 设计

基础调用：

```bash
image2svg input.png
```

输出：

```text
input.svg
```

指定输出：

```bash
image2svg input.png -o result.svg
```

自动模式：

```bash
image2svg input.png --mode auto
```

传统 tracing：

```bash
image2svg input.png --mode trace
```

语义重建：

```bash
image2svg input.png --mode semantic
```

严格纯矢量：

```bash
image2svg input.png --vector-only
```

开启 QA：

```bash
image2svg input.png --qa
```

输出工作目录：

```text
output/
├── result.svg
├── render.png
├── comparison.png
├── audit.json
└── metrics.json
```

---

## 18. MVP：v0.1

这是当前真正应该开发的版本。

只实现：

```text
image
↓
normalize
↓
VTracer
↓
SVG
↓
audit
↓
render
↓
compare
```

不要加入：

```text
PPTX
SAM
VLM
OCR
StarVector
OmniSVG
multi-agent
```

这些全部推迟。

v0.1 要解决的是：

> 建立一个稳定、可测试、可评价的基础 pipeline。

---

## 19. v0.1 完成标准

### Functional

```text
PNG → SVG
JPG → SVG
WebP → SVG
```

### SVG

```text
valid XML
valid viewBox
browser render success
```

### Strict Mode

```text
embedded raster = 0
external dependency = 0
```

### QA

至少输出：

```text
render.png
comparison.png
audit.json
metrics.json
```

### Tests

必须有：

```text
unit test
CLI smoke test
SVG render test
audit test
```

---

## 20. v0.2：Primitive Reconstruction

v0.1 稳定以后增加：

```text
rectangle detection
circle detection
ellipse detection
line detection
```

并把 trace path 替换为语义 primitive。

例如：

```text
复杂矩形 path
↓
rect
```

这一阶段正式启用 Scene IR。

---

## 21. v0.3：Text Reconstruction

增加：

```text
OCR
text bbox
font size estimation
text color
text alignment
```

目标：

```text
文字轮廓
↓
<text>
```

这是“真正可编辑”提升最大的阶段之一。

---

## 22. v0.4：AI Vector Backend

此时再接入：

```text
StarVector
OmniSVG
Vision Agent
```

所有模型通过 backend interface 接入，不得让 pipeline 依赖具体模型实现。

---

## 23. v0.5：Structured Figure Reconstruction

支持：

```text
流程图
科研图
信息图
PPT风格图像
```

正式增加：

```text
layout
group
arrow
connector
semantic layers
```

完整流程变成：

```text
Whole-image Analysis
        ↓
Element Detection
        ↓
Router
        ↓
Local Reconstruction
        ↓
Scene IR
        ↓
SVG
        ↓
Render QA
```

---

## 24. Future：PPT

只有当以下能力稳定以后：

```text
text
primitive
group
layer
layout
```

才考虑：

```text
Scene IR
↓
PPTX exporter
```

由于 Scene IR 已经保留：

```text
type
bbox
style
z_index
text
children
```

届时可以直接映射：

```text
rect → PPT shape
text → PPT textbox
line → PPT line
```

因此目前没有必要提前开发 PPTX。

---

## 25. 第一阶段开发顺序

严格按照以下顺序：

```text
1. project skeleton
2. image normalizer
3. VTracer backend
4. SVG renderer
5. SVG audit
6. image comparison
7. CLI
8. tests
9. benchmark examples
10. Scene IR
11. primitive reconstruction
12. OCR
13. AI backends
```

不要调整成：

```text
先接几个大模型看看效果
```

因为那样很难知道效果提升到底来自哪里。

---

## 26. 核心开发原则

### Principle 1

优先恢复简单结构。

```text
rect > path
circle > path
text > text outline
```

### Principle 2

模型只是 backend。

不要让 StarVector、OmniSVG 或某个 VLM 成为系统架构。

### Principle 3

任何结果必须可验证。

```text
generate
↓
render
↓
audit
↓
compare
```

### Principle 4

视觉相似和编辑性同时评价。

不能出现：

```text
视觉很好
但 SVG 有 8000 个 path
```

然后认为效果很好。

### Principle 5

先解决有限问题，再扩大输入范围。

开发顺序应当是：

```text
icon / logo
↓
simple graphic
↓
diagram
↓
compound figure
↓
slide-like image
```

而不是从第一天开始支持任意图片。

---

## 27. 最终目标

image2svg 最终希望成为：

```text
Raster Image
     ↓
Visual Understanding
     ↓
Editable Scene Reconstruction
     ↓
Structured Vector Representation
```

核心资产不是某个模型。

真正应该沉淀的是：

```text
Scene IR
Reconstruction Router
Backend System
Quality Evaluation
Benchmark
```

只要这五部分设计稳定，未来无论出现新的 SVG 模型、OCR 模型、VLM，甚至需要输出 PPTX，都可以继续扩展，而无需重写整个项目。
