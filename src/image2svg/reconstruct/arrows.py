from __future__ import annotations

from image2svg.core.scene import Scene, SceneElement

BBox = tuple[float, float, float, float]
Container = tuple[str, BBox, str]

FIXED_ARROW_COLOR = "#1769D2"
FIXED_ARROW_WIDTH = 2.25


def _fmt(value: float) -> str:
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return text or "0"


def render_arrow(
    start: tuple[float, float],
    end: tuple[float, float],
    color: str,
    width: float,
    arrowhead: bool = True,
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
    line = (
        f'<line x1="{_fmt(sx)}" y1="{_fmt(sy)}" x2="{_fmt(ex)}" y2="{_fmt(ey)}" '
        f'stroke="{color}" stroke-width="{_fmt(width)}" stroke-linecap="round"/>'
    )
    if not arrowhead:
        return line
    return line + (
        f'<polygon points="{_fmt(ex)},{_fmt(ey)} {_fmt(p1[0])},{_fmt(p1[1])} '
        f'{_fmt(p2[0])},{_fmt(p2[1])}" fill="{color}"/>'
    )


def _border_point(point: tuple[float, float], box: BBox) -> tuple[tuple[float, float], float]:
    px, py = point
    x, y, w, h = box
    right, bottom = x + w, y + h
    if x <= px <= right and y <= py <= bottom:
        candidates = [
            ((x, py), px - x),
            ((right, py), right - px),
            ((px, y), py - y),
            ((px, bottom), bottom - py),
        ]
        return min(candidates, key=lambda item: item[1])
    nearest = (min(max(px, x), right), min(max(py, y), bottom))
    distance = ((nearest[0] - px) ** 2 + (nearest[1] - py) ** 2) ** 0.5
    return nearest, distance


def _nearest_container(
    point: tuple[float, float],
    containers: list[Container],
    max_distance: float,
) -> tuple[tuple[float, float], str | None, float]:
    best_point = point
    best_id = None
    best_distance = max_distance
    for element_id, box, _element_type in containers:
        candidate, distance = _border_point(point, box)
        if distance <= best_distance:
            best_point = candidate
            best_id = element_id
            best_distance = distance
    return best_point, best_id, best_distance


def _center(box: BBox) -> tuple[float, float]:
    return (box[0] + box[2] / 2.0, box[1] + box[3] / 2.0)


def _boundary_toward(box: BBox, target: tuple[float, float]) -> tuple[float, float]:
    cx, cy = _center(box)
    dx, dy = target[0] - cx, target[1] - cy
    if abs(dx) < 1e-6 and abs(dy) < 1e-6:
        return (cx, cy)
    scale_x = box[2] / (2.0 * abs(dx)) if abs(dx) >= 1e-6 else float("inf")
    scale_y = box[3] / (2.0 * abs(dy)) if abs(dy) >= 1e-6 else float("inf")
    scale = min(scale_x, scale_y)
    return (cx + dx * scale, cy + dy * scale)


def _directional_candidates(
    midpoint: tuple[float, float],
    direction: tuple[float, float],
    containers: list[Container],
    side: int,
    diagonal: float,
) -> list[tuple[float, str, BBox]]:
    ux, uy = direction
    px, py = -uy, ux
    candidates: list[tuple[float, str, BBox]] = []
    for element_id, box, element_type in containers:
        cx, cy = _center(box)
        vx, vy = cx - midpoint[0], cy - midpoint[1]
        projection = vx * ux + vy * uy
        along_radius = abs(ux) * box[2] / 2.0 + abs(uy) * box[3] / 2.0
        if side * projection < -along_radius:
            continue
        perpendicular = abs(vx * px + vy * py)
        perpendicular_radius = abs(px) * box[2] / 2.0 + abs(py) * box[3] / 2.0
        gap = max(0.0, abs(projection) - along_radius)
        offset = max(0.0, perpendicular - perpendicular_radius)
        if gap > diagonal * 0.45 or offset > diagonal * 0.28:
            continue
        type_penalty = 0.0 if element_type != "image" else diagonal * 0.025
        candidates.append((gap + offset * 0.35 + type_penalty, element_id, box))
    return sorted(candidates, key=lambda item: item[0])


def _infer_relationship(
    start: tuple[float, float],
    end: tuple[float, float],
    containers: list[Container],
    diagonal: float,
) -> tuple[tuple[float, float], str, tuple[float, float], str] | None:
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = (dx * dx + dy * dy) ** 0.5
    if length <= 0:
        return None
    direction = (dx / length, dy / length)
    midpoint = ((start[0] + end[0]) / 2.0, (start[1] + end[1]) / 2.0)
    starts = _directional_candidates(midpoint, direction, containers, -1, diagonal)
    ends = _directional_candidates(midpoint, direction, containers, 1, diagonal)
    pairs = [
        (left[0] + right[0], left, right)
        for left in starts[:8]
        for right in ends[:8]
        if left[1] != right[1]
    ]
    if not pairs:
        return None
    _score, source, target = min(pairs, key=lambda item: item[0])
    source_center = _center(source[2])
    target_center = _center(target[2])
    return (
        _boundary_toward(source[2], target_center),
        source[1],
        _boundary_toward(target[2], source_center),
        target[1],
    )


def _normalize_reading_direction(
    start: tuple[float, float],
    start_id: str,
    end: tuple[float, float],
    end_id: str,
    boxes: dict[str, BBox],
) -> tuple[tuple[float, float], str, tuple[float, float], str]:
    start_center = _center(boxes[start_id])
    end_center = _center(boxes[end_id])
    start_box = boxes[start_id]
    end_box = boxes[end_id]
    dx = end_center[0] - start_center[0]
    dy = end_center[1] - start_center[1]
    vertically_separated = (
        start_box[1] + start_box[3] <= end_box[1]
        or end_box[1] + end_box[3] <= start_box[1]
    )
    horizontally_separated = (
        start_box[0] + start_box[2] <= end_box[0]
        or end_box[0] + end_box[2] <= start_box[0]
    )
    if vertically_separated:
        reverse = start_center[1] > end_center[1]
    elif horizontally_separated:
        reverse = start_center[0] > end_center[0]
    else:
        reverse = (
            start_center[1] > end_center[1]
            if abs(dy) >= abs(dx)
            else start_center[0] > end_center[0]
        )
    if reverse:
        return end, end_id, start, start_id
    return start, start_id, end, end_id


def connect_arrows(scene: Scene, *, max_snap: float | None = None) -> Scene:
    """Snap arrow endpoints onto the nearest boxes, then de-duplicate arrows."""
    scene_area = max(1.0, scene.width * scene.height)
    diagonal = (scene.width * scene.width + scene.height * scene.height) ** 0.5
    snap_distance = max(12.0, min(60.0, diagonal * 0.035)) if max_snap is None else max_snap
    containers: list[Container] = [
        (element.id, element.bbox, element.type)
        for element in scene.elements
        if element.type in ("rect", "image", "ellipse", "circle")
        and 0.0002 * scene_area <= element.bbox[2] * element.bbox[3] <= 0.3 * scene_area
    ]
    container_boxes = {element_id: box for element_id, box, _type in containers}
    seen: list[tuple[tuple[float, float], tuple[float, float]]] = []
    seen_relationships: set[tuple[str, str]] = set()
    kept: list[SceneElement] = []

    for element in scene.elements:
        start = element.style.get("arrow_start") if element.style else None
        end = element.style.get("arrow_end") if element.style else None
        if element.type == "group" and start and end:
            original_start = tuple(float(value) for value in start)
            original_end = tuple(float(value) for value in end)
            length = (
                (original_end[0] - original_start[0]) ** 2
                + (original_end[1] - original_start[1]) ** 2
            ) ** 0.5
            if length < max(6.0, diagonal * 0.004):
                continue
            start, start_id, _ = _nearest_container(
                original_start, containers, snap_distance
            )
            end, end_id, _ = _nearest_container(original_end, containers, snap_distance)
            if (start_id is None or end_id is None or start_id == end_id) and max_snap is None:
                inferred = _infer_relationship(
                    original_start, original_end, containers, diagonal
                )
                if inferred is not None:
                    start, start_id, end, end_id = inferred
            if start_id is None or end_id is None:
                continue
            if start_id == end_id:
                continue
            start, start_id, end, end_id = _normalize_reading_direction(
                start, start_id, end, end_id, container_boxes
            )
            markup = render_arrow(
                start,
                end,
                FIXED_ARROW_COLOR,
                FIXED_ARROW_WIDTH,
                True,
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
                        "stroke": FIXED_ARROW_COLOR,
                        "stroke_width": FIXED_ARROW_WIDTH,
                        "arrowhead": True,
                        "connector_start": start_id,
                        "connector_end": end_id,
                    },
                )
            )
            continue

        kept.append(element)

    # De-duplicate overlapping arrows.
    final: list[SceneElement] = []
    for element in kept:
        if element.type == "group" and element.style.get("arrow_start"):
            start = tuple(element.style["arrow_start"])
            end = tuple(element.style["arrow_end"])
            relationship = (
                str(element.style.get("connector_start", "")),
                str(element.style.get("connector_end", "")),
            )
            if relationship in seen_relationships:
                continue
            duplicate = any(
                _same_arrow(start, end, other_start, other_end) for other_start, other_end in seen
            )
            if duplicate:
                continue
            seen.append((start, end))
            seen_relationships.add(relationship)
        final.append(element)

    scene.elements = final
    return scene


def _same_arrow(
    start: tuple[float, float],
    end: tuple[float, float],
    other_start: tuple[float, float],
    other_end: tuple[float, float],
    tolerance: float = 12.0,
) -> bool:
    def close(a: tuple[float, float], b: tuple[float, float]) -> bool:
        return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 <= tolerance * tolerance

    return (close(start, other_start) and close(end, other_end)) or (
        close(start, other_end) and close(end, other_start)
    )
