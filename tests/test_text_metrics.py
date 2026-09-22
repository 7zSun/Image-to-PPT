from image2svg.core.scene import Scene, SceneElement
from image2svg.reconstruct.text_metrics import (
    avoid_text_graphics,
    fit_text_element,
    fit_text_to_box,
    fit_text_to_boxes,
)


def test_fit_text_to_box_uses_available_width() -> None:
    wide, _baseline, _measured = fit_text_to_box(
        "Coordinate aware text",
        300,
        40,
        font_family="Arial",
    )
    narrow, _baseline, measured = fit_text_to_box(
        "Coordinate aware text",
        120,
        40,
        font_family="Arial",
    )

    assert narrow < wide
    assert measured <= 120 * 0.92


def test_fit_text_element_keeps_ocr_coordinates() -> None:
    element = SceneElement(
        id="ocr",
        type="text",
        bbox=(17.0, 23.0, 96.0, 21.0),
        text="Editable label",
        style={"font-family": "Arial", "font-weight": "bold"},
    )

    fit_text_element(element)

    assert element.bbox == (17.0, 23.0, 96.0, 21.0)
    assert element.style["fit-to-box"] is True
    assert element.style["measured-width"] <= 96 * 0.92


def test_fit_text_to_boxes_only_updates_opted_in_text() -> None:
    fitted = SceneElement(
        id="ocr",
        type="text",
        bbox=(10, 10, 80, 20),
        text="OCR label",
        style={"font-size": 99, "font-family": "Arial", "fit-to-box": True},
    )
    authored = SceneElement(
        id="authored",
        type="text",
        bbox=(10, 40, 80, 20),
        text="Authored label",
        style={"font-size": 24, "font-family": "Arial"},
    )
    scene = Scene(width=200, height=100, elements=[fitted, authored])

    fit_text_to_boxes(scene)

    assert fitted.style["font-size"] < 99
    assert authored.style["font-size"] == 24


def test_avoid_text_graphics_moves_overlapping_lines_as_a_group() -> None:
    first = SceneElement(
        id="line-1",
        type="text",
        bbox=(60, 45, 80, 20),
        text="First line",
        style={"fit-to-box": True},
    )
    second = SceneElement(
        id="line-2",
        type="text",
        bbox=(70, 62, 60, 18),
        text="Second",
        style={"fit-to-box": True},
    )
    scene = Scene(
        width=400,
        height=300,
        elements=[
            SceneElement(id="card", type="rect", bbox=(40, 10, 120, 110)),
            SceneElement(id="icon", type="image", bbox=(75, 20, 50, 50)),
            first,
            second,
        ],
    )

    avoid_text_graphics(scene)

    assert first.bbox[1] > 70
    assert second.bbox[1] - first.bbox[1] == 17
    assert first.bbox[0] == 60
    assert first.style["graphic-avoidance-dy"] == second.style["graphic-avoidance-dy"]


def test_avoid_text_graphics_does_not_move_text_without_shared_container() -> None:
    text = SceneElement(
        id="label",
        type="text",
        bbox=(60, 45, 80, 20),
        text="Label",
    )
    scene = Scene(
        width=300,
        height=200,
        elements=[
            SceneElement(id="icon", type="group", bbox=(75, 20, 50, 50)),
            text,
        ],
    )

    avoid_text_graphics(scene)

    assert text.bbox == (60, 45, 80, 20)


def test_avoid_text_graphics_includes_adjacent_non_overlapping_lines() -> None:
    first = SceneElement(id="first", type="text", bbox=(210, 90, 70, 20), text="First")
    second = SceneElement(id="second", type="text", bbox=(215, 111, 65, 20), text="Second")
    third = SceneElement(id="third", type="text", bbox=(212, 133, 68, 20), text="Third")
    scene = Scene(
        width=500,
        height=300,
        elements=[
            SceneElement(id="card", type="rect", bbox=(180, 40, 130, 150)),
            SceneElement(id="icon", type="image", bbox=(200, 60, 50, 50)),
            first,
            second,
            third,
        ],
    )

    avoid_text_graphics(scene)

    assert first.bbox[1] > 110
    assert second.bbox[1] - first.bbox[1] == 21
    assert third.bbox[1] - second.bbox[1] == 22
    assert first.style["graphic-avoidance-dy"] == third.style["graphic-avoidance-dy"]


def test_avoid_text_graphics_moves_side_label_horizontally() -> None:
    label = SceneElement(
        id="label",
        type="text",
        bbox=(136, 72, 100, 24),
        text="Side label",
    )
    scene = Scene(
        width=400,
        height=240,
        elements=[
            SceneElement(id="card", type="rect", bbox=(60, 40, 240, 100)),
            SceneElement(id="icon", type="path", bbox=(90, 60, 50, 50)),
            label,
        ],
    )

    avoid_text_graphics(scene)

    assert label.bbox[0] > 140
    assert label.bbox[1] == 72
    assert label.style["graphic-avoidance-dx"] > 0
