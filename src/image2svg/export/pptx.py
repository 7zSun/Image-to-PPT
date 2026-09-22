from __future__ import annotations

import base64
import tempfile
from pathlib import Path

from image2svg.core.scene import Scene, SceneElement

EMU_PER_PX = 9525
#: Computer px -> PowerPoint points.
PT_PER_PX = 0.75

_RECT_TYPES = {"rect"}
_TEXT_TYPES = {"text"}
_RASTER_TYPES = {"image"}


def _color(value: str):
    from pptx.dml.color import RGBColor

    text = value.strip().lstrip("#")
    if len(text) == 3:
        text = "".join(ch * 2 for ch in text)
    if len(text) < 6 or any(character not in "0123456789abcdefABCDEF" for character in text[:6]):
        return RGBColor(0, 0, 0)
    return RGBColor(int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))


def _apply_shape_style(shape, style: dict, pt) -> None:
    fill = style.get("fill")
    if fill and str(fill).lower() != "none":
        shape.fill.solid()
        shape.fill.fore_color.rgb = _color(str(fill))
    else:
        shape.fill.background()
    stroke = style.get("stroke")
    if stroke and str(stroke).lower() != "none":
        shape.line.color.rgb = _color(str(stroke))
        shape.line.width = pt(float(style.get("stroke-width", style.get("stroke_width", 1.0))))
    else:
        shape.line.fill.background()


def _set_arrowhead(connector) -> None:
    from pptx.oxml.ns import qn
    from pptx.oxml.xmlchemy import OxmlElement

    line = connector.line._get_or_add_ln()
    current = line.find(qn("a:tailEnd"))
    if current is not None:
        line.remove(current)
    tail = OxmlElement("a:tailEnd")
    tail.set("type", "triangle")
    tail.set("w", "sm")
    tail.set("len", "sm")
    line.append(tail)


def _local_element(element: SceneElement) -> SceneElement:
    x, y, width, height = element.bbox
    points = element.points
    if points is not None:
        points = [(px - x, py - y) for px, py in points]
    return SceneElement(
        id=element.id,
        type=element.type,
        bbox=(0.0, 0.0, width, height),
        style=dict(element.style),
        z_index=element.z_index,
        text=element.text,
        path_d=element.path_d,
        points=points,
        children=element.children,
        raw_svg=element.raw_svg,
    )


def _rasterize(element: SceneElement, workdir: Path, canvas_width: float, canvas_height: float) -> Path | None:
    """Render a vector element to PNG so it can be placed as a picture."""
    from image2svg.svg.builder import build_svg
    from image2svg.svg.render import render_svg

    _, _, width, height = element.bbox
    width = max(width, 8.0)
    height = max(height, 8.0)
    output = workdir / f"{element.id}.png"

    if element.style and "arrow_start" in element.style:
        # Arrows carry global coordinates; render on the full canvas and crop.
        from PIL import Image

        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
            'viewBox="0 0 {w} {h}"><g transform="translate(0,0)">{raw}</g></svg>'
        ).format(
            w=round(canvas_width),
            h=round(canvas_height),
            raw=element.raw_svg or "",
        )
        full = workdir / f"{element.id}_full.png"
        try:
            render_svg(svg, full)
            with Image.open(full) as image:
                x0, y0, _x1, _y1 = element.bbox
                crop = image.crop(
                    (int(max(0, x0)), int(max(0, y0)), int(min(canvas_width, x0 + width)), int(min(canvas_height, y0 + height)))
                )
                crop.save(output)
            return output
        except Exception:  # noqa: BLE001 - rasterization is best-effort
            return None

    local = _local_element(element)
    svg = build_svg(Scene(width=width, height=height, elements=[local]))
    try:
        render_svg(svg, output, scale=2.0)
    except Exception:  # noqa: BLE001 - rasterization is best-effort
        return None
    return output


def _data_uri_to_png(href: str, path: Path) -> Path | None:
    if not href.startswith("data:image/") or ";base64," not in href:
        return None
    payload = href.split(";base64,", 1)[1]
    try:
        path.write_bytes(base64.b64decode(payload))
    except (ValueError, OSError):
        return None
    return path


def export_pptx(scene: Scene, output_path: Path) -> Path:
    """Write a Scene to a .pptx with native, editable PowerPoint objects."""
    from pptx import Presentation
    from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
    from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
    from pptx.util import Emu, Pt

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    presentation = Presentation()
    presentation.slide_width = Emu(int(scene.width * EMU_PER_PX))
    presentation.slide_height = Emu(int(scene.height * EMU_PER_PX))
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])

    if scene.background:
        shape = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, 0, 0, presentation.slide_width, presentation.slide_height
        )
        shape.fill.solid()
        shape.fill.fore_color.rgb = _color(scene.background)
        shape.line.fill.background()

    with tempfile.TemporaryDirectory(prefix="image2svg-pptx-") as tmp:
        workdir = Path(tmp)
        ordered = sorted(enumerate(scene.elements), key=lambda pair: (pair[1].z_index, pair[0]))
        for index, element in ordered:
            x, y, width, height = element.bbox
            left, top = Emu(int(x * EMU_PER_PX)), Emu(int(y * EMU_PER_PX))
            w, h = Emu(int(width * EMU_PER_PX)), Emu(int(height * EMU_PER_PX))
            style = element.style

            if element.type in _RECT_TYPES:
                shape_type = (
                    MSO_SHAPE.ROUNDED_RECTANGLE if style.get("rx") else MSO_SHAPE.RECTANGLE
                )
                shape = slide.shapes.add_shape(shape_type, left, top, w, h)
                _apply_shape_style(shape, style, Pt)
                continue

            if element.type in {"circle", "ellipse"}:
                shape = slide.shapes.add_shape(MSO_SHAPE.OVAL, left, top, w, h)
                _apply_shape_style(shape, style, Pt)
                continue

            if element.type in {"polygon", "polyline"} and element.points:
                points = element.points
                builder = slide.shapes.build_freeform(
                    points[0][0], points[0][1], scale=EMU_PER_PX
                )
                builder.add_line_segments(points[1:], close=element.type == "polygon")
                shape = builder.convert_to_shape()
                _apply_shape_style(shape, style, Pt)
                if element.type == "polyline":
                    shape.fill.background()
                continue

            arrow_start = style.get("arrow_start")
            arrow_end = style.get("arrow_end")
            if arrow_start and arrow_end:
                connector = slide.shapes.add_connector(
                    MSO_CONNECTOR.STRAIGHT,
                    Emu(int(float(arrow_start[0]) * EMU_PER_PX)),
                    Emu(int(float(arrow_start[1]) * EMU_PER_PX)),
                    Emu(int(float(arrow_end[0]) * EMU_PER_PX)),
                    Emu(int(float(arrow_end[1]) * EMU_PER_PX)),
                )
                connector.line.color.rgb = _color(str(style.get("stroke", "#333333")))
                connector.line.width = Pt(
                    float(style.get("stroke_width", style.get("stroke-width", 2.0)))
                    * PT_PER_PX
                )
                if style.get("arrowhead", True):
                    _set_arrowhead(connector)
                continue

            if element.type == "line":
                points = element.points or [(x, y + height), (x + width, y)]
                start, end = points[0], points[1]
                connector = slide.shapes.add_connector(
                    MSO_CONNECTOR.STRAIGHT,
                    Emu(int(start[0] * EMU_PER_PX)),
                    Emu(int(start[1] * EMU_PER_PX)),
                    Emu(int(end[0] * EMU_PER_PX)),
                    Emu(int(end[1] * EMU_PER_PX)),
                )
                connector.line.color.rgb = _color(str(style.get("stroke", "#333333")))
                connector.line.width = Pt(
                    float(style.get("stroke-width", style.get("stroke_width", 1.0)))
                    * PT_PER_PX
                )
                if style.get("arrowhead", False):
                    _set_arrowhead(connector)
                continue

            if element.type in _TEXT_TYPES:
                # Open XML converts SVG outlines; a real text box stays editable.
                box = slide.shapes.add_textbox(left, top, w, h)
                frame = box.text_frame
                frame.word_wrap = bool(style.get("wrap", False))
                if style.get("fit-to-box"):
                    frame.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
                frame.margin_left = frame.margin_right = 0
                frame.margin_top = frame.margin_bottom = 0
                frame.vertical_anchor = MSO_ANCHOR.MIDDLE
                paragraph = frame.paragraphs[0]
                align = style.get("align")
                if align == "center":
                    paragraph.alignment = PP_ALIGN.CENTER
                elif align == "right":
                    paragraph.alignment = PP_ALIGN.RIGHT
                else:
                    paragraph.alignment = PP_ALIGN.LEFT
                run = paragraph.add_run()
                run.text = element.text or ""
                font = run.font
                font.name = str(style.get("font-family", "Arial")).split(",")[0].strip("'\"")
                font.size = Pt(float(style.get("font-size", 18)) * PT_PER_PX)
                font.color.rgb = _color(str(style.get("fill", "#000000")))
                font.bold = str(style.get("font-weight", "normal")).lower() in {
                    "bold",
                    "600",
                    "700",
                    "800",
                    "900",
                }
                continue

            if element.type in _RASTER_TYPES:
                png = _data_uri_to_png(str(style.get("href", "")), workdir / f"{index}.png")
                if png is not None and png.exists():
                    slide.shapes.add_picture(str(png), left, top, w, h)
                continue

            png = _rasterize(element, workdir, scene.width, scene.height)
            if png is not None and png.exists():
                slide.shapes.add_picture(str(png), left, top, w, h)

    presentation.save(str(output_path))
    return output_path
