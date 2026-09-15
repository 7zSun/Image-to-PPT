from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageChops, ImageFilter, ImageStat


def compare_images(
    reference_path: Path,
    render_path: Path,
    *,
    difference_path: Path | None = None,
) -> dict[str, float]:
    reference = Image.open(reference_path).convert("RGBA")
    rendered = Image.open(render_path).convert("RGBA")
    if rendered.size != reference.size:
        rendered = rendered.resize(reference.size, Image.Resampling.LANCZOS)

    diff = ImageChops.difference(reference, rendered)
    if difference_path is not None:
        difference_path = Path(difference_path)
        difference_path.parent.mkdir(parents=True, exist_ok=True)
        diff.save(difference_path)

    stat = ImageStat.Stat(diff)
    mean_abs = sum(stat.mean) / len(stat.mean) / 255.0

    ref_edge = reference.convert("L").filter(ImageFilter.FIND_EDGES)
    out_edge = rendered.convert("L").filter(ImageFilter.FIND_EDGES)
    edge_diff = ImageStat.Stat(ImageChops.difference(ref_edge, out_edge)).mean[0] / 255.0

    return {
        "mean_absolute_pixel_error": round(mean_abs, 6),
        "edge_difference": round(edge_diff, 6),
        "visual_similarity": round(max(0.0, 1.0 - mean_abs), 6),
    }
