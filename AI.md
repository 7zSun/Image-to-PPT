# AI runtime

image2svg 将轻量转换程序与模型运行时分开安装。

```text
lightweight environment                 AI environment
CLI / GUI / Scene IR / export           Torch / Paddle / OpenCV / models
              |                                      |
              +---------- JSON subprocess -----------+
```

轻量环境不会直接导入 Torch、Paddle、SAM3 或 MinerU。`src/image2svg/ai/scripts/` 中的桥接脚本在独立 Python 环境执行，并将结果写为 JSON。

## 1. 核心环境

```bash
pip install -e ".[qa,pptx,dev]"
```

核心环境包含 Pillow、VTracer，以及可选的 CairoSVG、python-pptx、pytest 和 Ruff。桌面界面使用 Python 自带的 Tkinter。

## 2. AI 环境

建议单独创建环境：

```bash
conda create -n image2svg-ai python=3.12 -y
conda activate image2svg-ai
```

当前转换链路使用：

- PyTorch、torchvision、Transformers
- NumPy、OpenCV、Pillow
- PaddlePaddle、PaddleOCR
- GroundingDINO
- MinerU 及对应模型
- SAM3 官方代码和 checkpoint

CUDA、PyTorch 和 PaddlePaddle 的安装方式取决于显卡、驱动和操作系统，请使用各项目官方提供的兼容版本。

## 3. 连接两个环境

PowerShell：

```powershell
$env:IMAGE2SVG_AI_PYTHON = "C:\path\to\image2svg-ai\python.exe"
$env:IMAGE2SVG_MODEL_ROOT = "C:\path\to\model-folders"
```

bash：

```bash
export IMAGE2SVG_AI_PYTHON=/path/to/image2svg-ai/bin/python
export IMAGE2SVG_MODEL_ROOT=/path/to/model-folders
```

模型根目录按需包含：

```text
model-folders/
  minerU/
  groundingdino/
  sam3-agent/checkpoints/sam3.pt
```

也可以分别设置 `MINERU_MODEL` 与 `SAM3_CHECKPOINT`。模型权重不包含在源码仓库或 GUI 发行包中。

## 4. 推荐调用

常规流程图和信息图：

```bash
image2svg input.png -o output.svg \
  --pptx output.pptx \
  --html output.review.html \
  --preset balanced \
  --qa
```

论文截图、点云、触觉图和复杂多面板图片：

```bash
image2svg paper.png -o paper.svg \
  --pptx paper.pptx \
  --html paper.review.html \
  --preset paper \
  --qa
```

`paper` 预设使用 SAM3 定位复杂视觉区域，并以局部原图方式保留照片、点云和科研子图。当前两个预设都不重建箭头。

## 5. 当前模型职责

| Model | Role |
|---|---|
| GroundingDINO | 面板、卡片、容器和视觉对象检测 |
| MinerU | 页面布局、文本块和图片块分析 |
| PaddleOCR / PP-OCRv6 | 可编辑文字及坐标恢复 |
| SAM3 | 照片、logo 和复杂视觉区域分割 |

## 6. 已知限制

- 模型权重需要用户自行下载，并遵守各自许可证。
- SAM3 的提示词和阈值会影响召回率与重复检测。
- OCR 能恢复文字内容，但字体、字距、换行和基线仍是近似值。
- 照片、点云和复杂纹理会保留为局部位图，不等同于纯矢量输出。
- 当前不恢复箭头和连接关系。
- Windows 上的 QA 渲染需要 Cairo；GUI 打包脚本可以将 Cairo DLL 一并加入发行目录。
