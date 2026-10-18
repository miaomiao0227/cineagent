"""Online/offline input parity regression for the actual upstream services."""
import asyncio,json,numpy as np
from pathlib import Path
from app.database import SessionLocal
from app.models import Movie
from app.api.v1.endpoints.recommendations import UserFeaturesRequest,enrich_user_features,get_item_features
from online.pipeline import get_pipeline
from online.recall.youtubednn import YouTubeDNNRecallStrategy
from online.ranking.deepfm import DeepFMRankingStrategy
root=Path('/artifacts/rec_v1');meta=json.loads((root/'metadata.json').read_text());v=json.loads((root/'retrieval_vocab.json').read_text());tables=dict(np.load(root/'feature_tables.npz',allow_pickle=False));uid=635
db=SessionLocal()
try:
    pipeline=get_pipeline();pipeline.set_movie_genre_map(db.query(Movie).all());context=asyncio.run(enrich_user_features(UserFeaturesRequest(user_id=uid),db))
    strategy=YouTubeDNNRecallStrategy();actual=strategy.preprocess_user(context)
    for k in ['user_id','gender','age','occupation','zip_code']:np.testing.assert_array_equal(actual[k],[tables['user_'+k][uid]])
    hist=meta['histories'][str(uid)];assert context['hist_movie_ids']==hist
    enc={k:{x:i+1 for i,x in enumerate(a)} for k,a in v.items()};m={x['movie_id']:x for x in meta['movies']}
    expected=[enc['movie_id'][str(x)] for x in hist];expected=[0]*(10-len(expected))+expected;np.testing.assert_array_equal(actual['hist_movie_id'],[expected])
    g=[enc['genres'][g] for x in hist for g in m[x]['genres']][-10:];g=[0]*(10-len(g))+g;np.testing.assert_array_equal(actual['hist_genres'],[g])
    mids=meta['catalog'][:32];item=asyncio.run(get_item_features(mids,db));candidates=[{'movie_id':mid,**item[mid]} for mid in mids]
    rank=DeepFMRankingStrategy();inputs=rank._prepare_batch_inputs(context,candidates)
    for k in ['user_id','gender','age','occupation','zip_code']:np.testing.assert_array_equal(inputs[k],np.full(len(mids),tables['user_'+k][uid]))
    for k in ['movie_id','genres','startYear']:np.testing.assert_array_equal(inputs[k],tables['item_'+k][mids])
    rm=strategy.resource_manager;rm._ensure_resources_loaded();ids=np.load(root/'movie_ids.npy',allow_pickle=False);emb=np.load(root/'item_embeddings.npy',allow_pickle=False);np.testing.assert_array_equal(np.array(rm.all_movie_ids),ids);np.testing.assert_allclose(rm.item_embedding_matrix[1:],emb)
    report={'ok':True,'user_id':uid,'retrieval_input_checks':7,'ranking_input_checks':8,'ranking_candidate_rows_checked':32,'positive_history_order_matches':True,'item_embedding_order_matches':True,'recall_channels':[type(s).__name__ for s in pipeline.recall_service.strategies]}
    (root/'ONLINE_PARITY.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:db.close()
