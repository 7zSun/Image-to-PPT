"""Optional AI analyzers. Heavy dependencies stay behind bridge processes."""

from image2svg.analyze.models import (
    OcrResult,
    SegmentationResult,
    SegmentInstance,
    TextRegion,
)
from image2svg.analyze.ocr import OcrAnalyzer, OcrOptions
from image2svg.analyze.omnisvg import OmniSvgGenerator, OmniSvgOptions
from image2svg.analyze.sam3 import Sam3Analyzer, Sam3Options
from image2svg.analyze.starvector import StarVectorGenerator, StarVectorOptions

__all__ = [
    "OcrAnalyzer",
    "OcrOptions",
    "OcrResult",
    "OmniSvgGenerator",
    "OmniSvgOptions",
    "Sam3Analyzer",
    "Sam3Options",
    "SegmentInstance",
    "SegmentationResult",
    "StarVectorGenerator",
    "StarVectorOptions",
    "TextRegion",
]
