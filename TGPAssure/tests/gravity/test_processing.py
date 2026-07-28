from pathlib import Path
import numpy as np
from modules.gravity.constants import RAW_GRAVITY, TIDE_CORRECTION, TERRAIN_CORRECTION, COMPLETE_BOUGUER_ANOMALY
from modules.gravity.gravity_processing_engine import GravityProcessingEngine
from modules.gravity.models import GravityDataRole, GravityDataset, GravitySurveyType


def test_standard_reduction_preserves_raw_and_creates_bouguer_channels(tmp_path: Path):
    n=10; t=np.datetime64("2026-01-01","ms")+np.arange(n)*np.timedelta64(1,"m")
    obs=GravityDataset(tmp_path/"obs.csv",GravityDataRole.OBSERVATIONS,GravitySurveyType.LAND,t,{RAW_GRAVITY:np.ones(n)*978000,TIDE_CORRECTION:np.zeros(n),TERRAIN_CORRECTION:np.ones(n)*0.2},latitude=np.ones(n)*33.7,longitude=np.linspace(73,73.01,n),elevation=np.ones(n)*600)
    base=GravityDataset(tmp_path/"base.csv",GravityDataRole.BASE,GravitySurveyType.BASE_STATION,np.array([t[0],t[-1]]),{RAW_GRAVITY:np.array([978000,978000.01])},latitude=np.ones(2)*33.7,longitude=np.ones(2)*73,elevation=np.ones(2)*600,is_base=np.ones(2,bool))
    raw=obs.channel(RAW_GRAVITY).copy()
    GravityProcessingEngine().run_standard_reduction(obs,base=base)
    assert np.array_equal(raw,obs.channel(RAW_GRAVITY))
    assert COMPLETE_BOUGUER_ANOMALY in obs.channels
