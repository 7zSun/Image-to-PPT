"""Layout + text parsing with MinerU2.5-Pro, emitting JSON blocks.

Runs inside the AI environment. Separates text blocks (with content) from
image/figure blocks so the reconstruction never bakes text into pictures.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_MODEL_ENV = "MINERU_MODEL"
_REPO_ROOT = Path(
    os.environ.get("IMAGE2SVG_MODEL_ROOT") or Path(__file__).resolve().parents[5]
)

#: Block types that must remain raster (figures / photos / charts / tables).
IMAGE_TYPES = {
    "image",
    "image_block",
    "chart",
    "table",
    "equation",
    "equation_block",
}


def _resolve_model(explicit: str | None) -> str:
    if explicit:
        return explicit
    env = os.environ.get(_MODEL_ENV)
    if env and Path(env).exists():
        return env
    fallback = _REPO_ROOT / "minerU"
    return str(fallback) if fallback.exists() else "opendatalab/MinerU2.5-Pro-2605-1.2B"


def _text_style(pixels, box):
    import numpy as np

    x0, y0, x1, y1 = (round(v) for v in box)
    pad = max(2, round((y1 - y0) * 0.12))
    x0, y0, x1, y1 = x0 - pad, y0 - pad, x1 + pad, y1 + pad
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(pixels.shape[1], x1), min(pixels.shape[0], y1)
    if x1 <= x0 or y1 <= y0:
        return None, "normal"
    region = pixels[y0:y1, x0:x1].astype("float32")
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


def _ocr_lines(engine, crop_image):
    """Return (text, score, xyxy-in-crop) for each OCR line."""
    import numpy as np

    raw = engine.predict(np.asarray(crop_image.convert("RGB")))
    lines = []
    for page in raw:
        data = page if isinstance(page, dict) else page.json
        texts = data.get("rec_texts") or []
        scores = data.get("rec_scores") or []
        polygons = data.get("rec_polys")
        if polygons is None:
            polygons = data.get("dt_polys") or []
        for index, text in enumerate(texts):
            if index >= len(polygons):
                continue
            poly = polygons[index]
            xs = [float(point[0]) for point in poly]
            ys = [float(point[1]) for point in poly]
            lines.append(
                (
                    str(text),
                    float(scores[index]) if index < len(scores) else 0.0,
                    (min(xs), min(ys), max(xs), max(ys)),
                )
            )
    return lines


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    os.environ.setdefault("HF_HUB_OFFLINE", "1")

    parser = argparse.ArgumentParser(description="MinerU layout/text bridge")
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--model", default=None)
    parser.add_argument("--max-edge", type=int, default=1600)
    parser.add_argument("--crop-dir", type=Path, default=None)
    parser.add_argument("--ocr-text", action="store_true")
    parser.add_argument("--ocr-lang", default="en")
    parser.add_argument("--ocr-confidence", type=float, default=0.4)
    parser.add_argument("--text-box-ratio", type=float, default=0.12)
    args = parser.parse_args()

    import numpy as np
    from mineru_vl_utils import MinerUClient
    from PIL import Image
    from transformers import AutoProcessor, Qwen2VLForConditionalGeneration

    model_dir = _resolve_model(args.model)
    model = Qwen2VLForConditionalGeneration.from_pretrained(
        model_dir, dtype="auto", device_map="auto"
    )
    processor = AutoProcessor.from_pretrained(model_dir, use_fast=True)
    client = MinerUClient(
        backend="transformers", model=model, processor=processor, use_tqdm=False
    )

    image = Image.open(args.image).convert("RGB")
    width, height = image.size
    pixels = np.asarray(image)

    if args.crop_dir is not None:
        args.crop_dir.mkdir(parents=True, exist_ok=True)

    ocr_engine = None
    if args.ocr_text:
        from paddleocr import PaddleOCR

        ocr_engine = PaddleOCR(lang=args.ocr_lang, enable_mkldnn=False, device="cpu")

    blocks: list[dict] = []

    def region_blocks(region, ox, oy, counter) -> list[dict]:
        """Extract blocks from a region, mapping bboxes into global coordinates."""
        region_w, region_h = region.size
        scale_ = args.max_edge / max(region_w, region_h)
        working_region = (
            region.resize((int(region_w * scale_), int(region_h * scale_)))
            if scale_ < 1
            else region
        )
        out: list[dict] = []
        for block in client.two_step_extract(working_region):
            block_type = str(block.get("type", "unknown")).lower()
            bx0, by0, bx1, by1 = block.get("bbox", [0, 0, 0, 0])
            box = [
                ox + bx0 * region_w,
                oy + by0 * region_h,
                ox + bx1 * region_w,
                oy + by1 * region_h,
            ]
            text = block.get("content") or ""
            record = {"type": block_type, "bbox": box, "text": str(text)}

            if block_type in IMAGE_TYPES:
                x0, y0, x1, y1 = (max(0, round(v)) for v in box)
                x1, y1 = min(width, x1), min(height, y1)
                if x1 > x0 and y1 > y0:
                    sub = region.crop((int(x0 - ox), int(y0 - oy), int(x1 - ox), int(y1 - oy)))
                    lines = _ocr_lines(ocr_engine, sub) if ocr_engine is not None else []
                    lines = [line for line in lines if line[1] >= args.ocr_confidence]
                    area = max(1.0, (x1 - x0) * (y1 - y0))
                    text_area = sum(
                        max(0.0, c - a) * max(0.0, d - b)
                        for _, _score, (a, b, c, d) in lines
                    )
                    if lines and text_area / area >= args.text_box_ratio:
                        array = np.asarray(sub)
                        h, w = array.shape[:2]
                        interior = array[
                            int(h * 0.3) : int(h * 0.7) or h,
                            int(w * 0.3) : int(w * 0.7) or w,
                        ]
                        texture = float(np.std(interior.reshape(-1, 3).mean(axis=1)))
                        if texture > 25.0:
                            if args.crop_dir is not None:
                                counter[0] += 1
                                crop_path = args.crop_dir / f"layout_{counter[0]:03d}.png"
                                sub.save(crop_path)
                                record["crop_path"] = str(crop_path)
                                record["crop_box"] = [float(x0), float(y0), float(x1), float(y1)]
                            out.append(record)
                            if area >= 0.18 * width * height:
                                for line_text, _score, (a, b, c, d) in lines:
                                    global_box = [x0 + a, y0 + b, x0 + c, y0 + d]
                                    color, weight = _text_style(pixels, global_box)
                                    out.append(
                                        {
                                            "type": "text",
                                            "bbox": global_box,
                                            "text": line_text,
                                            "color": color,
                                            "weight": weight,
                                        }
                                    )
                            continue
                        ir, ig, ib = (int(c) for c in np.median(interior.reshape(-1, 3), axis=0))
                        gray = array.mean(axis=2)
                        reference = float(np.percentile(gray, 8))
                        edge_mask = gray <= reference + 12
                        fill_lum = ir * 0.299 + ig * 0.587 + ib * 0.114
                        stroke = None
                        if edge_mask.any():
                            dark = np.median(array[edge_mask], axis=0)
                            sr, sg, sb = (int(c) for c in dark)
                            stroke_lum = sr * 0.299 + sg * 0.587 + sb * 0.114
                            if stroke_lum < fill_lum - 20:
                                stroke = f"#{sr:02X}{sg:02X}{sb:02X}"
                        out.append(
                            {
                                "type": "box",
                                "bbox": box,
                                "text": "",
                                "color": f"#{ir:02X}{ig:02X}{ib:02X}",
                                "stroke": stroke,
                            }
                        )
                        for line_text, _score, (a, b, c, d) in lines:
                            global_box = [x0 + a, y0 + b, x0 + c, y0 + d]
                            color, weight = _text_style(pixels, global_box)
                            out.append(
                                {
                                    "type": "text",
                                    "bbox": global_box,
                                    "text": line_text,
                                    "color": color,
                                    "weight": weight,
                                }
                            )
                        continue

                    if args.crop_dir is not None:
                        counter[0] += 1
                        crop_path = args.crop_dir / f"layout_{counter[0]:03d}.png"
                        sub.save(crop_path)
                        record["crop_path"] = str(crop_path)
                        record["crop_box"] = [float(x0), float(y0), float(x1), float(y1)]
                    out.append(record)
                    continue
            elif text.strip():
                color, weight = _text_style(pixels, box)
                record["color"] = color
                record["weight"] = weight

            out.append(record)
        return out

    blocks = region_blocks(image, 0, 0, [0])

    # Deep pass: re-segment very large image blocks (whole diagrams lumped
    # together by MinerU) one level deeper.
    final: list[dict] = []
    for record in blocks:
        if record.get("type") in IMAGE_TYPES and record.get("crop_path"):
            x0, y0, x1, y1 = record["bbox"]
            if (
                (x1 - x0) * (y1 - y0) >= 0.06 * width * height
                and (x1 - x0) >= 100
                and (y1 - y0) >= 100
            ):
                sub = image.crop((int(x0), int(y0), int(x1), int(y1)))
                sub_blocks = region_blocks(sub, x0, y0, [len(final)])
                if len(sub_blocks) > 1:
                    final.extend(sub_blocks)
                    continue
        final.append(record)
    blocks = final

    payload = {
        "image": str(args.image),
        "width": width,
        "height": height,
        "model": model_dir,
        "blocks": blocks,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"mineru: wrote {len(blocks)} blocks to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
