# image2svg

## 项目简介

`image2svg` 是一个面向 **图片到可编辑矢量内容转换** 的探索项目。

当前项目定位已经从简单的 raster image → SVG 转换，逐步扩展为：

> **PPT / AI 生成图片 → 分层可编辑 SVG → 可编辑 PPT 重建系统**

核心目标不是生成一张视觉相似的 SVG，而是理解图片中的语义元素，并恢复为可编辑对象。

---

## 当前已实现 / 已规划方向

当前仓库主要完成了方案设计和技术路线规划，核心实现方向包括：

### 1. 类 PPT 图像解析

目标输入：

- PPT 截图
- AI 生成的 slide 图片
- 信息图
- 流程图
- 海报式页面

计划将整张图片拆解为：

```
Image
 ↓
Layout understanding
 ↓
Element detection
 ↓
Element reconstruction
 ↓
Layered SVG / PPTX
```

---

### 2. 元素级重建策略

不同视觉元素采用不同恢复方式：

| 元素 | 重建方式 |
| --- | --- |
| 文字 | OCR + 文本框恢复 |
| 矩形/圆角矩形 | 几何拟合 |
| 圆/线/箭头 | 基础图形恢复 |
| Icon | SVG 生成模型辅助 |
| 插画 | 局部 SVG 生成 |
| 图片 | 保留 raster image |

核心思想：

> 不直接把整张图片转换成 path，而是恢复图片背后的可编辑结构。

---

## 当前方案文档

详细技术路线见：

- `Slide2Edit_image_to_editable_ppt_plan.md`

其中包含：

- 分层 SVG 重建方案
- OCR 文本恢复
- 元素分类 Router
- SVG / PPTX 输出设计
- StarVector、OmniSVG 等模型的使用策略

---

## 系统目标架构

最终希望实现：

```
Input Image
    |
    v
Layout Analysis
    |
    +---- OCR
    |
    +---- Shape Detection
    |
    +---- Semantic Segmentation
    |
    v
Element Reconstruction Router
    |
    +---- Text Object
    +---- Shape Object
    +---- SVG Object
    +---- Image Object
    |
    v
Unified Intermediate Representation
    |
    +---- SVG
    +---- PPTX
```

---

## 当前状态

目前项目处于 **方案验证阶段**：

- [x] 完成整体架构设计
- [x] 明确图片 → 元素 → 可编辑对象的技术路线
- [x] 设计 SVG / PPTX 重建方向
- [ ] 完成自动化版面分析
- [ ] 完成 OCR + 文本框恢复
- [ ] 完成元素级 SVG 重建
- [ ] 完成 PPTX 导出

---

## 后续计划

### Phase 1：基础可编辑 SVG

实现：

- OCR 文本恢复
- 基础 shape 检测
- 分层 SVG 输出

### Phase 2：智能元素重建

加入：

- VLM 页面理解
- 元素分类 Router
- 局部 SVG 生成模型

### Phase 3：PPT 原生重建

实现：

- PPT textbox
- PPT shape
- PPT connector
- SVG icon 插入

最终目标：

> 将一张不可编辑的图片恢复成用户可以继续修改的 PPT 文件。

---

## License

Research prototype.
