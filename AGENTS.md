# AGENTS.md — image2svg 项目交接与开发指南

> 本文件面向接手的 AI 智能体（或开发者）。请先通读再动手。
> 目标：图片 → 可编辑 SVG/PPTX（真正可编辑的元素，而不是贴图）。

## 1. 项目一句话

把栅格图片（截图/示意图/框架图）自动解析成**可编辑元素**：文字 `<text>`、框 `<rect>`、箭头 `<line>`、照片/渲染保留为 `<image>`，并支持导出 PPTX 与交互式审查 HTML。

## 2. 核心架构与数据流

```
CLI (src/image2svg/cli.py)
  └─ Image2SvgPipeline (pipeline.py)
       ├─ CompositeBackend（多个后端顺序执行，各自返回 Scene IR）
       │    ├─ PanelBackend       --ai-panels   确定性平色条块/胶囊 + Hough箭头兜底
       │    ├─ DetectorBackend    --detect      GroundingDINO：面板/框 → rect；箭头 PCA → line；图标 → VTracer
       │    │        （第二个实例：arrow-only labels，低阈值，只出箭头）
       │    ├─ LayoutBackend      --mineru      MinerU2.5-Pro 版面解析：文字/图块分离 + 递归再分割大图块
       │    └─ OcrBackend         --ocr         整图 PaddleOCR（现在基本被 --mineru-ocr 替代）
       ├─ 合并 + 清理（reconstruct/cleanup.py, arrows.py）
       │    deduplicate_scene（跨类别同位置只留一个）
       │    connect_arrows（箭头吸附/去重，当前 max_snap=0 即不吸附）
       │    drop_duplicate_text / filter_artifact_text
       │    assign_z_order（背景 < rect < image < 矢量化组 < 箭头 < 文字；同层大块在下）
       └─ Scene IR (core/scene.py) → build_svg (svg/builder.py)
            → audit_svg (svg/audit.py) → 写 SVG
            → QA：CairoSVG 渲染 + Pillow 对比（qa/compare.py）
            → 报告 report/、导出 export/pptx.py、export/html.py
```

**Scene IR**（`core/scene.py`）是核心中间表示：
- `Scene(width, height, background, elements)`
- `SceneElement(id, type, bbox=(x,y,w,h), style, z_index, text, path_d, points, children, raw_svg)`
- `raw_svg`：预生成矢量标记（如局部 VTracer 路径、箭头 `<line>`+`<polygon>`），由 builder 包进 `<g transform>`。

**后端抽象**（`backends/base.py`）：`VectorBackend.reconstruct(image_path) -> VectorResult(svg?, scene?)`。
**不得把任何具体模型写死进 pipeline**；重依赖一律通过**子进程桥接**调用（见 §6）。

## 3. 目录结构

```
image2svg/
├── src/image2svg/
│   ├── cli.py  pipeline.py
│   ├── core/       models.py（VectorResult/AuditResult/PipelineResult） scene.py（Scene/SceneElement/merge_scenes）
│   ├── backends/   base.py vtracer.py sam3.py ocr.py detector.py layout.py panels.py composite.py
│   ├── analyze/    models.py external.py(run_bridge) sam3.py ocr.py starvector.py omnisvg.py detector.py layout.py regions.py
│   ├── reconstruct/ segments.py text.py trace.py generate.py router.py arrows.py cleanup.py
│   ├── ai/scripts/ （全部是"AI 环境内运行"的桥接脚本，绝不 import image2svg）
│   │    mineru_parse.py  groundingdino_detect.py  flat_regions.py
│   │    ocr_recognize.py  sam3_segment.py  starvector_generate.py  omnisvg_generate.py
│   ├── svg/       audit.py builder.py render.py
│   ├── qa/        compare.py
│   ├── report/    report.py（conversion_report.json）
│   └── export/    pptx.py html.py
├── tests/         （42 个测试，pytest）
├── examples/
│   ├── input/     demo.png figure.png fig2_*.png 183544.png 0.png 5.png …
│   └── output/    （每次全量检测所有 input，产物 .svg/.pptx/.review.html/.qa/）
├── pyproject.toml（extras: qa= CairoSVG, pptx= python-pptx, dev= pytest+ruff）
├── AI.md  README.md  DEVELOPMENT.md
```

## 4. 环境（Windows 本机，重要！）

- 项目运行环境 `image2svg`（轻量，Pillow/vtracer/python-pptx/CairoSVG）：
  `G:\SQZ\demo\demo1\image2svg\python.exe`
- AI 环境 `image2svg-ai`（torch 2.7+cu126、transformers 5.17、MinerU、PaddleOCR、GroundingDINO、SAM3）：
  `G:\SQZ\demo\demo1\image2svg-ai\python.exe`
- StarVector 环境 `image2svg-svg`（transformers 4.49 + star-vector）：
  `G:\SQZ\demo\demo1\image2svg-svg\python.exe`

环境变量（桥接子进程会用）：
- `IMAGE2SVG_AI_PYTHON` → AI 环境 python（MinerU/DINO/SAM3/OCR）
- `IMAGE2SVG_STARVECTOR_PYTHON` → StarVector 环境 python
- `IMAGE2SVG_OMNISVG_PYTHON` → OmniSVG（本机用不了，见 §7）
- `SAM3_CHECKPOINT`、`STARVECTOR_LLM_CONFIG`、`MINERU_MODEL`、`OMNISVG_REPO`、`OMNISVG_WEIGHTS`（桥接脚本有默认回退到 E:\llama\PNG 下的兄弟目录）

**Cairo DLL**：Windows 上 CairoSVG 需要原生 cairo，本机从
`D:\BaiduNetdisk\module\ImageViewer\libcairo-2.dll` 借的。渲染/QA/PPTX 之前必须：
```powershell
$env:PATH = "D:\BaiduNetdisk\module\ImageViewer;" + $env:PATH
```

模型位置（`E:\llama\PNG\`，项目外的兄弟目录）：
- `minerU/`（MinerU2.5-Pro-2605-1.2B，Qwen2-VL）✅ 在用
- `groundingdino/`（grounding-dino-base，含权重）✅ 在用
- `sam3-agent/checkpoints/sam3.pt` + `sam3/`（官方 facebookresearch/sam3 克隆；本机改过 `edt.py`(triton stub)、`position_encoding.py`/`decoder.py`(CPU device)）🟡 仅 --sam3
- `starvector-1b-im2svg/` + `star-vector/`（改过 `llm/starcoder.py`：从 config 建 GPTBigCode，避免下载 gated 基座）+ `starcoder-config/`（本地 GPTBigCode config+tokenizer）🟡 未接入默认管线
- `omini4b/`（OmniSVG1.1-4B 权重）+ `OmniSVG/`（官方仓库）+ `qwen2.53b/`（Qwen2.5-VL-3B 基座）🔴 OmniSVG 需要 16GB 显存，本机 2080 Ti 11GB 跑不动
- `paddleocr/`（PP-OCRv6 匈牙利语 rec 模型，自定义，`--ocr-rec-model-dir` 可用）

## 5. 当前“最佳命令”与全量检测约定

**约定：每次优化后必须对 `examples/input/` 下所有图片全量检测。**

```powershell
$env:IMAGE2SVG_AI_PYTHON = "G:\SQZ\demo\demo1\image2svg-ai\python.exe"
$env:PATH = "D:\BaiduNetdisk\module\ImageViewer;" + $env:PATH
image2svg examples/input/0.png -o examples/output/0.svg `
  --pptx examples/output/0.pptx --html examples/output/0.review.html `
  --ai-panels --detect --mineru --mineru-ocr `
  --ai-background "#FFFFFF" --ai-device cuda --qa
```

常用 flag 一览：`--ai-panels`（平色/Hough）、`--detect`（DINO 结构+箭头）、`--mineru`（版面）、`--mineru-ocr`（图块内文字）、`--sam3` + `--prompt`、`--ai-refine {router|trace|generate|geometry|image|raster|vector}`、`--ai-generator {starvector|omnisvg|none}`、`--no-images`（纯矢量）、`--keep-baked-text`、`--pptx`、`--html`。

## 6. 桥接协议（新增模型照抄这个模式）

- 桥接脚本在 `src/image2svg/ai/scripts/*.py`，用 argparse，`--image/--output` 必填，**输出 JSON 到 --output**，只 import 重型库。
- 调用方 `analyze/*.py` 用 `run_bridge(python, script, args, output_path)`（`analyze/external.py`），子进程用 `encoding="utf-8", errors="replace"`。
- 解析产物统一为 `analyze/models.py` 的 `SegmentationResult/SegmentInstance(stats/geometry/crop_path…)` 或 `LayoutResult/LayoutBlock`。
- 桥接默认模型路径用 `Path(__file__).resolve().parents[5]`（= E:\llama\PNG）+ 兄弟目录名回退，也可用环境变量覆盖。

## 7. 已知状态与坑（接手必读）

**效果好的**：
- MinerU 文字/图块分离（含 0.png 左侧“超大 image 块递归再分割”，见 `mineru_parse.py` 的 deep pass）。
- DINO 结构框 + PCA 箭头 + Hough 箭头兜底（后者误检已收紧：minLen 36 + 细笔画校验 + 共线合并）。
- 跨类别去重 + z-order（大块在下、小块在上）+ PPTX/HTML 导出。

**还没解决的**：
1. **小 logo 未生成**：StarVector 环境就绪但未接入 MinerU 的“小图标块”；`reconstruct/generate.py` + `analyze/starvector.py` 已备好（`generate_batch`），接法参考 `backends/sam3.py::_batch_generator`。
2. **箭头**：仍有少量误检/漏检；`reconstruct/arrows.py::connect_arrows` 的吸附默认关（曾导致箭头塌缩）。用户原话：“只需要判断连接关系”——理想做法：箭头两端吸附到最近的框边界并去掉误检。
3. **框内文字可编辑 vs 保真的取舍**：纹理强(photo)的区域保留 image（标签文字烘焙不可编辑）；平色区域转 rect+text。用户希望“图标里带文字的也可编辑”。
4. **文字四要素**：位置/颜色/字号/字重已做，字体族只有默认 sans，对齐(居中/左)未做。
5. **OmniSVG 用不了**（16GB 显存）；Qwen2.5-VL-3B 目前闲置。
6. **重复标签**：偶发（如 “Point Embeddings” 两行），`drop_duplicate_text` 已做同文本+重叠/近邻去重，仍有漏网。

**质量红线（遵守）**：
- 不删除已有模块；不改 `VectorBackend` 抽象；不把具体模型写进 pipeline。
- 所有新功能配测试（pytest）；`ruff check src tests` 必须全绿；保持 Python typing；**不要添加代码注释**（除非用户要求）。
- 每次改动后：`pytest` + `ruff` + 对 examples/input 全量重跑 + 打开 `.review.html` 自查。

## 8. 验证命令

```powershell
& "G:\SQZ\demo\demo1\image2svg\python.exe" -m pytest -q
& "G:\SQZ\demo\demo1\image2svg\Scripts\ruff.exe" check src tests
```

## 9. 成果历史（供对比参考，均在 examples/output/）

| 输入 | 当前 similarity | 元素构成（约） |
|---|---|---|
| figure.png | 0.994 | 19 rect + 10 箭头 + 1 image |
| 183544.png | 0.98 | 13 rect + 15 image + 38 箭头 |
| fig2_*_detailed.png | 0.953 | 14 rect + 23 text + 11 image + 31 箭头 |
| 0.png | 0.913 | 8 rect + 47 text + 21 image + 27 箭头（左侧递归分割后，文字可编辑优先） |
| 5.png | 0.989 | 7 rect + 1 text + 1 image + 46 箭头 |
| demo.png | 0.963 | 简单几何 |
