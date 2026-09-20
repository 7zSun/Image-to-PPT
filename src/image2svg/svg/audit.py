from __future__ import annotations

import xml.etree.ElementTree as ET

from image2svg.core.models import AuditResult

_XLINK_HREF = "{http://www.w3.org/1999/xlink}href"

_COUNTED_ELEMENTS = ("path", "rect", "circle", "ellipse", "polygon", "text")
_VECTOR_ELEMENTS = frozenset(
    {"path", "rect", "circle", "ellipse", "line", "polyline", "polygon", "text"}
)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _empty_element_counts() -> dict[str, int]:
    return {name: 0 for name in _COUNTED_ELEMENTS}


def _editable_score(
    *,
    has_viewbox: bool,
    vector_element_count: int,
    path_count: int,
    embedded_raster_count: int,
    external_resource_count: int,
) -> int:
    """Score how editable the SVG is, 20 points per satisfied rule."""
    score = 0
    if has_viewbox:
        score += 20
    if path_count > 0:
        score += 20
    if vector_element_count > 0:
        score += 20
    if embedded_raster_count == 0:
        score += 20
    if external_resource_count == 0:
        score += 20
    return score


def audit_svg(svg: str) -> AuditResult:
    try:
        root = ET.fromstring(svg)
    except ET.ParseError as exc:
        return AuditResult(
            valid_xml=False,
            has_viewbox=False,
            embedded_raster_count=0,
            external_resource_count=0,
            node_count=0,
            path_count=0,
            errors=[f"XML parse error: {exc}"],
            element_counts=_empty_element_counts(),
            editable_score=0,
        )

    errors: list[str] = []
    tag = _local_name(root.tag)
    if tag != "svg":
        errors.append("Root element is not <svg>")

    has_viewbox = "viewBox" in root.attrib
    if not has_viewbox:
        errors.append("Missing viewBox")

    nodes = list(root.iter())
    tags = [_local_name(node.tag) for node in nodes]
    element_counts = {name: tags.count(name) for name in _COUNTED_ELEMENTS}
    path_count = element_counts["path"]
    vector_element_count = sum(1 for node_tag in tags if node_tag in _VECTOR_ELEMENTS)

    embedded_raster_count = 0
    external_resource_count = 0
    for node in nodes:
        if _local_name(node.tag) != "image":
            continue
        href = node.attrib.get("href") or node.attrib.get(_XLINK_HREF) or ""
        if href.startswith("data:image/"):
            embedded_raster_count += 1
        elif href:
            external_resource_count += 1

    return AuditResult(
        valid_xml=True,
        has_viewbox=has_viewbox,
        embedded_raster_count=embedded_raster_count,
        external_resource_count=external_resource_count,
        node_count=len(nodes),
        path_count=path_count,
        errors=errors,
        element_counts=element_counts,
        editable_score=_editable_score(
            has_viewbox=has_viewbox,
            vector_element_count=vector_element_count,
            path_count=path_count,
            embedded_raster_count=embedded_raster_count,
            external_resource_count=external_resource_count,
        ),
    )
