# Current implementation and technology stack

本文档记录当前代码实际使用的模块、依赖边界和成熟度，避免把规划中的能力写成已经稳定的功能。

## 1. 产品边界

当前输入：PNG、JPG、JPEG、WebP 以及常见截图。

当前输出：

- SVG：结构化场景的主输出。
- PPTX：原生文本框、基础形状和图片，非原生矢量按需渲染回退。
- HTML：原图、重建图和元素信息的交互式审查页面。
- QA artifacts：渲染图、对比图、指标和结构审计。

主要适用对象：科研图、流程图、信息图、架构图、PPT 风格页面。

## 2. 两个运行环境

### Lightweight environment

负责 CLI、场景合并、SVG/PPTX 导出和测试，不直接导入 PyTorch 或 Paddle。

主要依赖：

- Python 3.10+
- Pillow
- VTracer
- CairoSVG（可选 QA）
- python-pptx（可选 PPTX）
- Tkinter（桌面界面，Python 标准库）
- PyInstaller（可选 GUI 打包）
- pytest、Ruff（开发）

### AI environment

通过子进程执行 `src/image2svg/ai/scripts/` 下的桥接脚本，使用 JSON 文件与轻量环境交换结果。

主要依赖：

- PyTorch / torchvision
- Transformers
- NumPy
- OpenCV
- Pillow
- SAM3
- PaddleOCR / PaddlePaddle
- MinerU 及其模型依赖

这种隔离避免核心包被 CUDA、Torch、Paddle 和模型版本锁死。

打包后的界面通过 `IMAGE2SVG_MODEL_ROOT` 或 `--model-root` 定位外部模型目录，因此发行包不依赖源码仓库的相对路径。

## 3. 当前组件

| 组件 | 代码入口 | 职责 | 当前状态 |
|---|---|---|---|
| VTracer | `backends/vtracer.py` | 整图或局部平面图形矢量化 | 稳定 |
| GroundingDINO | `ai/scripts/groundingdino_detect.py` | 面板、卡片、图标和结构检测 | 可用 |
| MinerU | `ai/scripts/mineru_parse.py` | 页面布局、文字块和图片块 | 可用 |
| PaddleOCR | `ai/scripts/ocr_recognize.py` | 独立整图 OCR | 可用 |
| SAM3 | `ai/scripts/sam3_segment.py` | 开放词汇对象分割和裁剪 | 可用 |
| Cleanup | `reconstruct/cleanup.py` | 去重、遮挡清理、文字过滤、层级排序 | 可用 |
| SVG exporter | `svg/builder.py` | Scene IR 到 SVG | 可用 |
| PPTX exporter | `export/pptx.py` | Scene IR 到可编辑 PowerPoint | 可用 |
| HTML reviewer | `export/html.py` | 浏览器审查页面 | 可用 |
| QA | `qa/compare.py` | 渲染和像素级比较 | 可用，但不能替代人工审查 |
| Desktop GUI | `gui.py` | 批量转换、预设选择和运行日志 | 可用 |
| Presets | `presets.py` | 平衡模式和论文复杂图增强模式 | 可用 |

## 4. 模型与工具

当前验证过的本地模型组合：

- MinerU2.5-Pro：页面和内容块分析。
- GroundingDINO：开放词汇结构检测。
- SAM3：对象分割。
- PP-OCRv6：中文和英文文字识别。

## 5. Scene IR

所有后端最终都转换为统一的 `Scene` 和 `SceneElement`：

```text
Scene
  width / height / background
  elements[]
    id
    type
    bbox
    style
    z_index
    text / points / path_d / raw_svg
```

这样 SVG、PPTX 和 HTML 共用同一份结构数据，模型实现不会直接写入主 pipeline。

## 6. 重建策略

- 简单、纯色、低纹理：原生 primitive 或 VTracer。
- 复杂多色 icon、logo、建筑渲染：保留高分辨率局部裁剪。
- 照片、热力图、3D render：保留原始像素。
- 文字：优先使用 OCR 恢复成可编辑文本。

SAM3 图标遮罩会根据内容进行 1–3 像素膨胀与轻微羽化。高填充率矩形对象可以规则化为圆角矩形遮罩，以减少毛刺。

## 7. 当前主要风险

- OCR 字体家族、字距、自动换行和基线只能近似恢复。
- 不同模型对同一区域可能产生重复检测，仍依赖规则去重。
- 复杂对象保真通常意味着保留位图，因此不一定满足纯矢量要求。
- 开放词汇提示词和阈值会显著影响检测覆盖率。
- 当前不恢复箭头和连接关系。
- AI 环境和模型权重尚未形成一键安装包。

## 8. 发布建议

GitHub 源码仓库建议只包含代码、小型可公开样例和文档。模型权重、完整 QA 产物、私有图片以及本地环境路径不应提交。效果展示可以单独放在 `docs/assets/`，较大的 PPTX 或视频建议放到 GitHub Releases。
