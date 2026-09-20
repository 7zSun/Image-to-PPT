"""Optional AI adapters (SAM3, OCR) and their bridge scripts.

The bridge scripts in ``image2svg.ai.scripts`` run inside the dedicated AI
environment (torch / sam3 / paddleocr) and are invoked through a subprocess so
the lightweight conversion pipeline never imports heavy dependencies.
"""
