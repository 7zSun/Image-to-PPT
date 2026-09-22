from __future__ import annotations

import re

from image2svg.core.scene import Scene, SceneElement

BBox = tuple[float, float, float, float]


def _rgb(value: object) -> tuple[int, int, int] | None:
    text = str(value or "").strip().lstrip("#")
    if len(text) == 3:
        text = "".join(character * 2 for character in text)
    if len(text) < 6 or any(character not in "0123456789abcdefABCDEF" for character in text[:6]):
        return None
    return int(text[:2], 16), int(text[2:4], 16), int(text[4:6], 16)


def _luminance(value: object) -> float | None:
    color = _rgb(value)
    if color is None:
        return None
    return color[0] * 0.299 + color[1] * 0.587 + color[2] * 0.114


def _color_distance(first: object, second: object) -> float:
    a, b = _rgb(first), _rgb(second)
    if a is None or b is None:
        return float("inf")
    return sum((left - right) ** 2 for left, right in zip(a, b)) ** 0.5


def _contains(container: BBox, point: tuple[float, float]) -> bool:
    x, y, w, h = container
    px, py = point
    return x <= px <= x + w and y <= py <= y + h


def _iou(a: BBox, b: BBox) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix = max(0.0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0.0, min(ay + ah, by + bh) - max(ay, by))
    inter = ix * iy
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def drop_baked_text(scene: Scene) -> Scene:
    """Remove OCR <text> whose center lies inside an embedded image.

    Those regions already contain their text as pixels, so keeping the OCR
    overlay would render the text twice.
    """
    image_boxes = [element.bbox for element in scene.elements if element.type == "image"]
    if not image_boxes:
        return scene

    kept: list[SceneElement] = []
    for element in scene.elements:
        if element.type == "text":
            x, y, w, h = element.bbox
            center = (x + w / 2.0, y + h / 2.0)
            if any(_contains(box, center) for box in image_boxes):
                continue
        kept.append(element)
    scene.elements = kept
    return scene


def drop_duplicate_text(scene: Scene, *, iou_threshold: float = 0.25) -> Scene:
    """Remove text elements duplicated by two analyzers (same text + overlapping box)."""
    kept: list[SceneElement] = []
    for element in scene.elements:
        if element.type == "text" and element.text:
            normalized = re.sub(r"[^\w]+", "", element.text, flags=re.UNICODE).lower()
            duplicate = False
            for index, other in enumerate(kept):
                if other.type == "text" and other.text:
                    other_normalized = re.sub(
                        r"[^\w]+", "", other.text, flags=re.UNICODE
                    ).lower()
                    same = other_normalized == normalized
                    if same and _iou(other.bbox, element.bbox) >= iou_threshold:
                        if _text_quality(element) > _text_quality(other):
                            kept[index] = element
                        duplicate = True
                        break
                    if same and abs(other.bbox[1] - element.bbox[1]) < 0.5 * element.bbox[3]:
                        ix = max(
                            0.0,
                            min(other.bbox[0] + other.bbox[2], element.bbox[0] + element.bbox[2])
                            - max(other.bbox[0], element.bbox[0]),
                        )
                        if ix > 0.5 * min(other.bbox[2], element.bbox[2]):
                            duplicate = True
                            break
                    if same:
                        other_center = (
                            other.bbox[0] + other.bbox[2] / 2.0,
                            other.bbox[1] + other.bbox[3] / 2.0,
                        )
                        center = (
                            element.bbox[0] + element.bbox[2] / 2.0,
                            element.bbox[1] + element.bbox[3] / 2.0,
                        )
                        if (
                            abs(other_center[0] - center[0])
                            <= 0.15 * max(other.bbox[2], element.bbox[2])
                            and abs(other_center[1] - center[1])
                            <= 1.2 * max(other.bbox[3], element.bbox[3])
                        ):
                            duplicate = True
                            break
                    contained = (
                        len(normalized) >= 2
                        and len(other_normalized) >= 2
                        and (normalized in other_normalized or other_normalized in normalized)
                    )
                    if contained and _boxes_share_text_line(other.bbox, element.bbox):
                        if _text_quality(element) > _text_quality(other):
                            kept[index] = element
                        duplicate = True
                        break
            if duplicate:
                continue
        kept.append(element)
    scene.elements = kept
    return scene


def _boxes_share_text_line(first: BBox, second: BBox) -> bool:
    fx, fy, fw, fh = first
    sx, sy, sw, sh = second
    horizontal = max(0.0, min(fx + fw, sx + sw) - max(fx, sx))
    vertical = max(0.0, min(fy + fh, sy + sh) - max(fy, sy))
    return horizontal >= 0.45 * min(fw, sw) and vertical >= 0.45 * min(fh, sh)


def _text_quality(element: SceneElement) -> tuple[int, float, int]:
    source_priority = {"paddleocr": 2, "mineru": 1}.get(
        str(element.style.get("source", "")), 0
    )
    confidence = float(element.style.get("confidence", 0.0) or 0.0)
    return source_priority, confidence, len(element.text or "")


def _category(element: SceneElement) -> str:
    # rect / image / traced group at the same spot are the same construction
    # emitted by different layers, so they share one category.
    if element.type in ("rect", "image"):
        return "shape"
    if element.type == "group" and not (element.style or {}).get("arrow_start"):
        return "shape"
    return "other"


def _richness(element: SceneElement) -> tuple[int, float]:
    style = element.style or {}
    semantic = str(style.get("semantic", "")).lower()
    source = str(style.get("source", ""))
    if element.type == "image" and semantic in {"photo", "render", "chart"}:
        score = 20
    elif element.type == "image" and source in {"mineru", "sam3"}:
        score = 16
    elif element.type == "rect":
        score = 6
    elif element.type == "group":
        score = 5
    elif element.type == "image":
        score = 2
    else:
        score = 0
    if style.get("stroke"):
        score += 2
    if style.get("fill"):
        score += 1
    score += {"groundingdino": 3, "mineru": 2, "flat-regions": 1}.get(
        source, 0
    )
    _x, _y, w, h = element.bbox
    return score, w * h


def assign_z_order(scene: Scene) -> Scene:
    """Order layers bottom-to-top.

    Large blocks sit below small ones: all shapes are ordered primarily by
    area (bigger = behind); background fills go first, then arrows, then text.
    """
    scene_area = max(1.0, scene.width * scene.height)
    type_priority = {"rect": 0, "image": 1, "group": 2}

    def key(element: SceneElement) -> tuple[float, float, float]:
        area = element.bbox[2] * element.bbox[3]
        if element.type == "text":
            return (5.0, 0.0, -area)
        if element.type == "group" and (element.style or {}).get("arrow_start"):
            return (4.0, 0.0, -area)
        if element.type == "rect" and area >= 0.9 * scene_area:
            return (-1.0, 0.0, -area)
        priority = float(type_priority.get(element.type, 0))
        return (1.0, priority, -area)

    ordered = sorted(enumerate(scene.elements), key=lambda pair: (key(pair[1]), pair[0]))
    for z, (_index, element) in enumerate(ordered):
        element.z_index = z
    return scene


def align_text_to_containers(scene: Scene) -> Scene:
    containers = [
        element
        for element in scene.elements
        if element.type == "rect"
        and element.bbox[2] * element.bbox[3] <= 0.35 * max(1.0, scene.width * scene.height)
    ]
    for element in scene.elements:
        if element.type != "text":
            continue
        x, y, width, height = element.bbox
        center = (x + width / 2.0, y + height / 2.0)
        matches = [container for container in containers if _contains(container.bbox, center)]
        if not matches:
            for container in containers:
                cx, cy, cw, ch = container.bbox
                intersection_width = max(0.0, min(x + width, cx + cw) - max(x, cx))
                intersection_height = max(0.0, min(y + height, cy + ch) - max(y, cy))
                if (
                    height >= 0.45 * ch
                    and intersection_width >= 0.65 * width
                    and intersection_height * intersection_width >= 0.3 * width * height
                ):
                    matches.append(container)
        align = "left"
        if matches:
            container = min(matches, key=lambda value: value.bbox[2] * value.bbox[3])
            box = container.bbox
            if not _contains(box, center) and height <= 0.9 * box[3]:
                y = box[1] + (box[3] - height) / 2.0
                element.bbox = (x, y, width, height)
                center = (x + width / 2.0, y + height / 2.0)
            box_center_x = box[0] + box[2] / 2.0
            padding = max(2.0, min(8.0, min(box[2], box[3]) * 0.035))
            inner_left = box[0] + padding
            inner_right = box[0] + box[2] - padding
            if width > inner_right - inner_left:
                x = inner_left
                width = inner_right - inner_left
            if abs(center[0] - box_center_x) <= max(8.0, box[2] * 0.24):
                align = "center"
                x = box_center_x - width / 2.0
            else:
                x = max(inner_left, min(x, inner_right - width))
            element.bbox = (x, y, width, height)
            background_luminance = _luminance(container.style.get("fill"))
            text_luminance = _luminance(element.style.get("fill"))
            if background_luminance is not None and text_luminance is not None:
                if background_luminance < 165.0 and abs(text_luminance - background_luminance) < 75.0:
                    element.style["fill"] = "#FFFFFF"
                elif background_luminance > 210.0 and text_luminance > 190.0:
                    element.style["fill"] = "#1F3F7A"
        elif width >= scene.width * 0.25 and abs(center[0] - scene.width / 2.0) <= scene.width * 0.06:
            align = "center"
        element.style["align"] = align
        element.style["text-anchor"] = "middle" if align == "center" else "start"
    return scene


def filter_artifact_text(scene: Scene) -> Scene:
    """Drop text that is clearly a detector artifact (e.g. '1|1', tiny glyphs)."""
    import re

    artifact = re.compile(r"^\s*\d+\s*[|/\\]\s*\d+\s*$")
    kept: list[SceneElement] = []
    for element in scene.elements:
        if element.type == "text":
            text = (element.text or "").strip()
            _x, _y, w, h = element.bbox
            if not text or artifact.match(text):
                continue
            if w < 3 or h < 3:
                continue
            if len(text) <= 2 and not re.search(r"[A-Za-z0-9]{2,}", text):
                continue
        kept.append(element)
    scene.elements = kept
    return scene


def drop_text_backplates(scene: Scene) -> Scene:
    text_boxes = [element.bbox for element in scene.elements if element.type == "text"]
    kept: list[SceneElement] = []
    for element in scene.elements:
        if element.type != "rect":
            kept.append(element)
            continue
        x, y, width, height = element.bbox
        remove = False
        for tx, ty, tw, th in text_boxes:
            intersection_width = max(0.0, min(x + width, tx + tw) - max(x, tx))
            intersection_height = max(0.0, min(y + height, ty + th) - max(y, ty))
            text_area = max(1.0, tw * th)
            rect_area = max(1.0, width * height)
            if (
                intersection_width * intersection_height / text_area >= 0.7
                and rect_area / text_area <= 2.5
                and width >= 2.5 * height
            ):
                remove = True
                break
            text_element = next(
                (
                    candidate
                    for candidate in scene.elements
                    if candidate.type == "text" and candidate.bbox == (tx, ty, tw, th)
                ),
                None,
            )
            if (
                text_element is not None
                and ty <= y + height / 2.0 <= ty + th
                and tx <= x
                and x + width <= tx + tw
                and height <= 1.6 * th
                and width >= 2.5 * height
                and _color_distance(element.style.get("fill"), text_element.style.get("fill")) <= 45.0
            ):
                remove = True
                break
        if not remove:
            kept.append(element)
    scene.elements = kept
    return scene


def deduplicate_scene(scene: Scene, *, iou_threshold: float = 0.5) -> Scene:
    """Keep a single copy of each construction across overlapping layers."""
    kept: list[SceneElement] = []
    for element in scene.elements:
        category = _category(element)
        if category == "other":
            kept.append(element)
            continue
        replaced = False
        for index, other in enumerate(kept):
            if _category(other) != category:
                continue
            element_area = max(1.0, element.bbox[2] * element.bbox[3])
            other_area = max(1.0, other.bbox[2] * other.bbox[3])
            if min(element_area, other_area) / max(element_area, other_area) < 0.72:
                continue
            if _iou(other.bbox, element.bbox) < iou_threshold:
                continue
            if _richness(element) > _richness(other):
                kept[index] = element
            replaced = True
            break
        if not replaced:
            kept.append(element)
    scene.elements = kept
    return scene
