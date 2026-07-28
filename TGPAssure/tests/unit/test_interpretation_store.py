from core.data_access.db_engine import DatabaseEngine
from modules.seismic.interpretation_store import SeismicInterpretationStore


def test_picks_and_horizons_are_persisted(tmp_path) -> None:
    store = SeismicInterpretationStore(DatabaseEngine(tmp_path / 'project.db'))
    store.save_manual_pick(2, 100, 0.5, {'author': 'tester'})
    store.save_horizon('H1', [{'trace_index': 2, 'sample_index': 100}, {'trace_index': 1, 'sample_index': 90}])
    picks = store.list_interpretations('first_break_pick')
    horizons = store.list_interpretations('reflection_horizon')
    assert picks[0]['payload']['time_ms'] == 50.0
    assert horizons[0]['payload']['points'][0]['trace_index'] == 1
