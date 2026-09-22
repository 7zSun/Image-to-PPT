from __future__ import annotations

from image2svg.analyze.models import SegmentInstance

#: Geometry kinds that are already good editable primitives.
CLEAN_KINDS = frozenset({"rect", "rounded_rect", "ellipse"})

#: Default heuristics separating "use the original" from "generate".
DEFAULT_GENERATE_AREA_RATIO = 0.02
DEFAULT_COMPLEX_VERTICES = 8
DEFAULT_LOW_SOLIDITY = 0.85
DEFAULT_MULTICOLOR = 3
#: Above this many distinct colors a region is treated as raster content
#: (photo / 3D render / chart) and kept from the original image.
DEFAULT_RASTER_COLORS = 20
RASTER_LABELS = frozenset({"photo", "photograph", "render", "chart"})
VECTOR_LABELS = frozenset({"building", "document", "icon", "illustration", "logo", "robot", "symbol"})


def classify_instance(
    instance: SegmentInstance,
    image_area: float,
    *,
    generate_area_ratio: float = DEFAULT_GENERATE_AREA_RATIO,
    complex_vertices: int = DEFAULT_COMPLEX_VERTICES,
    low_solidity: float = DEFAULT_LOW_SOLIDITY,
    multicolor: int = DEFAULT_MULTICOLOR,
    raster_colors: int = DEFAULT_RASTER_COLORS,
) -> str:
    """Decide how to reconstruct a segment.

    Returns one of ``"raster"``, ``"primitive"``, ``"generate"`` or ``"trace"``.

    * ``raster``: textured or multi-color region kept as the original
      transparent segmentation crop.
    * ``primitive``: clean fitted rectangle / rounded rect / ellipse.
    * ``generate``: small flat icon-like part suitable for an SVG model.
    * ``trace``: remaining simple contours reconstructed with VTracer.
    """
    stats = instance.stats or {}
    colors = int(stats.get("colors", 1))
    solidity = float(stats.get("solidity", 1.0))
    label = instance.label.strip().lower()

    if label in RASTER_LABELS:
        return "raster"

    x0, y0, x1, y1 = instance.box
    box_area = max(1.0, (x1 - x0) * (y1 - y0))
    is_small = box_area <= generate_area_ratio * max(1.0, image_area)

    geometry = instance.geometry or {}
    vertices = int(stats.get("vertices", 4))
    is_complex = vertices > complex_vertices or solidity < low_solidity

    if label in VECTOR_LABELS and colors >= raster_colors:
        return "raster"

    if colors >= raster_colors and (
        is_complex or geometry.get("kind") not in CLEAN_KINDS
    ):
        return "raster"

    if geometry.get("kind") in CLEAN_KINDS:
        return "primitive"

    if label in VECTOR_LABELS and is_small:
        return "generate"

    if is_small and (colors >= multicolor or is_complex):
        return "generate"
    return "trace"
