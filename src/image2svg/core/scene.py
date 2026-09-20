from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

BBox = tuple[float, float, float, float]

#: Element types understood by the SVG builder.
ELEMENT_TYPES = (
    "rect",
    "circle",
    "ellipse",
    "line",
    "polyline",
    "polygon",
    "path",
    "text",
    "image",
    "group",
)


@dataclass(slots=True)
class SceneElement:
    """A single editable element of a reconstructed scene.

    ``bbox`` is expressed as ``(x, y, width, height)`` in scene coordinates.
    Geometry that cannot be derived from the bbox uses ``points`` or ``path_d``.
    """

    id: str
    type: str
    bbox: BBox
    style: dict[str, Any] = field(default_factory=dict)
    z_index: int = 0
    text: str | None = None
    path_d: str | None = None
    points: list[tuple[float, float]] | None = None
    children: list[SceneElement] = field(default_factory=list)
    #: Pre-rendered vector markup (e.g. a locally traced icon) placed at ``bbox``.
    raw_svg: str | None = None


@dataclass(slots=True)
class Scene:
    """The editable scene intermediate representation produced by backends."""

    width: float
    height: float
    background: str | None = None
    elements: list[SceneElement] = field(default_factory=list)


def merge_scenes(scenes: list[Scene], *, background: str | None = None) -> Scene:
    """Combine several scenes into one canvas, preserving element order."""
    if not scenes:
        return Scene(width=0, height=0, background=background, elements=[])

    width = max(scene.width for scene in scenes)
    height = max(scene.height for scene in scenes)
    resolved_background = background
    if resolved_background is None:
        resolved_background = next(
            (scene.background for scene in scenes if scene.background), None
        )
    elements: list[SceneElement] = []
    for scene in scenes:
        elements.extend(scene.elements)
    return Scene(
        width=width,
        height=height,
        background=resolved_background,
        elements=elements,
    )
