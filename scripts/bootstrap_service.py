"""Bootstrap dedicated service from inert JSON + verified numeric train arrays only."""
import os,json,gzip,io,collections,pickle
from pathlib import Path
import numpy as np,pandas as pd,redis
from sqlalchemy import text
from app.database import engine,SessionLocal,init_db
from app.models import User,Movie,Rating
from app.config import settings
from app.core.security import get_password_hash
from scripts import ingest_data_to_database as ingest
from scripts.index_movies_elasticsearch import index_movies
ROOT=Path('/artifacts/rec_v1');DEPLOY=Path('/artifacts/web_project/deployed_models')
assert engine.url.database=='cineagent_db' and engine.url.host=='postgres' and engine.url.username=='cineagent'
meta=json.loads((ROOT/'metadata.json').read_text());train=dict(np.load(ROOT/'train.npz',allow_pickle=False))
with gzip.open('/catalog.safe.json.gz','rt',encoding='utf-8') as f:catalog=json.load(f)
df_movies=pd.DataFrame(catalog['movies']);official={m['movie_id']:m for m in meta['movies']}
for i,row in df_movies.iterrows():
    m=official[int(row.movie_id)];df_movies.loc[i,'title']=m['title'];df_movies.loc[i,'startYear']=None if m['startYear']=='unknown' else m['startYear'];df_movies.loc[i,'genres']='|'.join(m['genres'])
assert len(df_movies)==3883 and not df_movies.movie_id.duplicated().any()
users=pd.DataFrame(meta['users']);frames={k:pd.DataFrame(v) for k,v in catalog['metadata'].items()}
init_db(drop_existing=False)
db=SessionLocal();marker=ROOT/'DB_IMPORTED.json'
try:
    counts={'movies':db.query(Movie).count(),'users':db.query(User).count(),'ratings':db.query(Rating).count()}
    if marker.exists():
        assert counts['movies']==3883 and counts['ratings']==len(train['user_id']),'Existing import does not match marker'
    else:
        assert counts=={'movies':0,'users':0,'ratings':0},'Nonempty database: refusing reset or overwrite'
        title=ingest.ingest_title_ratings(db,frames['title_ratings']);ingest.ingest_users(db,users);ingest.ingest_movies(db,df_movies,title)
        # Preserve original UI 1-10 scale; model labels use official1-5 in separate immutable arrays.
        buf=io.StringIO()
        for u,m,r,t in zip(train['user_id'],train['movie_id'],train['rating'],train['timestamp']):buf.write(f'{int(u)}\t{int(m)}\t{int(r)*2}\t{int(t)}\n')
        buf.seek(0);raw=engine.raw_connection()
        try:
            cur=raw.cursor();cur.copy_expert('COPY ratings (user_id,movie_id,rating,timestamp) FROM STDIN',buf);raw.commit()
        finally:raw.close()
        ingest.update_movie_statistics(db);ingest.ingest_name_basics(db,frames['name_basics']);ingest.ingest_title_crew(db,frames['title_crew']);ingest.ingest_title_principals(db,frames['title_principals']);ingest.ingest_title_akas(db,frames['title_akas']);ingest.ingest_genres(db,df_movies)
        db.execute(text("UPDATE movies SET description=NULL WHERE description IN ('nan','None','\\N')"));db.commit()
        demo_uid=min(int(u) for u,h in meta['histories'].items() if len(h)>=5);demo=db.get(User,demo_uid)
        demo.email='demo@cineagent.local';demo.username='MovieLens demonstration persona';demo.hashed_password=get_password_hash(os.environ['DEMO_PASSWORD']);demo.is_superuser=0;db.commit()
        counts={'movies':db.query(Movie).count(),'users':db.query(User).count(),'ratings':db.query(Rating).count()};assert counts=={'movies':3883,'users':6040,'ratings':800164}
        assert db.execute(text('SELECT max(timestamp) FROM ratings')).scalar()<975768738
        (ROOT/'DB_IMPORTED.json').write_text(json.dumps({'counts':counts,'train_only':True,'ui_rating_scale':'1-10; official rating*2','demo_user_id':demo_uid,'demo_email':'demo@cineagent.local','demo_persona':'historical dataset user, not newly fabricated ratings'}))
finally:db.close()
# Train-boundary positive histories; no FLUSHDB or future interactions.
r=redis.Redis.from_url(settings.redis_url,decode_responses=True);r.ping();pipe=r.pipeline();movies={m['movie_id']:m for m in meta['movies']}
for u in meta['users']:
    uid=u['user_id'];hist=meta['histories'].get(str(uid),[]);all_positive=meta['positive_histories'].get(str(uid),[]);genres=collections.Counter(g for mid in all_positive for g in movies[mid]['genres'])
    profile={k:str(u[k]) for k in ['gender','age','occupation','zip_code']};profile['frequent_genres']=','.join(g for g,n in genres.most_common(3))
    pipe.hset(f'user:{uid}:profile',mapping=profile);pipe.delete(f'user:{uid}:history')
    if hist:pipe.rpush(f'user:{uid}:history',*hist)
    if int(uid)%500==0:pipe.execute()
pipe.execute()
# Tiny trusted vocab artifacts; model active pointers avoid copying model directories.
DEPLOY.mkdir(parents=True,exist_ok=True);(DEPLOY/'ranking').mkdir(exist_ok=True)
for source,dest in [('retrieval_vocab.json',DEPLOY/'vocab_dict.pkl'),('vocab.json',DEPLOY/'ranking/vocab_dict.pkl')]:
    v=json.loads((ROOT/source).read_text());dest.write_bytes(pickle.dumps({k:np.array(a) for k,a in v.items()},protocol=4))
v=json.loads((ROOT/'vocab.json').read_text());(DEPLOY/'ranking/feature_dict.pkl').write_bytes(pickle.dumps({k:len(a)+1 for k,a in v.items()},protocol=4));(DEPLOY/'ranking/model_config.pkl').write_bytes(pickle.dumps({'protocol':'rec-v1','feature_columns':list(v)},protocol=4))
for name in ['item_embeddings.npy','movie_ids.npy']:
    target=DEPLOY/name
    # Arrays are small and required at the upstream loader's fixed location.
    import shutil;shutil.copyfile(ROOT/name,target)
for key,model in [('user_recall','user_model'),('ranking','ranking_model')]:
    folder=DEPLOY/'model'/key;folder.mkdir(parents=True,exist_ok=True);(folder/'active.json').write_text(json.dumps({'version':'rec-v1','path':'../../rec_v1/models/'+model}))
assert index_movies(recreate_index=False,batch_size=1000),'Elasticsearch indexing failed'
report={'ok':True,'database':json.loads(marker.read_text()),'redis_profiles':len(meta['users']),'model_version':'rec-v1','formal_evaluation_route_is_separate_from_online_multichannel':True}
(ROOT/'SERVICE_BOOTSTRAP.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
