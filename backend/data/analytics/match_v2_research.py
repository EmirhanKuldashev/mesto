"""Explicit offline personalization experiment. Never imported by API handlers.

Export uses the existing Local service in a read-only repeatable-read transaction.
Analysis requires numpy/scipy as offline tools only, not runtime dependencies.
"""
import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path

KEYS = ('stop_availability', 'school', 'kindergarten', 'healthcare', 'parks')
PERSONAS = {'Family': (1,3,3,2,2), 'Transport': (3,0,0,1,1),
            'Parks': (1,0,0,1,3), 'Healthcare': (1,0,0,3,1),
            'Education': (1,3,3,0,1), 'Balanced': (2,2,2,2,2)}


def strict_reversals(objective, values):
    """Count strictly reversed candidate pairs; exclude ties on either side.

    Inputs here are ranking-only numerical tie values, not modified utilities.
    Fenwick prefix counts make the exhaustive grid experiment O(P*N*log(N)).
    """
    from bisect import bisect_left
    order=sorted(range(len(objective)),key=lambda i:-objective[i])
    levels=sorted(set(values));positions=[bisect_left(levels,values[i]) for i in order]
    tree=[0]*(len(levels)+1);count=0;offset=0
    while offset<len(order):
        end=offset+1
        while end<len(order) and objective[order[end]]==objective[order[offset]]:end+=1
        for pos in positions[offset:end]:
            idx=pos;subtotal=0
            while idx:subtotal+=tree[idx];idx-=idx&-idx
            count+=subtotal
        for pos in positions[offset:end]:
            idx=pos+1
            while idx<len(tree):tree[idx]+=1;idx+=idx&-idx
        offset=end
    return count


def export():
    from sqlalchemy import select, text
    from sqlalchemy.orm import Session
    from app import models
    from app.db import create_session_factory
    from app.analytics.local.models import LocalRequest
    from app.analytics.local.service import LocalAnalyticsService
    from app.analytics.school.sampling import district_grid_250
    _, engine = create_session_factory()
    try:
        with engine.connect().execution_options(isolation_level='REPEATABLE READ', postgresql_readonly=True) as conn:
            with conn.begin(), Session(bind=conn) as session:
                assert session.scalar(text('SHOW transaction_read_only')) == 'on'
                service = LocalAnalyticsService(session)
                districts = dict(session.execute(select(models.District.id, models.District.slug).where(models.District.source_id=='osm')).all())
                grid = district_grid_250(session, list(districts), reference=service.contracts['school'][2].reference)
                assert all(g.unavailable_reason is None for g in grid)
                points = [{'id': f'{districts[g.district_id]}:{s.cell_x}:{s.cell_y}', **s.coordinate.model_dump()} for g in grid for s in g.samples]
                candidates = [dict(r) for r in session.execute(text("""SELECT external_id AS id,name,ST_Y(location) latitude,
                    ST_X(location) longitude,price_from::float,source_version,fetched_at::text
                    FROM residential_complexes WHERE source_id='cian' AND NOT is_synthetic ORDER BY external_id""")).mappings()]
                assert len(points)==6065 and len(candidates)==108
                for sample in (points,candidates):
                    results = service.points([LocalRequest(latitude=p['latitude'],longitude=p['longitude']) for p in sample])
                    for row, result in zip(sample,results,strict=True):
                        row['availability'] = result.availability
                        row['utilities'] = [result.components[k].score for k in KEYS]
                        row['objective'] = result.score
                        row['unavailable_reason'] = result.unavailable_reason
                return {'version':'match-v2-local-research-v1','read_only':True,'keys':KEYS,
                    'references':{k: {'id':v[0].REFERENCE_ID,'sha256':v[0].REFERENCE_SHA256} for k,v in service.contracts.items()},
                    'grid':points,'cian':candidates,'cian_coordinate_semantics':'source/map anchor; not verified building/entrance ground truth'}
    finally:
        engine.dispose()


def analyze(rows):
    import numpy as np
    from scipy.stats import kendalltau
    profiles = list(itertools.product(range(4),repeat=5))[1:]
    ready = sorted((r for r in rows if r['availability']=='AVAILABLE'),key=lambda r:r['id'])
    assert len(ready)==len(rows), 'Do not silently remove unavailable candidates'
    utilities = np.array([r['utilities'] for r in ready])
    scores = []
    # Reduce proportional profiles before arithmetic: they must yield identical ranks.
    for weights in profiles:
        divisor=math.gcd(*weights)
        weights=tuple(w//divisor for w in weights)
        scores.append([math.fsum(w*u for w,u in zip(weights,row,strict=True))/sum(weights) for row in utilities])
    scores=np.array(scores)
    ranking_scores=np.round(scores,10)  # numerical tie handling only; utilities/output scores untouched
    ranks=np.argsort(-ranking_scores,axis=1,kind='stable')
    sets={n:[frozenset(r[:n]) for r in ranks] for n in (10,20)}
    overlaps={n:np.array([len(a & b)/n for i,a in enumerate(sets[n]) for b in sets[n][i+1:]]) for n in sets}
    objective=np.array([r['objective'] for r in ready])
    objective_ranking_scores=np.round(objective,10)
    objective_rank=np.argsort(-objective_ranking_scores,kind='stable')
    personas={}
    for name,weights in PERSONAS.items():
        index=profiles.index(weights)
        ranking=ranks[index]
        personas[name]={'weights':weights,'top10':[{'id':ready[i]['id'],'name':ready[i].get('name'),
            'score':float(scores[index,i]),'objective':float(objective[i]),'utilities':ready[i]['utilities']} for i in ranking[:10]],
            'objective_top10_overlap':len(set(ranking[:10]) & set(objective_rank[:10]))/10,
            'kendall_tau_b_vs_objective':float(kendalltau(ranking_scores[index],objective_ranking_scores).statistic),
            'score_quantiles':{str(q):float(np.quantile(scores[index],q)) for q in (0,.1,.5,.9,1)}}
    edges=[]
    for i,p in enumerate(profiles):
        for k in range(5):
            if p[k]<3:
                changed=list(p);changed[k]+=1
                j=profiles.index(tuple(changed))
                edges.append((i,j,k))
    sensitivity={KEYS[k]:{'mean_absolute_score_change':float(np.mean([np.mean(abs(scores[i]-scores[j])) for i,j,c in edges if c==k])),
        'mean_top10_retained_fraction':float(np.mean([len(sets[10][i]&sets[10][j])/10 for i,j,c in edges if c==k]))} for k in range(5)}
    reversals=np.array([strict_reversals(objective_ranking_scores.tolist(),s.tolist()) for s in ranking_scores])
    if len(rows)==108:
        # Independent quadratic audit is affordable for the residential sample.
        objective_pairs=objective_ranking_scores[:,None]-objective_ranking_scores[None,:]
        independent=[np.count_nonzero((objective_pairs*(s[:,None]-s[None,:]))<0)//2 for s in ranking_scores]
        assert np.array_equal(reversals,independent)
    quantiles=lambda x:{str(q):float(np.quantile(x,q)) for q in (0,.1,.5,.9,1)}
    corr=np.corrcoef(utilities,rowvar=False)
    all_top=set().union(*sets[10])
    return {'count':len(rows),'available':len(ready),'profiles':len(profiles),
        'distinct_full_rankings':len({r.tobytes() for r in ranks}),
        'distinct_top10_orderings':len({r[:10].tobytes() for r in ranks}),
        'distinct_top10_sets':len(set(sets[10])),'distinct_top20_sets':len(set(sets[20])),
        'top10_candidate_union_count':len(all_top),'top20_candidate_union_count':len(set().union(*sets[20])),
        'candidates_in_every_top10':[ready[i]['id'] for i in sorted(set.intersection(*(set(s) for s in sets[10])))],
        'distinct_top1_candidates':len(set(ranks[:,0])),
        'top1_exhaustive_profile_counts':{ready[i]['id']:int(sum(ranks[:,0]==i)) for i in sorted(set(ranks[:,0]))},
        'pairwise_topN_overlap_quantiles':{str(n):quantiles(v) for n,v in overlaps.items()},
        'strict_pair_reversals_vs_objective':{'quantiles':quantiles(reversals),'denominator_all_candidate_pairs':len(rows)*(len(rows)-1)//2,
            'profiles_with_any_reversal':int(sum(reversals>0))},
        'reversal_audit':'independent quadratic pair comparison matched all 1023 profiles' if len(rows)==108 else 'Fenwick counter with independently tested tie rules',
        'one_step_importance_change':{'edge_count':len(edges),'top10_overlap_quantiles':quantiles([len(sets[10][i]&sets[10][j])/10 for i,j,k in edges])},
        'fit_distribution_all_profile_candidate_pairs':quantiles(scores),
        'component_correlations':corr.tolist(),'mean_pairwise_component_pearson':float(np.mean(corr[np.triu_indices(5,1)])),
        'factor_sensitivity':sensitivity,'personas':personas,
        'persona_pairwise_top10_overlap':{f'{a}/{b}':len({r['id'] for r in personas[a]['top10']} & {r['id'] for r in personas[b]['top10']})/10 for a,b in itertools.combinations(PERSONAS,2)},
        'objective_top10':[{'id':ready[i]['id'],'name':ready[i].get('name'),'score':float(objective[i])} for i in objective_rank[:10]],
        'tie_policy':'Rank comparison only: round to 10 decimal places to suppress floating-point pseudo-reversals, then stable source-ID. Full-precision utilities and reported scores unchanged.',
        'top10_boundary_tie_profile_count':int(sum(ranking_scores[i,r[9]]==ranking_scores[i,r[10]] for i,r in enumerate(ranks))),
        'pareto_undominated_ids':([ready[i]['id'] for i,row in enumerate(utilities)
            if not any(np.all(other>=row) and np.any(other>row) for other in utilities)] if len(rows)==108 else None)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--export',action='store_true')
    parser.add_argument('--input',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.export:result=export()
    else:
        raw=args.input.read_bytes();data=json.loads(raw)
        result={'version':data['version'],'input_sha256':hashlib.sha256(raw).hexdigest(),'references':data['references'],
            'grid':analyze(data['grid']),'cian':analyze(data['cian']),
            'limitations':['Exhaustive profile frequencies are not user probabilities.',
                'Importance 0..3 is an unvalidated product hypothesis.',data['cian_coordinate_semantics'],
                'No user validation; candidate sample is exploratory; no housing quality inference.']}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    print('wrote',args.output)


if __name__=='__main__':main()
