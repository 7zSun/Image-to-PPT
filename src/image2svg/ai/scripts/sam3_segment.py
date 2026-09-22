"""Run SAM3 open-vocabulary segmentation and emit a JSON instance list.

This script is executed inside the dedicated AI environment (torch + sam3).
It deliberately does not import the ``image2svg`` package so that the heavy
runtime stays isolated from the lightweight conversion pipeline.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from contextlib import nullcontext
from pathlib import Path
from typing import Any

_CHECKPOINT_ENV = "SAM3_CHECKPOINT"


def _resolve_checkpoint(explicit: str | None) -> str:
    if explicit:
        return explicit
    env = os.environ.get(_CHECKPOINT_ENV)
    if env and Path(env).exists():
        return env
    model_root = Path(
        os.environ.get("IMAGE2SVG_MODEL_ROOT") or Path(__file__).resolve().parents[5]
    )
    fallback = model_root / "sam3-agent" / "checkpoints" / "sam3.pt"
    if fallback.exists():
        return str(fallback)
    return ""


def _box_to_list(box: Any) -> list[float]:
    return [round(float(value), 3) for value in box.tolist()]


def _mean_color(image: Any, mask: Any) -> str | None:
    import cv2
    import numpy as np

    pixels = np.asarray(image.convert("RGB"), dtype="float32")
    kernel = np.ones((5, 5), np.uint8)
    interior = cv2.erode(mask.astype(np.uint8), kernel, iterations=1).astype(bool)
    selected = pixels[interior if interior.sum() >= 20 else mask]
    if selected.size == 0:
        return None
    # Median is robust against stray border/text pixels inside the mask.
    median = np.median(selected, axis=0)
    red, green, blue = (int(channel) for channel in median)
    return f"#{red:02X}{green:02X}{blue:02X}"


def _background_color(image: Any) -> str:
    import numpy as np

    array = np.asarray(image.convert("RGB"), dtype=np.uint8)
    band = 8
    border = np.concatenate(
        [
            array[:band].reshape(-1, 3),
            array[-band:].reshape(-1, 3),
            array[:, :band].reshape(-1, 3),
            array[:, -band:].reshape(-1, 3),
        ]
    )
    values, counts = np.unique(border, axis=0, return_counts=True)
    color = values[counts.argmax()]
    red, green, blue = (int(channel) for channel in color)
    return f"#{red:02X}{green:02X}{blue:02X}"


def _fit_geometry(mask: Any) -> dict[str, Any] | None:
    """Fit an editable primitive (rect / rounded rect / ellipse / polygon) to a mask."""
    import cv2
    import numpy as np

    canvas = mask.astype(np.uint8) * 255
    contours, _ = cv2.findContours(canvas, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    contour = max(contours, key=cv2.contourArea)
    area = float(cv2.contourArea(contour))
    if area < 40:
        return None
    x, y, w, h = cv2.boundingRect(contour)
    if w <= 0 or h <= 0:
        return None

    extent = area / float(w * h)
    perimeter = cv2.arcLength(contour, True)
    approx = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
    vertices = len(approx)

    ellipse_fill = 0.0
    axis_ratio = 1.0
    if len(contour) >= 5:
        (cx, cy), (d1, d2), _angle = cv2.fitEllipse(contour)
        ellipse_area = math.pi * (d1 / 2.0) * (d2 / 2.0)
        ellipse_fill = area / max(1.0, ellipse_area)
        axis_ratio = min(d1, d2) / max(d1, d2) if max(d1, d2) > 0 else 0.0

    geometry: dict[str, Any] = {"bbox": [float(x), float(y), float(x + w), float(y + h)]}

    if extent >= 0.95 and vertices == 4:
        geometry["kind"] = "rect"
    elif extent >= 0.85 and vertices <= 16:
        geometry["kind"] = "rounded_rect"
        rows = np.where(mask)[0]
        top = mask[int(rows.min())]
        run = np.where(top)[0]
        flat = float(run.max() - run.min() + 1) if run.size else float(w)
        geometry["radius"] = round(max(0.0, (w - flat) / 2.0), 2)
    elif ellipse_fill >= 0.90 and axis_ratio >= 0.4 and vertices > 8:
        geometry["kind"] = "ellipse"
        geometry["bbox"] = [
            float(cx - d1 / 2.0),
            float(cy - d2 / 2.0),
            float(cx + d1 / 2.0),
            float(cy + d2 / 2.0),
        ]
    else:
        if vertices > 40:
            approx = cv2.approxPolyDP(contour, 0.01 * perimeter, True)
        geometry["kind"] = "polygon"
        geometry["points"] = [
            [round(float(px), 2), round(float(py), 2)]
            for px, py in approx.reshape(-1, 2)
        ]
    return geometry


def _mask_stats(image: Any, mask: Any, geometry: dict[str, Any] | None) -> dict[str, Any]:
    """Cheap complexity signals used by the reconstruction router."""
    import cv2
    import numpy as np

    pixels = np.asarray(image.convert("RGB"), dtype=np.uint8)[mask]
    if pixels.size:
        quantized = (pixels // 32).astype(np.int32).reshape(-1, 3)
        colors = int(np.unique(quantized, axis=0).shape[0])
    else:
        colors = 0

    solidity = 1.0
    contour = None
    contours, _ = cv2.findContours(
        mask.astype(np.uint8) * 255, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    if contours:
        contour = max(contours, key=cv2.contourArea)
        area = float(cv2.contourArea(contour))
        hull_area = float(cv2.contourArea(cv2.convexHull(contour)))
        if hull_area > 0:
            solidity = area / hull_area

    if geometry and geometry.get("kind") == "polygon":
        vertices = len(geometry.get("points", []))
    elif contour is not None:
        perimeter = cv2.arcLength(contour, True)
        vertices = len(cv2.approxPolyDP(contour, 0.02 * perimeter, True))
    else:
        vertices = 4

    return {
        "colors": colors,
        "vertices": int(vertices),
        "solidity": round(float(solidity), 3),
    }


def _presentation_mask(
    alpha: Any,
    label: str,
    geometry: dict[str, Any] | None,
) -> tuple[Any, str]:
    from PIL import Image, ImageDraw, ImageFilter

    semantic = label.strip().lower()
    smooth_labels = {"icon", "logo", "symbol", "document", "robot", "building"}
    if not any(token in semantic for token in smooth_labels):
        return alpha, "mask"
    bbox = alpha.getbbox()
    if bbox is None:
        return alpha, "mask"
    x0, y0, x1, y1 = bbox
    width = max(1, x1 - x0)
    height = max(1, y1 - y0)
    histogram = alpha.histogram()
    area = sum(index * count for index, count in enumerate(histogram)) / 255.0
    extent = area / float(width * height)
    kind = (geometry or {}).get("kind")
    radius = min(3, max(1, round(min(width, height) * 0.015)))

    if extent >= 0.9 and kind in {"rect", "rounded_rect"}:
        result = Image.new("L", alpha.size, 0)
        draw = ImageDraw.Draw(result)
        pad = max(1, radius)
        bounds = (
            max(0, x0 - pad),
            max(0, y0 - pad),
            min(alpha.width - 1, x1 - 1 + pad),
            min(alpha.height - 1, y1 - 1 + pad),
        )
        corner = max(1, round(min(width, height) * 0.025))
        draw.rounded_rectangle(bounds, radius=corner, fill=255)
        return result.filter(ImageFilter.GaussianBlur(0.45)), "rectangle"

    result = alpha.filter(ImageFilter.MaxFilter(radius * 2 + 1))
    return result.filter(ImageFilter.GaussianBlur(0.65)), "dilated"


def main() -> int:
    parser = argparse.ArgumentParser(description="SAM3 text-prompt segmentation bridge")
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--prompt", action="append", default=[])
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--checkpoint", default=None)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--confidence", type=float, default=0.5)
    parser.add_argument("--resolution", type=int, default=1008)
    parser.add_argument("--mask-dir", type=Path, default=None)
    parser.add_argument("--crop-dir", type=Path, default=None)
    parser.add_argument("--min-area", type=int, default=120)
    args = parser.parse_args()

    import numpy as np
    import torch
    from PIL import Image
    from sam3.model.sam3_image_processor import Sam3Processor
    from sam3.model_builder import build_sam3_image_model

    device = args.device
    if device == "cuda" and not torch.cuda.is_available():
        device = "cpu"

    checkpoint = _resolve_checkpoint(args.checkpoint)
    model = build_sam3_image_model(
        checkpoint_path=checkpoint or None,
        device=device,
        eval_mode=True,
    )
    processor = Sam3Processor(
        model,
        resolution=args.resolution,
        device=device,
        confidence_threshold=args.confidence,
    )

    image = Image.open(args.image).convert("RGB")
    width, height = image.size
    rgba = image.convert("RGBA")

    if args.mask_dir is not None:
        args.mask_dir.mkdir(parents=True, exist_ok=True)
    if args.crop_dir is not None:
        args.crop_dir.mkdir(parents=True, exist_ok=True)

    autocast = (
        torch.autocast(device_type="cuda", dtype=torch.bfloat16)
        if device == "cuda"
        else nullcontext()
    )

    instances: list[dict[str, Any]] = []
    with autocast:
        state = processor.set_image(image)
        for prompt in args.prompt:
            result = processor.set_text_prompt(prompt=prompt, state=state)
            boxes = result["boxes"]
            scores = result["scores"]
            masks = result["masks"]
            for index in range(len(scores)):
                mask = masks[index].squeeze().cpu().numpy().astype(bool)
                if int(mask.sum()) < args.min_area:
                    continue
                geometry = _fit_geometry(mask)
                record: dict[str, Any] = {
                    "label": prompt,
                    "score": round(float(scores[index]), 4),
                    "box": _box_to_list(boxes[index]),
                    "area": int(mask.sum()),
                    "color": _mean_color(image, mask),
                    "geometry": geometry,
                    "stats": _mask_stats(image, mask, geometry),
                    "source": "sam3",
                }
                if args.mask_dir is not None:
                    mask_path = args.mask_dir / f"{prompt}_{index:03d}.png"
                    Image.fromarray((mask * 255).astype(np.uint8)).save(mask_path)
                    record["mask_path"] = str(mask_path)
                if args.crop_dir is not None:
                    alpha = Image.fromarray((mask * 255).astype(np.uint8))
                    alpha, crop_mode = _presentation_mask(alpha, prompt, geometry)
                    crop_bounds = alpha.getbbox()
                    if crop_bounds is not None:
                        cx0, cy0, cx1, cy1 = crop_bounds
                        sub = rgba.crop((cx0, cy0, cx1, cy1))
                        sub_alpha = alpha.crop((cx0, cy0, cx1, cy1))
                        sub.putalpha(sub_alpha)
                        crop_path = args.crop_dir / f"{prompt}_{index:03d}.png"
                        sub.save(crop_path)
                        record["crop_path"] = str(crop_path)
                        record["crop_box"] = [cx0, cy0, cx1, cy1]
                        record["stats"]["crop_mode"] = crop_mode
                instances.append(record)

    payload = {
        "image": str(args.image),
        "width": width,
        "height": height,
        "background": _background_color(image),
        "prompts": list(args.prompt),
        "instances": instances,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"sam3: wrote {len(instances)} instances to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
