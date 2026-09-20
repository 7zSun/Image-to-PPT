from __future__ import annotations

from typing import Any
from xml.sax.saxutils import escape, quoteattr

from image2svg.core.scene import Scene, SceneElement

_COMMON_STYLE_KEYS = (
    "fill",
    "stroke",
    "stroke-width",
    "stroke-linecap",
    "stroke-linejoin",
    "opacity",
    "fill-opacity",
    "stroke-opacity",
)


def _fmt(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        text = f"{float(value):.3f}".rstrip("0").rstrip(".")
        return text or "0"
    return str(value)


def _attrs(pairs: list[tuple[str, Any]]) -> str:
    rendered = [f"{key}={quoteattr(_fmt(value))}" for key, value in pairs if value is not None]
    return (" " + " ".join(rendered)) if rendered else ""


def _common_style(style: dict[str, Any]) -> list[tuple[str, Any]]:
    return [(key, style[key]) for key in _COMMON_STYLE_KEYS if key in style]


def _text_style(style: dict[str, Any]) -> list[tuple[str, Any]]:
    pairs: list[tuple[str, Any]] = []
    for source, target in (
        ("font-size", "font-size"),
        ("font_size", "font-size"),
        ("font-family", "font-family"),
        ("font_family", "font-family"),
        ("font-weight", "font-weight"),
        ("font_weight", "font-weight"),
        ("text-anchor", "text-anchor"),
        ("text_anchor", "text-anchor"),
    ):
        if source in style:
            pairs.append((target, style[source]))
    return pairs


def _element_to_svg(element: SceneElement) -> str:
    x, y, width, height = element.bbox
    style = element.style
    element_id = [("id", element.id)]

    if element.raw_svg is not None:
        transform = style.get("transform") or f"translate({_fmt(x)},{_fmt(y)})"
        return f"<g{_attrs(element_id + [('transform', transform)])}>{element.raw_svg}</g>"

    if element.type == "group":
        inner = "".join(_element_to_svg(child) for child in element.children)
        return f"<g{_attrs(element_id)}>{inner}</g>"

    if element.type == "rect":
        geometry: list[tuple[str, Any]] = [
            ("x", x),
            ("y", y),
            ("width", width),
            ("height", height),
        ]
        geometry += [(key, style[key]) for key in ("rx", "ry") if key in style]
        return f"<rect{_attrs(element_id + geometry + _common_style(style))}/>"

    if element.type == "circle":
        radius = style.get("r", min(width, height) / 2)
        geometry = [("cx", x + width / 2), ("cy", y + height / 2), ("r", radius)]
        return f"<circle{_attrs(element_id + geometry + _common_style(style))}/>"

    if element.type == "ellipse":
        geometry = [
            ("cx", x + width / 2),
            ("cy", y + height / 2),
            ("rx", width / 2),
            ("ry", height / 2),
        ]
        return f"<ellipse{_attrs(element_id + geometry + _common_style(style))}/>"

    if element.type == "line":
        points = element.points or [(x, y + height), (x + width, y)]
        (x1, y1), (x2, y2) = points[0], points[1]
        geometry = [("x1", x1), ("y1", y1), ("x2", x2), ("y2", y2)]
        return f"<line{_attrs(element_id + geometry + _common_style(style))}/>"

    if element.type in ("polygon", "polyline"):
        points = " ".join(f"{_fmt(px)},{_fmt(py)}" for px, py in (element.points or []))
        geometry = [("points", points)]
        return f"<{element.type}{_attrs(element_id + geometry + _common_style(style))}/>"

    if element.type == "path":
        geometry = [("d", element.path_d or "")]
        return f"<path{_attrs(element_id + geometry + _common_style(style))}/>"

    if element.type == "text":
        geometry = [("x", x), ("y", y + height)]
        attrs = element_id + geometry + _text_style(style) + _common_style(style)
        return f"<text{_attrs(attrs)}>{escape(element.text or '')}</text>"

    if element.type == "image":
        href = style.get("href", "")
        geometry = [
            ("x", x),
            ("y", y),
            ("width", width),
            ("height", height),
            ("href", href),
            ("xlink:href", href),
        ]
        return f"<image{_attrs(element_id + geometry)}/>"

    raise ValueError(f"Unsupported scene element type: {element.type}")


def build_svg(scene: Scene) -> str:
    """Render a :class:`Scene` into a standalone editable SVG document."""
    body: list[str] = []
    if scene.background:
        body.append(
            "<rect"
            + _attrs(
                [
                    ("x", 0),
                    ("y", 0),
                    ("width", scene.width),
                    ("height", scene.height),
                    ("fill", scene.background),
                ]
            )
            + "/>"
        )

    ordered = sorted(enumerate(scene.elements), key=lambda pair: (pair[1].z_index, pair[0]))
    body.extend(_element_to_svg(element) for _, element in ordered)

    return (
        '<svg xmlns="http://www.w3.org/2000/svg"'
        ' xmlns:xlink="http://www.w3.org/1999/xlink"'
        ' version="1.1"'
        + _attrs(
            [
                ("width", scene.width),
                ("height", scene.height),
                ("viewBox", f"0 0 {_fmt(scene.width)} {_fmt(scene.height)}"),
            ]
        )
        + ">"
        + "".join(body)
        + "</svg>"
    )
