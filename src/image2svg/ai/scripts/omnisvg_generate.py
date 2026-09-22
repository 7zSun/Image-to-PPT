#!/usr/bin/env python3
"""Generate SVG for crops with OmniSVG and emit JSON.

Wraps the official OmniSVG repository (Qwen2.5-VL based generator). The repo's
``inference.py`` is imported and reused, loading the model once for all crops.
Runs inside the AI environment.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

_REPO_ENV = "OMNISVG_REPO"
_WEIGHTS_ENV = "OMNISVG_WEIGHTS"
_REPO_ROOT = Path(
    os.environ.get("IMAGE2SVG_MODEL_ROOT") or Path(__file__).resolve().parents[5]
)


def _resolve_dir(explicit: str | None, env_name: str, sibling: str) -> str | None:
    if explicit:
        return explicit
    env = os.environ.get(env_name)
    if env and Path(env).exists():
        return env
    fallback = _REPO_ROOT / sibling
    if fallback.exists():
        return str(fallback)
    return None


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    parser = argparse.ArgumentParser(description="OmniSVG image-to-SVG bridge")
    parser.add_argument("--image", action="append", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--repo", default=None)
    parser.add_argument("--weights", default=None)
    parser.add_argument("--model-size", default="4B")
    parser.add_argument("--max-length", type=int, default=1024)
    parser.add_argument("--num-candidates", type=int, default=1)
    args = parser.parse_args()

    repo = _resolve_dir(args.repo, _REPO_ENV, "OmniSVG")
    weights = _resolve_dir(args.weights, _WEIGHTS_ENV, "omini4b")
    if repo is None or weights is None:
        raise SystemExit("OmniSVG repo/weights not found. Set OMNISVG_REPO and OMNISVG_WEIGHTS.")

    os.chdir(repo)
    sys.path.insert(0, repo)

    import inference as omni
    from PIL import Image

    # One candidate avoids OmniSVG's default extra-candidate buffer (much faster).
    omni.EXTRA_CANDIDATES_BUFFER = 0
    omni.load_models(args.model_size, weight_path=weights, model_path=weights)

    results = []
    for image_path in args.image:
        image = Image.open(image_path)
        processed, _ = omni.preprocess_image_for_svg(
            image,
            replace_background=True,
            target_size=omni.TARGET_IMAGE_SIZE,
        )
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as handle:
            processed.save(handle.name, format="PNG")
            tmp_path = handle.name
        try:
            inputs = omni.prepare_inputs("image-to-svg", tmp_path)
            candidates = omni.generate_candidates(
                inputs,
                "image-to-svg",
                "image",
                omni.TASK_CONFIGS["image-to-svg"]["default_temperature"],
                omni.TASK_CONFIGS["image-to-svg"]["default_top_p"],
                omni.TASK_CONFIGS["image-to-svg"]["default_top_k"],
                omni.TASK_CONFIGS["image-to-svg"]["default_repetition_penalty"],
                args.max_length,
                args.num_candidates,
            )
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

        svg = candidates[0]["svg"] if candidates else ""
        results.append({"image": str(image_path), "svg": svg})

    payload = {"model": weights, "results": results}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"omnisvg: wrote {len(results)} SVGs to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
