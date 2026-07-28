from __future__ import annotations

from modules.magnetic.readers.boundary_reader import MagneticBoundaryReader


def test_boundary_reader_reads_kml_polygon(tmp_path):
    path = tmp_path / "boundary.kml"
    path.write_text(
        """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
        <kml xmlns=\"http://www.opengis.net/kml/2.2\"><Document><Placemark><Polygon>
        <outerBoundaryIs><LinearRing><coordinates>
        73.0,34.0,0 73.1,34.0,0 73.1,34.1,0 73.0,34.1,0 73.0,34.0,0
        </coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark></Document></kml>""",
        encoding="utf-8",
    )
    boundary = MagneticBoundaryReader().read(path)
    assert boundary.vertices.shape == (5, 2)
    assert boundary.crs == "EPSG:4326"
