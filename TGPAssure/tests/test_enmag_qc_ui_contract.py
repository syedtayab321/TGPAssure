from pathlib import Path


def test_enmag_screen_keeps_reference_controls_and_defaults():
    text=Path('modules/magnetic/ui/enmag_data_qc_screen.py').read_text(encoding='utf-8')
    for token in [
        '"Log File"', '"Select Folder"', '"Preview Mode"', '"Grid Cols"', '"Grid Rows"',
        '"Point Radius"', '"IDW Power"', '"Grid Opacity %"', '"Color Scale"', '"Color Min"',
        '"Color Max"', '"Grid Type"', '"Interpolation"', '"Include Invalid Samples"',
        '"Heading Info Export"', '"Pan"', '"Filter"', '"Reset Filter"', '"Draw"', '"Export"',
    ]:
        assert token in text
    assert 'self.grid_cols.setValue(64)' in text
    assert 'self.grid_rows.setValue(64)' in text
    assert 'self.point_radius.setValue(2.2)' in text
    assert 'self.idw_power.setValue(0.7)' in text
    assert 'self.grid_opacity.setRange(0, 100)' in text
    assert '["Robust Auto", "Manual", "Auto"]' in text
    assert '["Fast Grid", "IDW", "Nearest"]' in text


def test_enmag_dashboard_import_path_stays_compatible():
    text=Path('modules/magnetic/ui/magnetic_dashboard.py').read_text(encoding='utf-8')
    assert 'class MagneticDashboard(EnMagDataQcScreen)' in text
