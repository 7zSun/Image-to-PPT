from image2svg.svg.audit import audit_svg


def test_audit_accepts_basic_svg() -> None:
    result = audit_svg(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
        '<rect x="10" y="10" width="80" height="80"/>'
        '</svg>'
    )
    assert result.valid_xml
    assert result.has_viewbox
    assert result.embedded_raster_count == 0
    assert result.external_resource_count == 0
    assert result.path_count == 0


def test_audit_detects_embedded_raster() -> None:
    result = audit_svg(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
        '<image href="data:image/png;base64,AAAA" width="10" height="10"/>'
        '</svg>'
    )
    assert result.embedded_raster_count == 1


def test_audit_rejects_invalid_xml() -> None:
    result = audit_svg('<svg viewBox="0 0 10 10">')
    assert not result.valid_xml
    assert result.errors
