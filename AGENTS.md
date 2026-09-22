# AGENTS.md — image2svg project guide

> 目标：将栅格截图重建为可编辑 SVG 和 PowerPoint，而不是把整张原图贴入幻灯片。

## 1. Current product path

```text
CLI / GUI
  -> GroundingDINO: panels, cards and visual objects
  -> MinerU: layout, text blocks and image regions
  -> PaddleOCR: editable text and coordinates
  -> SAM3: photos, logos and complex visual regions
  -> VTracer: simple flat graphics
  -> merge, deduplication, z-order and text fitting
  -> Scene IR
  -> SVG / PPTX / review HTML / QA artifacts
```

当前不恢复箭头和连接关系。复杂照片、点云、热力图和多色图形保留为局部图片；文字与基础图形优先恢复为原生可编辑对象。

## 2. Core architecture

`Scene` 和 `SceneElement` 位于 `core/scene.py`，是所有导出格式共用的中间表示。

- `Scene(width, height, background, elements)`
- `SceneElement(id, type, bbox, style, z_index, text, path_d, points, children, raw_svg)`
- `VectorBackend.reconstruct(image_path) -> VectorResult`

具体模型不得写入主 pipeline。重型依赖必须通过 `src/image2svg/ai/scripts/` 下的独立桥接脚本调用，并使用 JSON 交换结果。

## 3. Relevant source layout

```text
src/image2svg/
  cli.py             CLI and preset parsing
  gui.py             batch desktop UI
  presets.py         balanced and paper presets
  pipeline.py        orchestration and output audit
  analyze/           lightweight bridge callers
  ai/scripts/        scripts executed by the AI environment
  backends/          Scene-producing backend implementations
  core/              Scene IR and shared models
  reconstruct/       text, tracing, element recovery and cleanup
  svg/               SVG building, audit and rendering
  export/            PPTX and HTML export
  qa/                visual comparison
  report/            conversion reports
tests/                unit and integration tests
examples/input/       regression inputs
examples/output/      generated artifacts, ignored by Git
docs/                 architecture, technology stack and showcase
```

## 4. Runtime boundary

The lightweight environment contains Pillow, VTracer, CairoSVG, python-pptx, Tkinter and development tools. The separate AI environment contains PyTorch, Transformers, PaddleOCR, MinerU, GroundingDINO, SAM3, NumPy and OpenCV.

Required configuration:

```powershell
$env:IMAGE2SVG_AI_PYTHON = "C:\path\to\image2svg-ai\python.exe"
$env:IMAGE2SVG_MODEL_ROOT = "C:\path\to\model-folders"
```

The model root may contain `minerU/`, `groundingdino/` and `sam3-agent/checkpoints/sam3.pt`. Model weights must not be committed.

## 5. Supported presets

Balanced mode:

```powershell
image2svg input.png -o output.svg `
  --pptx output.pptx --html output.review.html `
  --preset balanced --qa
```

Paper and complex-figure mode:

```powershell
image2svg paper.png -o paper.svg `
  --pptx paper.pptx --html paper.review.html `
  --preset paper --qa
```

`balanced` combines GroundingDINO, MinerU and PaddleOCR. `paper` additionally uses SAM3 with prompts for photos, diagrams, charts, point clouds and tactile images.

## 6. Bridge protocol

- Each bridge is an independent argparse script with required `--image` and `--output` arguments.
- Heavy libraries are imported only inside the bridge process.
- The bridge writes JSON to `--output` and does not import the image2svg package.
- Lightweight callers use `analyze/external.py::run_bridge`.
- Model paths come from explicit options, model-specific environment variables or `IMAGE2SVG_MODEL_ROOT`.

## 7. Quality rules

- Do not remove existing source modules or change the `VectorBackend` abstraction without an explicit request.
- Avoid full-page raster fallback because it creates misleading visual scores.
- Preserve source coordinates when reconstructing text and objects.
- Add tests for new behavior and keep typing intact.
- Do not add code comments unless requested.
- After code changes, run pytest, Ruff and relevant example conversions, then inspect the QA render or review page.

## 8. Validation

```powershell
python -m pytest -q
ruff check src tests
```

For rendering and export changes, also verify:

- SVG structure and audit results
- PPTX slide count and native object types
- QA render and comparison images
- absence of accidental full-page embedded images

## 9. Known limitations

- OCR font family, spacing, wrapping and baseline are approximate.
- Dense pages can still contain overlapping or clipped text.
- SAM3 prompts and confidence thresholds affect visual-object recall.
- Complex visuals remain local raster crops rather than pure vectors.
- The GUI package does not include model weights or the AI Python environment.
