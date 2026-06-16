# Slide2Edit：面向类 PPT 图像的分层可编辑矢量重建方案

## 1. 项目重新定位

原始目标可以表述为：

> 将一张包含 icon、文本框、箭头、文字、基础形状、图片、图表等元素的 PPT 图片，转化为可编辑的矢量图，甚至进一步生成可编辑 PPT。

建议不要将项目简单定义为 **image2svg**，而应定义为：

> **PPT screenshot / AI-generated slide image → layered editable SVG → editable PPTX**

或者中文表述为：

> **面向类 PPT 图像的分层矢量化与可编辑 PPT 重建系统。**

核心思想不是“整图 image2svg”，而是：

```text
一张 PPT 图片
↓
拆解为多个可编辑元素
↓
每类元素选择最合适的重建方式
↓
生成统一中间表示 IR
↓
导出 SVG / 可粘贴 SVG / PPTX
```

StarVector 和 OmniSVG 可以直接用于**局部视觉元素的 SVG 生成**，但不建议让它们承担全部任务。文字、文本框、箭头、矩形、圆角卡片等 PPT 高频对象，最好恢复成真正的 **text box / shape / line / arrow**，否则最终虽然是 SVG，但在 PPT 中的编辑体验会很差。

---

## 2. 最终目标分级

### Level 1：视觉可还原

输出一张 SVG，看起来和原图接近。

```text
图片 → SVG
```

特点：

- 实现难度最低；
- 视觉上可以比较接近；
- 但编辑性较弱；
- 适合作为最初 demo。

---

### Level 2：局部可编辑

文字可以改，图标是 SVG，背景和复杂图片保留为 image。

```text
图片 → layered SVG
```

特点：

- 文字保留为 `<text>` 或独立文本对象；
- 图标、插画、装饰元素可作为 SVG；
- 复杂照片、纹理、图表暂时保留为 raster image；
- 适合作为第一阶段主要目标。

---

### Level 3：PPT 原生可编辑

文字是 PPT 文本框，矩形是 PPT 形状，箭头是 PPT 线条，图标是 SVG/shape，图片是图片对象。

```text
图片 → PPTX
```

特点：

- 这是最终目标；
- 用户可以在 PowerPoint 中直接编辑主要元素；
- 难点在于元素语义恢复、图层恢复、字体样式估计和复杂 SVG 转 PPT 对象。

---

## 3. 总体架构设计

完整流程建议如下：

```text
Input PPT Image
↓
1. Canvas normalization
↓
2. Layout parsing
↓
3. OCR + text reconstruction
↓
4. Element segmentation
↓
5. Element classification / reconstruction router
↓
6. SVG generation / shape reconstruction
↓
7. Layer ordering
↓
8. Unified intermediate representation
↓
9. Rendering feedback correction
↓
10. Export SVG / PPTX
```

项目真正的核心不是“调用 StarVector/OmniSVG”，而是设计一个可靠的：

```text
视觉元素 → 可编辑对象
```

转换框架。

---

## 4. 输入输出定义

### 4.1 输入

输入为一张类 PPT 图片，例如：

- GPT / DALL·E / Midjourney / Canva 生成的类 PPT 图；
- 截图形式的 slide；
- 海报式信息图；
- 16:9 演示页面；
- 包含文字、卡片、icon、箭头、流程图等元素的页面。

第一版建议限定输入范围：

```text
1920×1080 或 1280×720
横版 16:9
背景相对干净
以文字、卡片、icon、箭头、基础形状为主
```

暂时不建议第一版处理：

```text
复杂照片
复杂渐变
复杂图表
高密度表格
强透视图像
真实扫描文档
手绘风格页面
```

---

### 4.2 输出一：完整 SVG

```text
slide.svg
```

特点：

- 整体可缩放；
- 部分元素可编辑；
- 可以插入 PowerPoint；
- 适合作为中间结果或可视化结果。

---

### 4.3 输出二：可编辑 PPTX

```text
slide_reconstructed.pptx
```

特点：

- 文字是真文本；
- 矩形、圆、箭头是 PPT 原生形状；
- icon 是 SVG 或转换后的 shape；
- 复杂插画/照片作为图片保留；
- 用户打开 PPT 后可以编辑主要内容。

---

## 5. 为什么不建议直接整图生成 SVG

一种直觉路线是：

```text
整张 PPT 图片 → StarVector / OmniSVG → 完整 SVG
```

这条路线不推荐作为主路线，原因如下：

1. **整图元素太多，模型容易漏元素。**  
   一张 PPT 可能包含几十个对象，直接整图生成时模型可能忽略小图标、细箭头、浅色装饰等元素。

2. **文字容易被转成 path，失去可编辑性。**  
   对 PPT 重建来说，文字必须变成真正的文本框，而不是曲线路径。

3. **层级关系不可控。**  
   PPT 的视觉效果高度依赖 z-index、遮挡关系、透明度和阴影。

4. **复杂页面 SVG 代码太长。**  
   长 SVG 代码会导致生成不稳定、语法错误、路径冗余等问题。

5. **PPT 对象语义无法恢复。**  
   用户真正需要的是文本框、形状、箭头、表格、图片等对象，而不仅是一堆 SVG path。

更合理的路线是：

```text
整图解析
↓
拆成元素
↓
每个元素单独处理
↓
再组合成完整 SVG / PPT
```

也就是：

```text
whole-image understanding + local vectorization + global reconstruction
```

---

## 6. 模块设计

## 6.1 Module 1：画布归一化

输入图片后，先统一坐标系统。

```json
{
  "canvas_width": 1920,
  "canvas_height": 1080,
  "slide_ratio": "16:9"
}
```

所有后续元素都记录在同一个坐标系里：

```json
{
  "bbox": [x, y, w, h]
}
```

PPT 输出时再将像素坐标转为 PPT 尺寸：

```text
x_ppt = x_px / image_width  * slide_width
y_ppt = y_px / image_height * slide_height
w_ppt = w_px / image_width  * slide_width
h_ppt = h_px / image_height * slide_height
```

需要记录：

- 原始分辨率；
- 归一化分辨率；
- slide ratio；
- 背景颜色；
- 主色调；
- 坐标缩放关系。

---

## 6.2 Module 2：版面结构检测

这一步的目标是先找出页面上的语义区域：

```text
标题区域
正文区域
卡片区域
icon 区域
箭头区域
图表区域
图片区域
背景区域
装饰区域
```

不要一上来用 SAM3 对所有东西随机分割。SAM 类模型给的是 mask，不是 PPT 语义对象。你需要先做版面级检测。

可选技术：

```text
DocLayout detector
PaddleOCR layout analysis
自训练 YOLO
Grounding DINO + SAM
VLM layout parser
```

输出示例：

```json
[
  {
    "id": "r001",
    "type": "title_candidate",
    "bbox": [120, 80, 800, 90],
    "confidence": 0.94
  },
  {
    "id": "r002",
    "type": "icon_candidate",
    "bbox": [150, 260, 80, 80],
    "confidence": 0.88
  },
  {
    "id": "r003",
    "type": "card_candidate",
    "bbox": [100, 220, 500, 300],
    "confidence": 0.91
  }
]
```

---

## 6.3 Module 3：OCR 和文字重建

文字必须单独走 OCR，不建议交给 StarVector 或 OmniSVG。

原因是：

> StarVector/OmniSVG 生成的文字可能变成 SVG path，而不是可编辑文本。

你的目标是 PPT 可编辑，所以文字应该变成：

```text
PPT text box
```

OCR 输出应该包括：

```json
{
  "type": "text",
  "text": "Market Analysis",
  "bbox": [120, 80, 600, 70],
  "font_size": 42,
  "color": "#1F2937",
  "font_weight": "bold",
  "align": "left"
}
```

需要估计的文字属性包括：

```text
文本内容
文本框位置
字号
颜色
粗细
对齐方式
行距
换行
旋转角度
```

第一版字体不需要完全一致，可以做粗略映射：

```text
无衬线 → Aptos / Arial / Microsoft YaHei
衬线 → Times New Roman / SimSun
代码 → Consolas
```

### 文字框聚合

不要只识别单个字，而要恢复段落级文本框。

流程：

```text
word boxes
↓
line grouping
↓
paragraph grouping
↓
text box reconstruction
```

聚合依据：

- 行间距；
- x 方向对齐；
- 字号相似；
- 颜色相似；
- 语义连续；
- bbox 空间接近。

例如下面的内容：

```text
• Market size increased by 35%
• User retention improved
• Revenue growth accelerated
```

应该恢复为一个 bullet list text box，而不是三个孤立文本框。

---

## 6.4 Module 4：元素分割

这一步才使用 SAM3。

对 layout detector 给出的候选区域进行 mask refine：

```text
bbox prompt → 精细 mask
text prompt → 找相同类型元素
point prompt → 修正局部边界
```

例如：

```text
检测到一个 icon bbox
↓
用 SAM3 精细抠出 icon mask
↓
裁剪 icon crop
↓
送入 StarVector / OmniSVG
```

SAM3 适合做：

```text
图标抠图
装饰图案抠图
插画区域抠图
复杂背景分离
相似元素批量发现
```

但不建议让 SAM3 决定最终元素类型。

---

## 6.5 Module 5：元素分类器 / Reconstruction Router

这是整个项目最重要的模块之一。

每个候选元素都要先分类，再决定怎么重建。

```text
element crop + bbox + mask + OCR result
↓
router
↓
选择重建方法
```

### 元素类别与重建方式

| 元素类型 | 重建方式 | 输出 |
|---|---|---|
| text | OCR + style estimation | PPT textbox / SVG text |
| rectangle | 几何拟合 | PPT rectangle / SVG rect |
| rounded rectangle | 几何拟合 | PPT rounded rectangle / SVG rect rx |
| circle / ellipse | 几何拟合 | PPT oval / SVG ellipse |
| line | 线段检测 | PPT line / SVG line |
| arrow | 线段 + 箭头检测 | PPT connector / SVG marker |
| icon | StarVector / OmniSVG | SVG group |
| illustration | OmniSVG / raster fallback | SVG group / image |
| photo | 保留原图 | image |
| chart | 第一版保留原图 | image |
| table | OCR + table parser | PPT table |
| background | 色块 / 渐变 / 图片 | shape / image |

### Router 的判断方式

Router 可以由三部分组成：

```text
规则判断 + CV 特征 + VLM 判断
```

示例规则：

```text
OCR 命中文本 → text
轮廓接近矩形且颜色单一 → rounded_rect / rect
小尺寸、多色、语义明确 → icon
大面积复杂纹理 → image
有坐标轴/柱状结构 → chart
```

---

## 7. StarVector 和 OmniSVG 的使用策略

StarVector 和 OmniSVG 可以作为系统中的 **visual element SVG generator**。

它们不应该替代 OCR 和几何拟合，而应该负责：

```text
icon
logo
复杂装饰
插画
语义图形
```

不应该主要负责：

```text
文字
文本框
基础形状
箭头
版面结构
```

---

## 7.1 简单 icon 优先 StarVector

```text
输入：icon crop
输出：局部 SVG code
```

适用元素：

```text
文件夹图标
放大镜图标
箭头图标
人物小图标
流程节点图标
logo 风格图形
```

原因：

```text
StarVector 更偏代码生成和结构化 SVG，适合相对清晰的 icon / logo。
```

---

## 7.2 复杂插画优先 OmniSVG

```text
输入：illustration crop
输出：局部 SVG code
```

适用元素：

```text
复杂装饰图案
多色插画
卡通人物
AI 生成风格图标
复杂视觉符号
```

原因：

```text
OmniSVG 更强调复杂 SVG 生成和多模态 SVG 表达能力。
```

---

## 7.3 双模型候选 + 渲染评分

不要只调用一个模型。建议对 icon / illustration 同时生成多个候选：

```text
icon crop
↓
StarVector 生成 SVG_A
OmniSVG 生成 SVG_B
VTracer 生成 SVG_C，可选
↓
全部渲染成 PNG
↓
和原 crop 比较
↓
选最优
```

评分指标可以包括：

```text
pixel similarity
CLIP / DINO similarity
边缘相似度
颜色相似度
SVG 代码复杂度
是否能成功渲染
path 数量
```

最终选择：

```text
score = 视觉相似度 - λ1 * SVG复杂度 - λ2 * 语法错误惩罚
```

这样比手工指定 StarVector 或 OmniSVG 更稳。

---

## 8. 基础形状重建策略

基础形状不要主要依赖 SVG 生成模型。

这些元素应该用几何方法恢复：

```text
圆角矩形
标题背景条
卡片
分隔线
流程箭头
圆形编号
边框
```

原因：

1. 更准确；
2. 更可控；
3. PPT 中可编辑性更好；
4. SVG 代码更简洁。

例如一个圆角矩形，用 StarVector 可能生成：

```xml
<path d="M 12.3 0 C ..."/>
```

但真正想要的是：

```xml
<rect x="100" y="220" width="500" height="300" rx="24" fill="#F9FAFB"/>
```

或者 PPT 中的：

```text
MSO_SHAPE.ROUNDED_RECTANGLE
```

---

## 9. 箭头重建策略

PPT 中箭头非常常见，不能简单当作 icon。

检测方式：

```text
边缘检测
霍夫线检测
细长区域判断
箭头头部三角形检测
起点终点估计
```

输出示例：

```json
{
  "type": "arrow",
  "start": [620, 360],
  "end": [800, 360],
  "stroke_width": 4,
  "color": "#2563EB",
  "arrow_end": true
}
```

SVG 表达：

```xml
<line x1="620" y1="360" x2="800" y2="360"
      stroke="#2563EB"
      stroke-width="4"
      marker-end="url(#arrowhead)" />
```

PPT 表达：

```text
add_connector 或 line with arrowhead
```

---

## 10. 图层顺序恢复

初始规则：

```text
背景色块 < 大卡片 < 小形状 < 图片/icon < 文字
```

更细的默认层级：

| 元素 | 默认层级 |
|---|---:|
| background | 0 |
| decorative background | 1 |
| card / panel | 2 |
| chart / image | 3 |
| shape | 4 |
| arrow / connector | 5 |
| icon | 6 |
| text | 7 |

然后用遮挡关系修正：

```text
如果 A 和 B 重叠，且 A 的可见区域被 B 切掉，则 B 的 z_index > A
```

最后做 render feedback：

```text
生成图像
↓
和原图对比
↓
如果某区域误差大，检查对应元素层级
```

---

## 11. 统一中间表示 IR

一定要设计一个中间表示，不要直接拼 SVG。

建议 IR 长这样：

```json
{
  "canvas": {
    "width": 1920,
    "height": 1080,
    "background": "#FFFFFF"
  },
  "elements": [
    {
      "id": "e001",
      "type": "text",
      "bbox": [120, 70, 700, 80],
      "z_index": 10,
      "text": "Business Growth",
      "style": {
        "font_size": 44,
        "font_family": "Aptos",
        "font_weight": "bold",
        "color": "#111827",
        "align": "left"
      }
    },
    {
      "id": "e002",
      "type": "rounded_rect",
      "bbox": [100, 220, 500, 300],
      "z_index": 1,
      "style": {
        "fill": "#F9FAFB",
        "stroke": "#E5E7EB",
        "stroke_width": 2,
        "radius": 24
      }
    },
    {
      "id": "e003",
      "type": "icon_svg",
      "bbox": [140, 260, 80, 80],
      "z_index": 6,
      "svg": "<svg>...</svg>"
    },
    {
      "id": "e004",
      "type": "arrow",
      "bbox": [620, 360, 180, 40],
      "z_index": 5,
      "style": {
        "stroke": "#2563EB",
        "stroke_width": 4,
        "arrow_end": true
      }
    }
  ]
}
```

这个 IR 是系统的核心资产。

有了它，可以导出：

```text
IR → SVG
IR → PPTX
IR → HTML/CSS
IR → 可视化编辑器
```

---

## 12. 从 IR 到 SVG

每个元素转换成 SVG：

| IR 类型 | SVG 输出 |
|---|---|
| text | `<text>` 或 `<foreignObject>` |
| rectangle | `<rect>` |
| rounded_rect | `<rect rx ry>` |
| circle | `<circle>` |
| ellipse | `<ellipse>` |
| line | `<line>` |
| arrow | `<line marker-end>` |
| icon_svg | `<g transform=...>...</g>` |
| image | `<image>` |
| background | `<rect>` 或 `<image>` |

最终完整 SVG 结构：

```xml
<svg width="1920" height="1080" viewBox="0 0 1920 1080">
  <rect width="1920" height="1080" fill="#FFFFFF"/>

  <g id="background-layer">
    ...
  </g>

  <g id="shape-layer">
    ...
  </g>

  <g id="icon-layer">
    ...
  </g>

  <g id="text-layer">
    ...
  </g>
</svg>
```

为了方便粘贴到 PPT，建议：

1. 每个元素保留 group id；
2. 尽量使用基础 SVG primitive；
3. 文字尽量保留为 `<text>`；
4. 不要过度使用 filter、clipPath、mask；
5. 避免过深嵌套；
6. 尽量不要把整页都变成 path。

---

## 13. 从 SVG 到 PPT 的两条路线

## 13.1 路线 A：生成完整 SVG，让用户插入 PowerPoint

这是最简单的路线：

```text
生成 slide.svg
↓
PowerPoint 插入 SVG
↓
必要时 Convert to Shape
```

优点：

```text
实现简单
视觉保真较好
可以手动插入 PPT
```

缺点：

```text
编辑性不稳定
文字可能不好改
不同 Office 版本表现不同
复杂 SVG 转 shape 可能失败
```

适合作为第一版 demo 输出。

---

## 13.2 路线 B：直接生成 PPTX，推荐作为最终路线

这条更适合你的项目：

```text
IR
↓
PPTX writer
↓
slide_reconstructed.pptx
```

输出时：

| IR 元素 | PPTX 对象 |
|---|---|
| text | textbox |
| rounded_rect | auto shape |
| rectangle | auto shape |
| circle | oval shape |
| line | line |
| arrow | connector / line with arrow |
| icon_svg | SVG image 或转换成 shape |
| illustration | SVG image / PNG fallback |
| photo | picture |
| table | PPT table |
| chart | 图片，后续再重建为 PPT chart |

这比“SVG 插入 PPT”更符合最终目标，因为用户打开 PPT 后能真正编辑主要元素。

---

## 14. 渲染反馈闭环

渲染反馈是系统稳定性的关键。

流程：

```text
IR → render as image
↓
与原始图片比较
↓
得到 error map
↓
定位错误元素
↓
修正 bbox / color / z-index / font size / stroke width
↓
重新渲染
```

可以优化的参数：

```text
元素位置
元素尺寸
颜色
透明度
线宽
圆角半径
字号
层级
```

示例：

```text
如果文字整体偏右 → 调整 text bbox x
如果色块颜色偏浅 → 调整 fill
如果箭头缺失 → 重新检测 line/arrow
如果 icon 相似度低 → 换 OmniSVG 或 StarVector 结果
```

这一步可以让系统从“能跑”变成“效果稳定”。

---

## 15. 推荐实现计划

## Phase 1：MVP 原型

目标：

```text
输入一张简单 PPT 图片
输出一个大致可编辑的 PPTX
```

支持元素：

```text
文本
矩形
圆角矩形
圆
直线
箭头
简单 icon
背景
```

暂不支持或弱支持：

```text
复杂图表
表格
复杂插画
照片
渐变
阴影
动画
```

技术组合：

```text
OCR：PaddleOCR / RapidOCR / GPT-4o OCR
分割：SAM3 / SAM2
SVG 生成：StarVector + OmniSVG
形状拟合：OpenCV
PPT 生成：python-pptx + SVG fallback
```

Phase 1 的重点不是追求完美，而是跑通：

```text
图片 → 元素解析 → IR → SVG → PPTX
```

---

## Phase 2：双模型 SVG 选择器

对 icon / illustration：

```text
crop → StarVector
crop → OmniSVG
crop → VTracer
↓
render all
↓
choose best
```

输出：

```text
局部 SVG
局部 PNG preview
质量分数
```

评价指标：

```text
视觉相似度
边缘相似度
颜色相似度
SVG 复杂度
语法正确性
渲染成功率
```

---

## Phase 3：IR 编辑器和重渲染闭环

可以做一个简单网页：

```text
左边：原图
右边：重建图
下面：元素列表
点击元素：显示 bbox/type/z-index/svg/text
```

这个编辑器有两个价值：

1. 方便人工修正错误；
2. 方便收集训练/评估数据。

---

## Phase 4：PPTX 深度可编辑化

把更多 SVG 元素转为 PPT 原生对象：

```text
rect → PPT rect
ellipse → PPT oval
line → PPT line
path → freeform shape
text → textbox
```

这一阶段最难，但也是最有价值的。

---

## 16. 评估指标设计

### 16.1 视觉还原指标

```text
pixel similarity
SSIM
LPIPS
DINO similarity
CLIP similarity
edge similarity
color histogram similarity
```

### 16.2 元素检测指标

```text
bbox IoU
element count accuracy
type classification accuracy
z-index accuracy
```

### 16.3 OCR 和文本指标

```text
CER / WER
文本框位置误差
字号估计误差
颜色误差
段落聚合准确率
```

### 16.4 可编辑性指标

```text
文本是否可编辑
基础形状是否为 PPT 原生对象
图标是否为 SVG
复杂图像是否合理保留为 image
对象数量是否合理
是否存在大量不可编辑 path
```

可以设计一个综合分数：

```text
Editable Reconstruction Score =
α * Visual Similarity
+ β * Text Editability
+ γ * Shape Editability
+ δ * Element Accuracy
- λ * SVG Complexity
```

---

## 17. 数据集构建建议

建议构建三类数据：

### A. 真实 PPT 渲染数据

```text
原始 PPTX → 渲染成 PNG
```

优点：

- 有真实 PPT 元素作为 ground truth；
- 可以评价元素类型、bbox、文字内容、字体、层级。

---

### B. 模板化合成数据

用脚本生成大量 slide：

```text
随机标题
随机正文
随机卡片
随机 icon
随机箭头
随机配色
随机布局
```

优点：

- 标注天然准确；
- 适合训练 router / layout detector / z-index predictor。

---

### C. AI 生成类 PPT 图片

例如：

```text
GPT 生成类 PPT 图片
DALL·E / Midjourney 生成信息图
Canva 风格图片
```

优点：

- 更贴近你的目标应用；
- 适合做人评和 demo。

缺点：

- 没有天然 ground truth；
- 需要人工评估。

---

## 18. 系统命名建议

不要叫 image2svg，太泛。

可以考虑：

```text
Slide2Edit
Slide2Vector
RasterSlide2PPT
PPT-ReVector
EditableSlide Reconstruction
```

论文/项目标题可以写：

> **Slide2Edit: Layered Editable Vector Reconstruction from Rasterized Presentation Images**

中文标题：

> **面向栅格化演示文稿图像的分层可编辑矢量重建方法**

---

## 19. 最终推荐路线图

```text
输入：PPT 图片

1. 页面理解
   - 检测版面区域、文本区域、图标区域、形状区域

2. 文本恢复
   - OCR 提取文字
   - 聚合成文本框
   - 估计字号、颜色、对齐方式

3. 形状恢复
   - OpenCV 拟合矩形、圆、线、箭头、卡片

4. 复杂元素恢复
   - icon → StarVector / OmniSVG
   - illustration → OmniSVG
   - 复杂失败 → raster fallback

5. 统一 IR
   - 保存 type、bbox、style、z-index、svg/text/image

6. 重渲染校正
   - IR → preview
   - 与原图比较
   - 调整位置、颜色、层级、字号

7. 导出
   - layered SVG
   - PPTX native objects
   - SVG fallback for complex elements
```

---

## 20. 最关键的结论

现在应该做的不是：

```text
一张 PPT 图片 → 一个 SVG 生成模型 → 一张 SVG
```

而是：

```text
一张 PPT 图片 → 元素级理解 → 不同元素用不同方式重建 → 统一 IR → SVG/PPTX 双导出
```

StarVector 和 OmniSVG 在这个系统里非常有用，但它们应该主要负责：

```text
icon、logo、复杂装饰、插画
```

而不是主要负责：

```text
文字、文本框、基础形状、箭头、版面结构
```

这样设计之后，系统才能同时具备：

1. **视觉还原度**；
2. **元素可编辑性**；
3. **PPT 导出可用性**；
4. **后续扩展空间**。

