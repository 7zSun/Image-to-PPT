from __future__ import annotations

from image2svg.core.scene import Scene, SceneElement

BBox = tuple[float, float, float, float]


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
            normalized = element.text.strip().lower()
            duplicate = False
            for other in kept:
                if other.type == "text" and other.text:
                    same = other.text.strip().lower() == normalized
                    if same and _iou(other.bbox, element.bbox) >= iou_threshold:
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
            if duplicate:
                continue
        kept.append(element)
    scene.elements = kept
    return scene


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
    score = 0
    if style.get("stroke"):
        score += 2
    if style.get("fill"):
        score += 1
    if element.type == "image":
        score += 1
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
