from pathlib import Path
import time

import numpy as np

from modules.magnetic.enmag_qc.gridding import grid_surface, make_color_range, robust_range
from modules.magnetic.enmag_qc.models import EnMagQcData
from modules.magnetic.enmag_qc.spatial import CoordinateIndex, apply_polygon_filter, polygon_inside_mask
from modules.magnetic.models import MagneticDataRole, MagneticDataset, MagneticSurveyType


def _dataset(n=1000):
    t=np.arange(n,dtype='int64').astype('datetime64[ms]')
    x=np.linspace(64.0,64.2,n)
    y=29.5+0.03*np.sin(np.linspace(0,8*np.pi,n))
    mag=47000+50*np.sin(np.linspace(0,20*np.pi,n))
    q=np.ones(n)
    q[10]=0
    flags=np.zeros(n,dtype=bool); flags[20]=True
    return MagneticDataset(
        source_path=Path('Acqu025.txt'), role=MagneticDataRole.ROVER, survey_type=MagneticSurveyType.GROUND,
        timestamps=t, channels={'total_field_raw':mag,'gps_quality':q,'heading':np.mod(np.linspace(350,370,n),360)},
        x=x,y=y,elevation=np.linspace(1200,1300,n), line_id=np.full(n,'L1',object), station_id=np.arange(n).astype(str),
        metadata={'parse_report':{'total_records':2*n+12,'gps_points':n+2}}, crs='EPSG:4326', coordinate_units='degrees',
        quality_flags={'sensor_validation_bad':flags,'gps_invalid_fix':q<=0},
    )


def test_counts_and_visibility_are_distinct():
    data=EnMagQcData.from_dataset(_dataset(100))
    assert data.raw_records==212
    assert data.gps_records==102
    assert data.sample_count==100
    assert np.count_nonzero(data.visible_mask())==98
    assert np.count_nonzero(data.visible_mask(include_invalid=True))==100


def test_fast_grid_is_radius_limited_and_north_up():
    ds=_dataset(1000); data=EnMagQcData.from_dataset(ds); mask=data.visible_mask()
    idx=np.flatnonzero(mask)
    result=grid_surface(data.x[mask],data.y[mask],data.magnetic_nt[mask],idx,cols=64,rows=64,point_radius=2.2,method='Fast Grid',idw_power=.7)
    assert result.values.shape==(64,64)
    assert np.any(np.isfinite(result.values))
    assert np.any(~np.isfinite(result.values))  # no full-bounds extrapolation
    assert result.y_coordinates[0] > result.y_coordinates[-1]


def test_idw_grid_is_vectorized_and_finite_near_track():
    ds=_dataset(3000); data=EnMagQcData.from_dataset(ds); mask=data.visible_mask(); idx=np.flatnonzero(mask)
    result=grid_surface(data.x[mask],data.y[mask],data.magnetic_nt[mask],idx,cols=80,rows=70,point_radius=4.0,method='IDW',idw_power=.7)
    assert result.values.shape==(70,80)
    assert np.count_nonzero(np.isfinite(result.values))>100


def test_heading_idw_wraps_359_to_zero_correctly():
    x=np.array([0.,1.]); y=np.array([0.,0.]); h=np.array([359.,1.]); idx=np.array([0,1])
    result=grid_surface(x,y,h,idx,cols=3,rows=2,point_radius=10,method='IDW',idw_power=1,circular=True)
    middle=result.values[:,1]
    assert np.all((middle<5)|(middle>355))


def test_manual_color_range_rejects_blank_and_bad_order():
    v=np.array([1.,2.,3.,100.])
    lo,hi=robust_range(v)
    assert 1<=lo<hi<=100
    try:
        make_color_range(v,'Manual',None,None,unit='nT')
        assert False
    except ValueError:
        pass
    try:
        make_color_range(v,'Manual',10,5,unit='nT')
        assert False
    except ValueError:
        pass


def test_polygon_filter_vectorized():
    x=np.array([0.,1.,2.,3.]); y=np.array([0.,1.,2.,3.]); vertices=np.array([[-1,-1],[2.2,-1],[2.2,2.2],[-1,2.2]])
    inside=polygon_inside_mask(x,y,vertices)
    assert inside.tolist()==[True,True,True,False]
    base=np.ones(4,dtype=bool)
    assert apply_polygon_filter(base,inside,'keep').tolist()==[True,True,True,False]
    assert apply_polygon_filter(base,inside,'ignore').tolist()==[False,False,False,True]


def test_kdtree_distance_is_metric_for_lat_lon():
    idx=CoordinateIndex(np.array([64.0,64.001]),np.array([29.0,29.0]),geographic=True,coordinate_units='degrees')
    q=idx.query(64.0005,29.0)
    assert q is not None
    _,distance,unit=q
    assert unit=='m'
    assert 40 < distance < 60


def test_fast_grid_50k_default_is_fast():
    n=50_000
    rng=np.random.default_rng(42)
    t=np.linspace(0,1,n)
    x=64.0+0.2*t+0.001*rng.normal(size=n)
    y=29.0+0.05*np.sin(12*np.pi*t)+0.001*rng.normal(size=n)
    z=47000+100*np.sin(30*np.pi*t)+rng.normal(0,2,n)
    source=np.arange(n)
    start=time.perf_counter()
    result=grid_surface(x,y,z,source,cols=64,rows=64,point_radius=2.2,method='Fast Grid',idw_power=.7)
    elapsed=time.perf_counter()-start
    assert np.any(np.isfinite(result.values))
    assert elapsed < 2.0


def test_enmag_event_log_exposes_reference_counts(tmp_path):
    from modules.magnetic.reader import MagneticReader
    path=tmp_path/'Acqu025.txt'
    path.write_text(
        'sensor_validation_good_char=_\n'
        '@GPS,PPS=Y,2026-08-12T05:00:00Z,29.400000,64.400000,1270,0.8,12,1,42\n'
        '!47169.1_@1s4,bno=40\n'
        '!47170.2_@2s4,bno=41\n'
        '@GPS,PPS=Y,2026-08-12T05:00:01Z,29.400010,64.400010,1271,0.8,12,1,43\n'
        '!47171.3*@3s4,bno=42\n'
        '@GPS,PPS=Y,2026-08-12T05:00:02Z,29.400020,64.400020,1272,0.8,12,1,44\n',
        encoding='utf-8'
    )
    ds=MagneticReader().read_rover(path)
    data=EnMagQcData.from_dataset(ds)
    assert data.raw_records==7
    assert data.gps_records==3
    assert data.sample_count==3
    assert np.count_nonzero(data.visible_mask())==2
    assert np.count_nonzero(data.visible_mask(include_invalid=True))==3
