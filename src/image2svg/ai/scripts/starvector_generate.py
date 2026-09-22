"""Generate SVG for one or more cropped regions with StarVector and emit JSON.

Runs inside the StarVector environment (transformers + torch). Loading the
model is expensive, so this bridge accepts several ``--image`` crops and
generates for all of them in a single process.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

_MODEL_ENV = "STARVECTOR_MODEL"
_LLM_CONFIG_ENV = "STARVECTOR_LLM_CONFIG"
_REPO_ROOT = Path(
    os.environ.get("IMAGE2SVG_MODEL_ROOT") or Path(__file__).resolve().parents[5]
)


def _resolve_env_path(explicit: str | None, env_name: str, sibling: str) -> str | None:
    if explicit:
        return explicit
    env = os.environ.get(env_name)
    if env and Path(env).exists():
        return env
    fallback = _REPO_ROOT / sibling
    if fallback.exists():
        return str(fallback)
    return None


def _isolate(image_path: Path, margin_ratio: float = 0.08):
    """Load a crop, composite alpha on white and add a margin."""
    from PIL import Image

    image = Image.open(image_path)
    if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.split()[-1])
        image = background
    else:
        image = image.convert("RGB")

    width, height = image.size
    margin = max(2, int(max(width, height) * margin_ratio))
    canvas = Image.new("RGB", (width + 2 * margin, height + 2 * margin), (255, 255, 255))
    canvas.paste(image, (margin, margin))
    return canvas


def main() -> int:
    parser = argparse.ArgumentParser(description="StarVector image-to-SVG bridge")
    parser.add_argument("--image", action="append", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--model", default=None)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--max-length", type=int, default=4000)
    args = parser.parse_args()

    llm_config = _resolve_env_path(None, _LLM_CONFIG_ENV, "starcoder-config")
    if llm_config:
        os.environ[_LLM_CONFIG_ENV] = llm_config

    import torch
    from transformers import AutoModelForCausalLM

    device = args.device
    if device == "cuda" and not torch.cuda.is_available():
        device = "cpu"

    model_path = _resolve_env_path(args.model, _MODEL_ENV, "starvector-1b-im2svg")
    model = AutoModelForCausalLM.from_pretrained(
        model_path,
        torch_dtype=torch.float16 if device == "cuda" else torch.float32,
        trust_remote_code=True,
    )
    model.to(device)
    model.eval()

    processor = model.model.processor
    results = []
    for image_path in args.image:
        pixel_values = processor(_isolate(image_path), return_tensors="pt")["pixel_values"]
        if pixel_values.dim() == 3:
            pixel_values = pixel_values.unsqueeze(0)
        pixel_values = pixel_values.to(device)
        svg = model.generate_im2svg({"image": pixel_values}, max_length=args.max_length)[0]
        results.append({"image": str(image_path), "svg": svg})

    payload = {"model": model_path, "results": results}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"starvector: wrote {len(results)} SVGs to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
