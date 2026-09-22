#!/usr/bin/env python3
"""Detect objects/panels/icons with GroundingDINO and emit JSON.

Runs inside the AI environment. Output records use the segmentation schema so
the existing reconstruction can consume them.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def _fit_arrow(patch):
    """Fit a line (start/end) to an arrow/connector crop via PCA."""
    import numpy as np

    h, w = patch.shape[:2]
    if h < 3 or w < 3:
        return None
    corners = np.concatenate(
        [
            patch[0:2].reshape(-1, 3),
            patch[-2:].reshape(-1, 3),
            patch[:, 0:2].reshape(-1, 3),
            patch[:, -2:].reshape(-1, 3),
        ]
    )
    background = np.median(corners, axis=0)
    distance = np.linalg.norm(patch - background, axis=2)
    mask = distance > 40
    ys, xs = np.where(mask)
    if xs.size < 8:
        return None
    density = float(mask.mean())
    if density > 0.32:
        return None
    points = np.stack([xs, ys], axis=1).astype("float64")
    centered = points - points.mean(axis=0)
    covariance = np.cov(centered.T)
    if not np.all(np.isfinite(covariance)):
        return None
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    if float(eigenvalues[-1] / max(1e-6, eigenvalues.sum())) < 0.82:
        return None
    direction = eigenvectors[:, -1]
    projection = centered @ direction
    start = points[int(projection.argmin())]
    end = points[int(projection.argmax())]
    length = float(projection.max() - projection.min())
    if length <= 1.0 or length < 0.5 * float((w * w + h * h) ** 0.5):
        return None
    radius = max(3.0, min(length * 0.16, max(w, h) * 0.22))
    start_mass = int(
        (((points[:, 0] - start[0]) ** 2 + (points[:, 1] - start[1]) ** 2) <= radius**2).sum()
    )
    end_mass = int(
        (((points[:, 0] - end[0]) ** 2 + (points[:, 1] - end[1]) ** 2) <= radius**2).sum()
    )
    if start_mass > end_mass:
        start, end = end, start
    thickness = max(1.5, float(mask.sum()) / length * 0.55)
    red, green, blue = (int(channel) for channel in np.median(patch[mask], axis=0))
    return {
        "kind": "arrow",
        "start": [round(float(start[0]), 2), round(float(start[1]), 2)],
        "end": [round(float(end[0]), 2), round(float(end[1]), 2)],
        "stroke": f"#{red:02X}{green:02X}{blue:02X}",
        "stroke_width": round(thickness, 2),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="GroundingDINO detector bridge")
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--label", action="append", default=[])
    parser.add_argument("--model", default=None)
    parser.add_argument("--box-threshold", type=float, default=0.3)
    parser.add_argument("--text-threshold", type=float, default=0.25)
    parser.add_argument("--crop-dir", type=Path, default=None)
    args = parser.parse_args()

    import torch
    from PIL import Image
    from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor

    model_dir = args.model
    if model_dir is None:
        model_root = Path(
            os.environ.get("IMAGE2SVG_MODEL_ROOT") or Path(__file__).resolve().parents[5]
        )
        fallback = model_root / "groundingdino"
        model_dir = str(fallback) if fallback.exists() else "IDEA-Research/grounding-dino-base"
    if not args.label:
        args.label = ["panel", "card", "icon", "arrow", "text"]

    device = "cuda" if torch.cuda.is_available() else "cpu"
    processor = AutoProcessor.from_pretrained(model_dir)
    model = AutoModelForZeroShotObjectDetection.from_pretrained(model_dir).to(device)
    model.eval()

    image = Image.open(args.image).convert("RGB")
    width, height = image.size
    text = " . ".join(label.lower() for label in args.label) + " ."

    inputs = processor(images=image, text=text, return_tensors="pt").to(device)
    with torch.no_grad():
        outputs = model(**inputs)
    try:
        results = processor.post_process_grounded_object_detection(
            outputs,
            inputs.input_ids,
            threshold=args.box_threshold,
            text_threshold=args.text_threshold,
            target_sizes=[(height, width)],
        )[0]
    except TypeError:  # transformers < 5 used box_threshold
        results = processor.post_process_grounded_object_detection(
            outputs,
            inputs.input_ids,
            box_threshold=args.box_threshold,
            text_threshold=args.text_threshold,
            target_sizes=[(height, width)],
        )[0]

    if args.crop_dir is not None:
        args.crop_dir.mkdir(parents=True, exist_ok=True)

    import numpy as np

    pixels = np.asarray(image, dtype=np.float32)

    def dominant(region: np.ndarray) -> str:
        flat = region.reshape(-1, 3)
        quant = (flat // 16).astype(np.int32)
        values, counts = np.unique(quant, axis=0, return_counts=True)
        chosen = values[counts.argmax()]
        mask = np.all(quant == chosen, axis=1)
        red, green, blue = (int(channel) for channel in flat[mask].mean(axis=0))
        return f"#{red:02X}{green:02X}{blue:02X}"

    instances = []
    for index, (box, score, label) in enumerate(
        zip(results["boxes"], results["scores"], results["labels"])
    ):
        x0, y0, x1, y1 = (float(value) for value in box.tolist())
        ix0, iy0 = max(0, int(x0)), max(0, int(y0))
        ix1, iy1 = min(width, int(x1)), min(height, int(y1))
        if ix1 <= ix0 or iy1 <= iy0:
            continue
        patch = pixels[iy0:iy1, ix0:ix1]
        ph, pw = patch.shape[:2]
        interior = patch[
            int(ph * 0.15) : max(int(ph * 0.85), int(ph * 0.15) + 1),
            int(pw * 0.15) : max(int(pw * 0.85), int(pw * 0.15) + 1),
        ]
        fill = dominant(interior)
        quant_all = (patch.reshape(-1, 3) // 32).astype(np.int32)
        ncolors = int(np.unique(quant_all, axis=0).shape[0])
        ring = 3
        border_parts = []
        if patch.shape[0] > 2 * ring and patch.shape[1] > 2 * ring:
            border_parts = [
                patch[:ring].reshape(-1, 3),
                patch[-ring:].reshape(-1, 3),
                patch[:, :ring].reshape(-1, 3),
                patch[:, -ring:].reshape(-1, 3),
            ]
        stroke = dominant(np.concatenate(border_parts, axis=0)) if border_parts else fill
        record = {
            "label": str(label).lower(),
            "score": round(float(score), 4),
            "box": [x0, y0, x1, y1],
            "area": int((ix1 - ix0) * (iy1 - iy0)),
            "color": fill,
            "stroke": stroke,
            "stats": {"colors": ncolors, "vertices": 4, "solidity": 1.0},
            "source": "groundingdino",
        }

        if set(record["label"].split()) & {"arrow", "arrows", "line", "connector", "link"}:
            arrow = _fit_arrow(patch)
            if arrow is not None:
                record["geometry"] = arrow
        if args.crop_dir is not None:
            crop_path = args.crop_dir / f"{label}_{index:03d}.png"
            image.crop((ix0, iy0, ix1, iy1)).save(crop_path)
            record["crop_path"] = str(crop_path)
            record["crop_box"] = [float(ix0), float(iy0), float(ix1), float(iy1)]
        instances.append(record)

    payload = {
        "image": str(args.image),
        "width": width,
        "height": height,
        "labels": args.label,
        "instances": instances,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"groundingdino: wrote {len(instances)} instances to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
