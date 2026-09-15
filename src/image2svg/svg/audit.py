from __future__ import annotations

import xml.etree.ElementTree as ET

from image2svg.core.models import AuditResult


_XLINK_HREF = "{http://www.w3.org/1999/xlink}href"


def audit_svg(svg: str) -> AuditResult:
    errors: list[str] = []
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
        )

    tag = root.tag.rsplit("}", 1)[-1]
    if tag != "svg":
        errors.append("Root element is not <svg>")

    has_viewbox = "viewBox" in root.attrib
    if not has_viewbox:
        errors.append("Missing viewBox")

    nodes = list(root.iter())
    path_count = sum(node.tag.rsplit("}", 1)[-1] == "path" for node in nodes)
    embedded_raster_count = 0
    external_resource_count = 0

    for node in nodes:
        if node.tag.rsplit("}", 1)[-1] != "image":
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
    )
