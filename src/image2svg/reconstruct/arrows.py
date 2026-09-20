from __future__ import annotations

from image2svg.core.scene import Scene, SceneElement

BBox = tuple[float, float, float, float]


def _fmt(value: float) -> str:
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return text or "0"


def render_arrow(
    start: tuple[float, float],
    end: tuple[float, float],
    color: str,
    width: float,
) -> str:
    sx, sy = start
    ex, ey = end
    dx, dy = ex - sx, ey - sy
    length = (dx * dx + dy * dy) ** 0.5
    if length <= 0:
        return ""
    ux, uy = dx / length, dy / length
    px, py = -uy, ux
    head = max(6.0, width * 3.2)
    bx, by = ex - ux * head, ey - uy * head
    p1 = (bx + px * head * 0.55, by + py * head * 0.55)
    p2 = (bx - px * head * 0.55, by - py * head * 0.55)
    return (
        f'<line x1="{_fmt(sx)}" y1="{_fmt(sy)}" x2="{_fmt(ex)}" y2="{_fmt(ey)}" '
        f'stroke="{color}" stroke-width="{_fmt(width)}" stroke-linecap="round"/>'
        f'<polygon points="{_fmt(ex)},{_fmt(ey)} {_fmt(p1[0])},{_fmt(p1[1])} '
        f'{_fmt(p2[0])},{_fmt(p2[1])}" fill="{color}"/>'
    )


def _snap(
    point: tuple[float, float],
    target: tuple[float, float],
    boxes: list[BBox],
    max_distance: float,
) -> tuple[float, float]:
    """Move a line endpoint onto the nearest container border along the line."""
    px, py = point
    tx, ty = target
    dx, dy = tx - px, ty - py
    length = (dx * dx + dy * dy) ** 0.5
    if length <= 0:
        return point
    ux, uy = dx / length, dy / length
    best = None
    best_distance = max_distance
    for x, y, w, h in boxes:
        # intersect ray (px,py)+t*(ux,uy) with rectangle, t>0
        ts = []
        if ux != 0:
            for bx in (x, x + w):
                t = (bx - px) / ux
                if t > 0:
                    yy = py + t * uy
                    if y <= yy <= y + h:
                        ts.append(t)
        if uy != 0:
            for by in (y, y + h):
                t = (by - py) / uy
                if t > 0:
                    xx = px + t * ux
                    if x <= xx <= x + w:
                        ts.append(t)
        if ts:
            t = min(ts)
            if t < best_distance:
                best_distance = t
                best = (px + t * ux, py + t * uy)
    return best if best is not None else point


def connect_arrows(scene: Scene, *, max_snap: float = 0.0) -> Scene:
    """Snap arrow endpoints onto the nearest boxes, then de-duplicate arrows."""
    scene_area = max(1.0, scene.width * scene.height)
    containers: list[BBox] = [
        element.bbox
        for element in scene.elements
        if element.type in ("rect", "image")
        and 0.0002 * scene_area <= element.bbox[2] * element.bbox[3] <= 0.3 * scene_area
    ]
    seen: list[BBox] = []
    kept: list[SceneElement] = []

    for element in scene.elements:
        start = element.style.get("arrow_start") if element.style else None
        end = element.style.get("arrow_end") if element.style else None
        if element.type == "group" and start and end:
            start = _snap(tuple(start), tuple(end), containers, max_snap) if containers else tuple(start)
            end = _snap(tuple(end), tuple(start), containers, max_snap) if containers else tuple(end)
            markup = render_arrow(
                start,
                end,
                str(element.style.get("stroke", "#333333")),
                float(element.style.get("stroke_width", 2.0)),
            )
            x0 = min(start[0], end[0])
            y0 = min(start[1], end[1])
            kept.append(
                SceneElement(
                    id=element.id,
                    type="group",
                    bbox=(x0, y0, abs(end[0] - start[0]), abs(end[1] - start[1])),
                    z_index=element.z_index,
                    raw_svg=markup,
                    style={
                        "transform": "translate(0,0)",
                        "arrow_start": [start[0], start[1]],
                        "arrow_end": [end[0], end[1]],
                        "stroke": element.style.get("stroke", "#333333"),
                        "stroke_width": element.style.get("stroke_width", 2.0),
                    },
                )
            )
            continue

        kept.append(element)

    # De-duplicate overlapping arrows.
    final: list[SceneElement] = []
    for element in kept:
        if element.type == "group" and element.style.get("arrow_start"):
            x, y, w, h = element.bbox
            box = (x - 6, y - 6, w + 12, h + 12)
            duplicate = any(_overlap_ratio(box, s) > 0.98 for s in seen)
            if duplicate:
                continue
            seen.append(box)
        final.append(element)

    scene.elements = final
    return scene


def _overlap_ratio(a: BBox, b: BBox) -> float:
    ix = max(0.0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
    area = a[2] * a[3]
    return (ix * iy) / area if area > 0 else 0.0

