from __future__ import annotations

from functools import lru_cache

from PIL import ImageFont

from image2svg.core.scene import Scene, SceneElement

_REFERENCE_SIZE = 1000
_WIDTH_FILL = 0.92
_HEIGHT_FILL = 0.9


def _is_bold(weight: object) -> bool:
    return str(weight or "normal").lower() in {"bold", "600", "700", "800", "900"}


def _font_candidates(font_family: str, bold: bool) -> list[str]:
    family = font_family.split(",")[0].strip(" '\"")
    normalized = family.lower()
    candidates = [family]
    if "microsoft yahei" in normalized:
        candidates.extend(["msyhbd.ttc" if bold else "msyh.ttc", "msyh.ttc"])
    elif "segoe ui" in normalized:
        candidates.extend(["segoeuib.ttf" if bold else "segoeui.ttf", "segoeui.ttf"])
    elif "arial" in normalized or "helvetica" in normalized:
        candidates.extend(["arialbd.ttf" if bold else "arial.ttf", "arial.ttf"])
    candidates.append("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf")
    return list(dict.fromkeys(candidate for candidate in candidates if candidate))


@lru_cache(maxsize=32)
def _metric_font(font_family: str, bold: bool) -> ImageFont.FreeTypeFont | None:
    for candidate in _font_candidates(font_family, bold):
        try:
            return ImageFont.truetype(candidate, _REFERENCE_SIZE)
        except OSError:
            continue
    return None


def _fallback_units(text: str) -> float:
    units = 0.0
    for character in text:
        if character.isspace():
            units += 0.32
        elif ord(character) > 255:
            units += 1.0
        elif character.isupper():
            units += 0.68
        else:
            units += 0.55
    return max(1.0, units)


def fit_text_to_box(
    text: str,
    width: float,
    height: float,
    *,
    font_family: str,
    font_weight: object = "normal",
) -> tuple[float, float, float]:
    usable_width = max(1.0, width * _WIDTH_FILL)
    usable_height = max(1.0, height * _HEIGHT_FILL)
    font = _metric_font(font_family, _is_bold(font_weight))
    if font is None:
        size = min(usable_height, usable_width / _fallback_units(text))
        return round(max(1.0, size), 2), 0.82, round(min(usable_width, size), 2)

    measured_width = max(1.0, float(font.getlength(text)))
    _left, top, _right, bottom = font.getbbox("Ag", anchor="ls")
    measured_height = max(1.0, float(bottom - top))
    size = min(
        usable_width * _REFERENCE_SIZE / measured_width,
        usable_height * _REFERENCE_SIZE / measured_height,
    )
    baseline_ratio = max(0.68, min(0.88, -float(top) / measured_height))
    rendered_width = measured_width * size / _REFERENCE_SIZE
    return (
        round(max(1.0, size), 2),
        round(baseline_ratio, 4),
        round(min(usable_width, rendered_width), 2),
    )


def fit_text_element(element: SceneElement) -> SceneElement:
    if element.type != "text" or not element.text:
        return element
    _x, _y, width, height = element.bbox
    style = element.style
    font_size, baseline_ratio, rendered_width = fit_text_to_box(
        element.text,
        width,
        height,
        font_family=str(style.get("font-family", "Arial")),
        font_weight=style.get("font-weight", "normal"),
    )
    style["font-size"] = font_size
    style["baseline-ratio"] = baseline_ratio
    style["measured-width"] = rendered_width
    style["fit-to-box"] = True
    return element


def fit_text_to_boxes(scene: Scene) -> Scene:
    for element in scene.elements:
        if element.type == "text" and element.style.get("fit-to-box"):
            fit_text_element(element)
    return scene


def _intersection_ratio(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> tuple[float, float]:
    fx, fy, fw, fh = first
    sx, sy, sw, sh = second
    horizontal = max(0.0, min(fx + fw, sx + sw) - max(fx, sx))
    vertical = max(0.0, min(fy + fh, sy + sh) - max(fy, sy))
    return horizontal / max(1.0, min(fw, sw)), vertical / max(1.0, min(fh, sh))


def _contains(box: tuple[float, float, float, float], point: tuple[float, float]) -> bool:
    x, y, width, height = box
    return x <= point[0] <= x + width and y <= point[1] <= y + height


def avoid_text_graphics(scene: Scene) -> Scene:
    scene_area = max(1.0, scene.width * scene.height)
    texts = [element for element in scene.elements if element.type == "text"]
    graphics = [
        element
        for element in scene.elements
        if element.type in {"image", "group", "path", "polygon", "polyline", "circle", "ellipse"}
        and not element.style.get("arrow_start")
        and element.bbox[2] * element.bbox[3] <= 0.03 * scene_area
    ]
    containers = [
        element
        for element in scene.elements
        if element.type == "rect"
        and element.bbox[2] * element.bbox[3] <= 0.35 * scene_area
    ]
    assignments: dict[str, list[SceneElement]] = {}
    owners: dict[str, str] = {}
    for text in texts:
        tx, ty, tw, th = text.bbox
        text_center = (tx + tw / 2.0, ty + th / 2.0)
        matches: list[tuple[float, SceneElement]] = []
        for graphic in graphics:
            horizontal, vertical = _intersection_ratio(text.bbox, graphic.bbox)
            gx, gy, gw, gh = graphic.bbox
            graphic_center = (gx + gw / 2.0, gy + gh / 2.0)
            delta_x = abs(text_center[0] - graphic_center[0])
            delta_y = abs(text_center[1] - graphic_center[1])
            stacked_overlap = horizontal >= 0.35 and vertical >= 0.15
            side_overlap = (
                horizontal >= 0.08 and vertical >= 0.45 and delta_x > delta_y * 1.25
            )
            if not stacked_overlap and not side_overlap:
                continue
            distance = delta_x / max(1.0, gw)
            matches.append((horizontal * vertical - distance * 0.02, graphic))
        if matches:
            graphic = max(matches, key=lambda match: match[0])[1]
            assignments.setdefault(graphic.id, []).append(text)
            owners[text.id] = graphic.id

    graphics_by_id = {element.id: element for element in graphics}
    for graphic_id, group in assignments.items():
        graphic = graphics_by_id[graphic_id]
        gx, gy, gw, gh = graphic.bbox
        changed = True
        while changed:
            changed = False
            left = min(element.bbox[0] for element in group)
            top = min(element.bbox[1] for element in group)
            right = max(element.bbox[0] + element.bbox[2] for element in group)
            bottom = max(element.bbox[1] + element.bbox[3] for element in group)
            group_width = right - left
            for candidate in texts:
                if candidate in group or owners.get(candidate.id) not in {None, graphic_id}:
                    continue
                cx, cy, cw, ch = candidate.bbox
                horizontal = max(0.0, min(right, cx + cw) - max(left, cx))
                horizontal_ratio = horizontal / max(1.0, min(group_width, cw))
                center_distance = abs((left + right) / 2.0 - (cx + cw / 2.0))
                vertical_gap = max(0.0, max(top, cy) - min(bottom, cy + ch))
                candidate_center = (cx + cw / 2.0, cy + ch / 2.0)
                graphic_center = (gx + gw / 2.0, gy + gh / 2.0)
                shares_container = any(
                    _contains(container.bbox, candidate_center)
                    and _contains(container.bbox, graphic_center)
                    for container in containers
                )
                if (
                    horizontal_ratio >= 0.6
                    and center_distance <= 0.35 * max(group_width, cw)
                    and vertical_gap <= max(4.0, ch * 0.3)
                    and shares_container
                ):
                    group.append(candidate)
                    owners[candidate.id] = graphic_id
                    changed = True
        left = min(element.bbox[0] for element in group)
        top = min(element.bbox[1] for element in group)
        right = max(element.bbox[0] + element.bbox[2] for element in group)
        bottom = max(element.bbox[1] + element.bbox[3] for element in group)
        group_center = ((left + right) / 2.0, (top + bottom) / 2.0)
        graphic_center = (gx + gw / 2.0, gy + gh / 2.0)
        parents = [
            container
            for container in containers
            if _contains(container.bbox, group_center)
            and _contains(container.bbox, graphic_center)
        ]
        if not parents:
            continue
        parent = min(parents, key=lambda element: element.bbox[2] * element.bbox[3])
        px, py, pw, ph = parent.bbox
        padding = max(1.0, min(4.0, ph * 0.02))
        gap = max(1.0, min(3.0, min(gw, gh) * 0.04))
        group_width = right - left
        group_height = bottom - top
        delta_x = group_center[0] - graphic_center[0]
        delta_y = group_center[1] - graphic_center[1]
        if abs(delta_x) > abs(delta_y) * 1.25:
            right_side = gx + gw + gap
            left_side = gx - gap - group_width
            left_bound = px + padding
            right_bound = px + pw - padding - group_width
            candidates = [right_side, left_side] if delta_x >= 0 else [left_side, right_side]
            valid = [candidate for candidate in candidates if left_bound <= candidate <= right_bound]
            if not valid:
                continue
            target = min(valid, key=lambda candidate: abs(candidate - left))
            delta = target - left
            if abs(delta) > max(group_width * 1.5, gw * 1.1):
                continue
            for element in group:
                x, y, width, height = element.bbox
                element.bbox = (x + delta, y, width, height)
                element.style["graphic-avoidance-dx"] = round(delta, 2)
            continue
        vertical_padding = max(0.5, min(2.0, ph * 0.01))
        vertical_gap = max(0.5, min(2.0, min(gw, gh) * 0.02))
        below = gy + gh + vertical_gap
        above = gy - vertical_gap - group_height
        lower_bound = py + vertical_padding
        upper_bound = py + ph - vertical_padding - group_height
        if group_center[1] >= graphic_center[1]:
            candidates = [below, above]
        else:
            candidates = [above, below]
        valid = [candidate for candidate in candidates if lower_bound <= candidate <= upper_bound]
        if not valid:
            continue
        target = min(valid, key=lambda candidate: abs(candidate - top))
        delta = target - top
        if abs(delta) > max(group_height * 1.5, gh * 1.1):
            continue
        for element in group:
            x, y, width, height = element.bbox
            element.bbox = (x, y + delta, width, height)
            element.style["graphic-avoidance-dy"] = round(delta, 2)
    return scene
