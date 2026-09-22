"""Run PaddleOCR text detection + recognition and emit a JSON region list.

Runs inside the dedicated AI environment. The detection model can be the
PaddleOCR default; the recognition model can point at a fine-tuned inference
directory (for example the bundled PP-OCRv6 Hungarian antiqua model).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _poly_to_xyxy(poly: Any) -> list[float]:
    xs = [float(point[0]) for point in poly]
    ys = [float(point[1]) for point in poly]
    return [round(min(xs), 3), round(min(ys), 3), round(max(xs), 3), round(max(ys), 3)]


def _text_style(image: Any, box: list[float]) -> tuple[str | None, str]:
    import numpy as np

    x0, y0, x1, y1 = (round(value) for value in box)
    if x1 <= x0 or y1 <= y0:
        return None, "normal"
    pad = max(2, round((y1 - y0) * 0.12))
    width, height = image.size
    x0, y0 = max(0, x0 - pad), max(0, y0 - pad)
    x1, y1 = min(width, x1 + pad), min(height, y1 + pad)
    region = np.asarray(image.convert("RGB").crop((x0, y0, x1, y1)), dtype=np.float32)
    flat = region.reshape(-1, 3)
    border = np.concatenate(
        [region[0].reshape(-1, 3), region[-1].reshape(-1, 3), region[:, 0], region[:, -1]]
    )
    background = np.median(border, axis=0)
    coefficients = np.array([0.299, 0.587, 0.114], dtype="float32")
    luminance = flat @ coefficients
    background_luminance = float(background @ coefficients)
    distance = np.linalg.norm(flat - background, axis=1)
    if background_luminance < 135.0:
        mask = (distance >= 28.0) & (luminance >= background_luminance + 24.0)
    else:
        mask = (distance >= 28.0) & (luminance <= background_luminance - 24.0)
    if not mask.any():
        mask = luminance >= np.percentile(luminance, 92) if background_luminance < 135 else luminance <= np.percentile(luminance, 8)
    foreground = np.median(flat[mask], axis=0) if mask.any() else np.array([51.0] * 3)
    red, green, blue = (int(max(0, min(255, channel))) for channel in foreground)
    weight = "bold" if float(mask.mean()) >= 0.22 else "normal"
    return f"#{red:02X}{green:02X}{blue:02X}", weight


def _parse_v3(results: Any) -> list[dict[str, Any]]:
    regions: list[dict[str, Any]] = []
    for page in results:
        data = page if isinstance(page, dict) else page.json
        texts = data.get("rec_texts", []) or []
        scores = data.get("rec_scores", []) or []
        polys = data.get("rec_polys")
        if polys is None:
            polys = data.get("dt_polys", []) or []
        for index, text in enumerate(texts):
            poly = polys[index] if index < len(polys) else [[0, 0], [0, 0], [0, 0], [0, 0]]
            regions.append(
                {
                    "text": str(text),
                    "score": round(float(scores[index]) if index < len(scores) else 0.0, 4),
                    "box": _poly_to_xyxy(poly),
                }
            )
    return regions


def _parse_v2(results: Any) -> list[dict[str, Any]]:
    regions: list[dict[str, Any]] = []
    for page in results:
        if not page:
            continue
        for line in page:
            box, (text, score) = line[0], line[1]
            regions.append(
                {
                    "text": str(text),
                    "score": round(float(score), 4),
                    "box": _poly_to_xyxy(box),
                }
            )
    return regions


def main() -> int:
    parser = argparse.ArgumentParser(description="PaddleOCR bridge")
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--lang", default="ch")
    parser.add_argument("--det-model-dir", default=None)
    parser.add_argument("--rec-model-dir", default=None)
    parser.add_argument("--rec-char-dict", default=None)
    parser.add_argument("--confidence", type=float, default=0.3)
    parser.add_argument("--mkldnn", action="store_true", help="Enable oneDNN acceleration")
    args = parser.parse_args()

    from paddleocr import PaddleOCR
    from PIL import Image

    kwargs: dict[str, Any] = {"lang": args.lang, "enable_mkldnn": args.mkldnn}
    if args.det_model_dir:
        kwargs["text_detection_model_dir"] = args.det_model_dir
    if args.rec_model_dir:
        kwargs["text_recognition_model_dir"] = args.rec_model_dir
    if args.rec_char_dict:
        kwargs["text_recognition_char_dict_path"] = args.rec_char_dict
    if args.device:
        kwargs["device"] = args.device

    try:
        engine = PaddleOCR(**kwargs)
    except TypeError:
        kwargs.pop("enable_mkldnn", None)
        kwargs.pop("device", None)
        engine = PaddleOCR(**kwargs)

    if hasattr(engine, "predict"):
        raw = engine.predict(str(args.image))
        regions = _parse_v3(raw)
    else:  # pragma: no cover - legacy PaddleOCR 2.x
        raw = engine.ocr(str(args.image), cls=True)
        regions = _parse_v2(raw)

    regions = [region for region in regions if region["score"] >= args.confidence]

    with Image.open(args.image) as image:
        width, height = image.size
        for region in regions:
            color, weight = _text_style(image, region["box"])
            region["color"] = color
            region["weight"] = weight

    if len(regions) >= 5:
        heights = sorted(region["box"][3] - region["box"][1] for region in regions)
        median_height = heights[len(heights) // 2]
        if median_height > 0:
            regions = [
                region
                for region in regions
                if (region["box"][3] - region["box"][1]) <= 1.8 * median_height
                or (region["score"] >= 0.8 and len(region["text"].strip()) >= 3)
            ]

    payload = {
        "image": str(args.image),
        "width": width,
        "height": height,
        "regions": regions,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"ocr: wrote {len(regions)} regions to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
