# AI Reconstruction (SAM3 + PaddleOCR)

This document explains how to run the optional AI backends. They are kept in a
**dedicated conda environment** so the lightweight `image2svg` pipeline never
imports torch or paddle.

```text
image2svg env                     AI env (image2svg-ai)
─────────────                     ─────────────────────
CLI / pipeline / Scene IR         torch + sam3
  │                               paddleocr
  └── bridge subprocess ────────► scripts in image2svg.ai.scripts
        (JSON result)  ◄────────  (JSON written to a temp file)
```

The boundary is a JSON file: the bridge scripts only depend on their own heavy
runtime, and the analyzers never import it.

## 1. Create the AI environment

```bash
conda create -n image2svg-ai python=3.12 -y
conda activate image2svg-ai
```

Install PyTorch (CUDA 12.6 build; use CPU or another CUDA version if needed):

```bash
# Fast mirror if the official CDN is slow:
pip install torch==2.7.0 torchvision==0.22.0 \
  --find-links https://mirror.sjtu.edu.cn/pytorch-wheels/cu126/ \
  -i https://pypi.tuna.tsinghua.edu.cn/simple
```

Install SAM3 (official repository) and OCR:

```bash
git clone https://github.com/facebookresearch/sam3.git
pip install -e ./sam3
pip install paddlepaddle paddleocr
```

> Windows note: Triton has no official wheels. `sam3/model/edt.py` is patched
> with a lightweight fallback because only the video tracker uses the EDT
> kernel; image segmentation does not.

## 2. Point image2svg at the AI environment

```bash
# PowerShell
$env:IMAGE2SVG_AI_PYTHON = "G:\path\to\image2svg-ai\python.exe"

# bash
export IMAGE2SVG_AI_PYTHON=/path/to/image2svg-ai/bin/python
```

SAM3 checkpoint resolution order:

1. `--checkpoint` (bridge flag)
2. `SAM3_CHECKPOINT` environment variable
3. `<workspace>/sam3-agent/checkpoints/sam3.pt`

## 3. Run

SAM3 open-vocabulary segmentation (editable primitives + `image` fallback):

```bash
image2svg input.png -o output.svg \
  --sam3 --prompt rectangle --prompt circle --prompt text \
  --ai-device cuda --ai-background "#FFFFFF" --qa
```

PaddleOCR text reconstruction (editable `<text>`):

```bash
image2svg input.png -o output.svg \
  --ocr --ocr-lang en --ai-device cpu --ai-background "#FFFFFF" --qa
```

Combined (shapes + text merged into one Scene):

```bash
image2svg input.png -o output.svg \
  --sam3 --prompt rectangle --prompt circle \
  --ocr --ai-device cuda --ai-background "#FFFFFF" --qa
```

Use a fine-tuned recognizer (for example the bundled Hungarian PP-OCRv6 model):

```bash
image2svg input.png -o output.svg --ocr \
  --ocr-rec-model-dir /path/to/paddleocr
```

## 4. Router: use-original vs generate

`--ai-refine router` classifies each non-primitive segment:

| Class | When | How |
|---|---|---|
| `primitive` | clean rect / rounded rect / ellipse | fitted SVG primitive |
| `trace` | flat, single-color, larger parts | VTracer on the original crop |
| `generate` | small, multi-color or structurally complex icons | StarVector |

The generative backend is pluggable (any object with `generate(crop, workdir)`);
OmniSVG can be added the same way. If generation fails or produces a raster
embed, the segment automatically falls back to tracing, so output stays vector.

```bash
# Batch-generate all icon crops once, then trace the rest
image2svg input.png -o output.svg \
  --sam3 --prompt icon --prompt "rounded rectangle" \
  --ocr --ai-refine router \
  --ai-device cuda --ocr-device cpu \
  --starvector-python /path/to/image2svg-ai/bin/python --qa
```

### StarVector environment notes

StarVector (`starvector/starvector-1b-im2svg`) in the AI env needs a few
workarounds:

1. Install the `star-vector` package (for the model implementation):
   `git clone https://github.com/joanrod/star-vector && pip install -e ./star-vector --no-deps`
2. `transformers==4.49.0`, `tokenizers==0.21.1`, `omegaconf`, `fairscale`,
   `matplotlib`, `svgpathtools`, `cairosvg`, and `numpy<2` + `scipy==1.11.4`
   (SAM3 requires `numpy<2`).
3. The base LLM config is gated (`bigcode/starcoderbase-1b`). A local
   `starcoder-config/` (GPT-BigCode config + tokenizer copied from the model
   dir) is used via `STARVECTOR_LLM_CONFIG`, and `star-vector` builds the LLM
   from config because the StarVector checkpoint supplies all weights.
4. StarVector is trained on clean icons/logos; crops with panel backgrounds
   produce raster embeds, which the router rejects (falls back to trace).


## 4. Options

| Flag | Meaning |
|---|---|
| `--sam3` | Use SAM3 open-vocabulary segmentation |
| `--prompt TEXT` | SAM3 prompt (repeatable) |
| `--ai-python PATH` | AI environment interpreter |
| `--ai-device cuda\|cpu` | Device for AI backends |
| `--ai-confidence FLOAT` | SAM3 detection confidence |
| `--ai-fallback image\|drop` | Unrecognized segment handling |
| `--ai-refine trace\|geometry\|image` | How non-primitive segments are rebuilt (default `trace`) |
| `--ai-background COLOR` | Scene background fill (auto-detected from the image if omitted) |
| `--ocr` | Use PaddleOCR |
| `--ocr-lang LANG` | PaddleOCR language |
| `--ocr-confidence FLOAT` | OCR confidence floor |
| `--ocr-det-model-dir DIR` | Custom detection model |
| `--ocr-rec-model-dir DIR` | Custom recognition model |

## 5. Known limitations

- The AI environment is created manually (not via a `pip` extra) because the
  dependencies are multi-GB.
- `--ai-fallback image` embeds masked crops as base64 PNG, so the result is no
  longer `--vector-only`. Use `--ai-fallback drop` for strictly vector output.
- Clean primitives (rect / rounded rect / ellipse) are emitted directly; all
  other segments are **locally vectorized with VTracer** (`--ai-refine trace`),
  which preserves icon/arrow detail while keeping each part editable.
- Segmentation coverage is the remaining bottleneck: prompts decide which
  parts are found. Add prompts (e.g. `panel`, `arrow`, `icon`) to cover more.
- Label → primitive mapping currently covers rectangle / square / circle /
  ellipse / triangle / line. Other labels rely on the traced refinement.
- Turing GPUs (e.g. RTX 2080 Ti) run without Flash Attention; bf16 autocast is
  still used and works.
