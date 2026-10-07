"""Offline read-only Local parity/performance/RC audit; never an API code path.

DATABASE_URL must point to the database being verified. No migrations, bootstrap,
collection or writes to it. Optional --output stores the verification artifact.
"""
import argparse
import json
import math
import statistics as st
import time
from pathlib import Path

from sqlalchemy import event, select, text
from sqlalchemy.orm import Session

from app import models
from app.analytics.local.models import LocalRequest
from app.analytics.local.service import LocalAnalyticsService
from app.analytics.objective.engine import WEIGHTS
from app.analytics.objective.provider import ObjectiveProvider, read_precomputed
from app.analytics.school.sampling import district_grid_250
from app.db import create_session_factory


def verify(session):
    artifact = read_precomputed()
    service = LocalAnalyticsService(session)
    ids = dict(session.execute(select(models.District.id,models.District.slug).where(models.District.source_id=='osm')).all())
    before = ObjectiveProvider(session).districts(list(ids))
    assert len(before) == 7 and all(r.availability == 'AVAILABLE' for r in before.values())
    queries = []
    def capture(*args):queries.append(args[2])
    conn = session.connection()
    durations = []
    point = LocalRequest(latitude=56.01,longitude=92.85)
    for _ in range(5):
        queries.clear()
        event.listen(conn,'before_cursor_execute',capture)
        started = time.perf_counter()
        try:example = LocalAnalyticsService(session).point(point)
        finally:event.remove(conn,'before_cursor_execute',capture)
        durations.append(time.perf_counter()-started)
        assert example.availability == 'AVAILABLE' and len(queries) == 7
        assert all('generate_series' not in q for q in queries)
    grid = district_grid_250(session,list(ids),reference=service.contracts['school'][2].reference)
    samples = [(ids[g.district_id],s) for g in grid for s in g.samples]
    assert len(samples) == 6065 and all(g.unavailable_reason is None for g in grid)
    started = time.perf_counter()
    results = service.points([LocalRequest(**s.coordinate.model_dump()) for _,s in samples])
    batch_seconds = time.perf_counter()-started
    assert len(results) == 6065 and all(r.availability == 'AVAILABLE' for r in results)
    parity = []
    differences = {}
    for ident,slug in ids.items():
        rows = [r for r,(s,_) in zip(results,samples) if s == slug]
        means = {key:st.mean(r.components[key].score for r in rows) for key in WEIGHTS}
        for key,mean in means.items():
            assert math.isclose(mean,artifact['districts'][slug]['components'][key]['score'],rel_tol=0,abs_tol=1e-12)
        composite = st.mean(r.score for r in rows)
        expected_full = math.fsum(.2*artifact['districts'][slug]['components'][key]['score'] for key in WEIGHTS)
        assert math.isclose(composite,expected_full,rel_tol=0,abs_tol=1e-12)
        assert round(composite,2) == before[ident].score
        parity.append({'district':slug,'samples':len(rows),**means,'local_objective_mean':composite,
            'objective_reproduced':round(composite,2),'expected_objective':before[ident].score})
        lo,hi = min(rows,key=lambda r:r.score),max(rows,key=lambda r:r.score)
        differences[slug] = {'min':lo.score,'max':hi.score,'median':st.median(r.score for r in rows),
            'lowest':lo.model_dump(mode='json'),'highest':hi.model_dump(mode='json')}
    assert ObjectiveProvider(session).districts(list(ids)) == before
    rc = list(session.execute(text("""SELECT source_id,is_synthetic,count(*) total,
      count(*) FILTER(WHERE location IS NOT NULL AND ST_SRID(location)=4326 AND NOT ST_IsEmpty(location)
        AND ST_IsValid(location) AND ST_X(location) BETWEEN -180 AND 180 AND ST_Y(location) BETWEEN -90 AND 90) valid_coordinates,
      count(*) FILTER(WHERE location IS NULL) missing_coordinates
      FROM residential_complexes GROUP BY source_id,is_synthetic ORDER BY source_id,is_synthetic""")).mappings())
    utilities = [r.score for r in results]
    spread = [max(c.score for c in r.components.values())-min(c.score for c in r.components.values()) for r in results]
    return {'version':'local-objective-v1','snapshot':artifact['snapshot'],'database_read_only':True,
        'point_performance':{'samples_seconds':durations,'median_seconds':st.median(durations),'sql_count':7,
            'includes_service_initialization':True},'batch_seconds':batch_seconds,'grid_count':len(results),
        'district_parity':parity,'local_distribution':{'min':min(utilities),'max':max(utilities),'median':st.median(utilities),
            'mean':st.mean(utilities),'std':st.pstdev(utilities)},
        'component_spread':{'min':min(spread),'max':max(spread),'median':st.median(spread)},
        'within_district':differences,'result_example':example.model_dump(mode='json'),
        'parks_inside_example':next(r.model_dump(mode='json') for r in results if r.components['parks'].inside_geometry),
        'residential_complexes':[dict(r) for r in rc],
        'rc_integration':False,'rc_coordinate_semantics':'portal_map_anchor_not_verified_building_or_entrance'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path)
    args = parser.parse_args()
    _,engine = create_session_factory()
    try:
        with engine.connect().execution_options(isolation_level='REPEATABLE READ',postgresql_readonly=True) as conn:
            with conn.begin(),Session(bind=conn) as session:
                assert session.scalar(text('SHOW transaction_read_only')) == 'on'
                report = verify(session)
    finally:engine.dispose()
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('within_district','parks_inside_example','result_example')},indent=2))


if __name__ == '__main__':main()
