"""Convert analyzer observations into an editable Scene IR."""

from image2svg.reconstruct.generate import SvgGenerator, generated_element
from image2svg.reconstruct.router import classify_instance
from image2svg.reconstruct.segments import scene_from_segmentation
from image2svg.reconstruct.text import scene_from_ocr

__all__ = [
    "SvgGenerator",
    "classify_instance",
    "generated_element",
    "scene_from_ocr",
    "scene_from_segmentation",
]
