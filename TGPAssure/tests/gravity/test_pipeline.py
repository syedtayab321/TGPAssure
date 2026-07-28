from pathlib import Path
import numpy as np
from modules.gravity.constants import RAW_GRAVITY,TIDE_CORRECTION,TERRAIN_CORRECTION
from modules.gravity.context import GravityQcContext
from modules.gravity.gravity_engine import GravityQcPipeline
from modules.gravity.gravity_profiles import get_profile
from modules.gravity.models import GravityDataRole, GravityDataset, GravitySurveyType


def test_full_pipeline_executes_all_stages(tmp_path: Path):
    n=20; t=np.datetime64("2026-01-01","ms")+np.arange(n)*np.timedelta64(2,"m")
    obs=GravityDataset(tmp_path/"obs.csv",GravityDataRole.OBSERVATIONS,GravitySurveyType.LAND,t,{RAW_GRAVITY:978000+np.arange(n)*0.001,TIDE_CORRECTION:np.zeros(n),TERRAIN_CORRECTION:np.ones(n)*0.2},latitude=np.ones(n)*33.7,longitude=73+np.arange(n)*0.0001,elevation=np.ones(n)*600,station_id=np.array([f"S{i}" for i in range(n)],object),line_id=np.array(["L1"]*n,object))
    base=GravityDataset(tmp_path/"base.csv",GravityDataRole.BASE,GravitySurveyType.BASE_STATION,np.array([t[0],t[-1]]),{RAW_GRAVITY:np.array([978000,978000.01])},latitude=np.ones(2)*33.7,longitude=np.ones(2)*73,elevation=np.ones(2)*600,is_base=np.ones(2,bool))
    result=GravityQcPipeline().run(GravityQcContext(obs,base,profile_name="standard",thresholds=get_profile("standard")))
    assert len(result.stage_outcomes)==16
    assert "simple_bouguer_anomaly_mgal" in obs.channels
