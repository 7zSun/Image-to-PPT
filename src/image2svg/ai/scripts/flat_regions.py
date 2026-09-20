#!/usr/bin/env python3
"""Detect large flat rounded rectangles (panels, cards, banners) deterministically.

Runs inside the AI environment (numpy + OpenCV). Emits JSON records compatible
with the segmentation schema so the existing reconstruction can turn them into
clean <rect>/<rect rx> elements. This gives the structural skeleton that
open-vocabulary prompting (SAM3) tends to miss on dense figures.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Flat region / panel detector")
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--min-area-ratio", type=float, default=0.0025)
    parser.add_argument("--max-regions", type=int, default=120)
    parser.add_argument("--close", type=int, default=17)
    parser.add_argument("--quant", type=int, default=24)
    parser.add_argument("--rect-fill", type=float, default=0.86)
    args = parser.parse_args()

    import cv2
    import numpy as np
    from PIL import Image

    image = np.asarray(Image.open(args.image).convert("RGB"), dtype=np.uint8)
    height, width = image.shape[:2]
    image_area = float(height * width)
    min_area = args.min_area_ratio * image_area

    quant = (image // args.quant) * args.quant
    colors, counts = np.unique(quant.reshape(-1, 3), axis=0, return_counts=True)
    order = np.argsort(-counts)

    kernel = np.ones((args.close, args.close), np.uint8)
    regions: list[dict] = []
    seen: list[tuple[int, int, int, int]] = []

    def overlaps_existing(box: tuple[int, int, int, int]) -> bool:
        x0, y0, x1, y1 = box
        for sx0, sy0, sx1, sy1 in seen:
            ix = max(0, min(x1, sx1) - max(x0, sx0))
            iy = max(0, min(y1, sy1) - max(y0, sy0))
            inter = ix * iy
            area = (x1 - x0) * (y1 - y0)
            if area and inter / area > 0.6:
                return True
        return False

    for index in order:
        if counts[index] < min_area:
            break
        color = colors[index]
        mask = np.all(quant == color, axis=2).astype(np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        num, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
        for label in range(1, num):
            x, y, w, h, area = stats[label]
            if area < min_area:
                continue
            fill = area / float(w * h)
            if fill < args.rect_fill:
                continue
            box = (int(x), int(y), int(x + w), int(y + h))
            if overlaps_existing(box):
                continue
            component = labels[y : y + h, x : x + w] == label
            pixels = image[y : y + h, x : x + w][component].astype(np.int32)
            quantized = (pixels // 16).astype(np.int32)
            values, counts_ = np.unique(quantized, axis=0, return_counts=True)
            chosen = values[counts_.argmax()]
            dominant = pixels[np.all(quantized == chosen, axis=1)]
            red, green, blue = (int(channel) for channel in dominant.mean(axis=0))
            if red > 246 and green > 246 and blue > 246 and area / image_area > 0.2:
                continue  # skip the page background
            kind = "rect" if fill >= 0.95 else "rounded_rect"
            geometry: dict = {"kind": kind, "bbox": [float(box[0]), float(box[1]), float(box[2]), float(box[3])]}
            if kind == "rounded_rect":
                geometry["radius"] = round(min(w, h) * 0.12, 1)
            regions.append(
                {
                    "label": "panel",
                    "score": 1.0,
                    "box": [float(box[0]), float(box[1]), float(box[2]), float(box[3])],
                    "area": int(area),
                    "color": f"#{red:02X}{green:02X}{blue:02X}",
                    "geometry": geometry,
                    "stats": {"colors": 1, "vertices": 4, "solidity": 1.0},
                }
            )
            seen.append(box)
            if len(regions) >= args.max_regions:
                break
        if len(regions) >= args.max_regions:
            break

    regions.sort(key=lambda r: r["area"], reverse=True)
    hsv = cv2.cvtColor(image, cv2.COLOR_RGB2HSV)
    saturation = hsv[:, :, 1]
    value = hsv[:, :, 2]
    colored = ((saturation > 45) & (value > 50)).astype(np.uint8)
    colored = cv2.morphologyEx(colored, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    contours, _ = cv2.findContours(colored, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:60]:
        x, y, w, h = cv2.boundingRect(contour)
        box_area = w * h
        if box_area < min_area or box_area > 0.9 * image_area:
            continue
        box = (int(x), int(y), int(x + w), int(y + h))
        if overlaps_existing(box):
            continue
        patch = image[y : y + h, x : x + w]
        patch_mask = colored[y : y + h, x : x + w].astype(bool)
        if not patch_mask.any():
            continue
        selected = patch[patch_mask].astype(np.int32)
        quantized = (selected // 16).astype(np.int32)
        values, counts_ = np.unique(quantized, axis=0, return_counts=True)
        chosen = values[counts_.argmax()]
        dominant = selected[np.all(quantized == chosen, axis=1)]
        red, green, blue = (int(channel) for channel in dominant.mean(axis=0))
        regions.append(
            {
                "label": "panel",
                "score": 1.0,
                "box": [float(box[0]), float(box[1]), float(box[2]), float(box[3])],
                "area": int(box_area),
                "color": f"#{red:02X}{green:02X}{blue:02X}",
                "geometry": {
                    "kind": "rounded_rect",
                    "bbox": [float(box[0]), float(box[1]), float(box[2]), float(box[3])],
                    "radius": round(min(w, h) * 0.03, 1),
                },
                "stats": {"colors": 1, "vertices": 4, "solidity": 1.0},
            }
        )
        seen.append(box)
        if len(regions) >= args.max_regions:
            break

    regions.sort(key=lambda r: r["area"], reverse=True)

    # Arrow pass: thin dark line segments that are not part of a box border.
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    dark_mask = (gray < 110).astype(np.uint8)
    candidates = cv2.HoughLinesP(
        dark_mask, 1, np.pi / 180, threshold=40, minLineLength=36, maxLineGap=6
    )

    def _thin_segment(x1: int, y1: int, x2: int, y2: int) -> bool:
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy)
        if length <= 0:
            return False
        px, py = -dy / length, dx / length
        for t in (0.25, 0.5, 0.75):
            cx = round(x1 + dx * t)
            cy = round(y1 + dy * t)
            for offset in (-3, 3):
                nx = round(cx + px * offset)
                ny = round(cy + py * offset)
                if 0 <= ny < height and 0 <= nx < width and gray[ny, nx] < 110:
                    return False
        return True

    segments = []
    if candidates is not None:
        for line in candidates[:, 0]:
            x1, y1, x2, y2 = (int(v) for v in line)
            length = math.hypot(x2 - x1, y2 - y1)
            if length < 30:
                continue
            on_border = False
            for bx0, by0, bx1, by1 in seen:
                inside_x = bx0 - 6 <= x1 <= bx1 + 6 and bx0 - 6 <= x2 <= bx1 + 6
                near_edge = (
                    abs(y1 - by0) <= 6
                    or abs(y1 - by1) <= 6
                    or abs(y2 - by0) <= 6
                    or abs(y2 - by1) <= 6
                )
                if inside_x and near_edge:
                    on_border = True
                    break
            if on_border or not _thin_segment(x1, y1, x2, y2):
                continue
            segments.append((float(x1), float(y1), float(x2), float(y2)))

    # Merge collinear, close segments into single connectors.
    clusters: list[list[tuple[float, float, float, float]]] = []
    for seg in segments:
        x1, y1, x2, y2 = seg
        length = math.hypot(x2 - x1, y2 - y1)
        ux, uy = (x2 - x1) / length, (y2 - y1) / length
        placed = False
        for cluster in clusters:
            cx1, cy1, cx2, cy2 = cluster[0]
            cl = math.hypot(cx2 - cx1, cy2 - cy1)
            cux, cuy = (cx2 - cx1) / cl, (cy2 - cy1) / cl
            if abs(ux * cux + uy * cuy) < 0.97:
                continue
            # distance between segment midpoints perpendicular to direction
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            cmx, cmy = (cx1 + cx2) / 2, (cy1 + cy2) / 2
            perp = abs((mx - cmx) * (-uy) + (my - cmy) * ux)
            if perp > 12:
                continue
            cluster.append(seg)
            placed = True
            break
        if not placed:
            clusters.append([seg])

    for cluster in clusters:
        pts = [(s[0], s[1]) for s in cluster] + [(s[2], s[3]) for s in cluster]
        if len(pts) < 2:
            continue
        # extreme points along the cluster direction
        start = min(pts, key=lambda p: (p[0], p[1]))
        end = max(pts, key=lambda p: (p[0], p[1]))
        if abs(start[0] - end[0]) < abs(start[1] - end[1]):
            start = min(pts, key=lambda p: (p[1], p[0]))
            end = max(pts, key=lambda p: (p[1], p[0]))
        length = math.hypot(end[0] - start[0], end[1] - start[1])
        if length < 30:
            continue
        sx, sy, ex, ey = float(start[0]), float(start[1]), float(end[0]), float(end[1])
        sample = image[
            max(0, int(min(sy, ey))) : min(height, int(max(sy, ey)) + 1),
            max(0, int(min(sx, ex))) : min(width, int(max(sx, ex)) + 1),
        ]
        if sample.size == 0:
            continue
        red, green, blue = (int(c) for c in np.median(sample.reshape(-1, 3), axis=0))
        regions.append(
            {
                "label": "arrow",
                "score": 1.0,
                "box": [float(min(sx, ex)), float(min(sy, ey)), float(max(sx, ex)), float(max(sy, ey))],
                "area": int(length),
                "color": f"#{red:02X}{green:02X}{blue:02X}",
                "geometry": {
                    "kind": "arrow",
                    "start": [float(sx), float(sy)],
                    "end": [float(ex), float(ey)],
                    "stroke": f"#{red:02X}{green:02X}{blue:02X}",
                    "stroke_width": 2.0,
                },
                "stats": {"colors": 1, "vertices": 2, "solidity": 1.0},
            }
        )

    payload = {"image": str(args.image), "width": width, "height": height, "background": None, "instances": regions}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"flat_regions: wrote {len(regions)} regions to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
