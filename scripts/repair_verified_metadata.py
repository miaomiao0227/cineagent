"""Apply verified identity links; never infer unresolved metadata."""
import json
from pathlib import Path
from sqlalchemy import text
from app.database import engine,SessionLocal
from app.models import Movie,TitleRating
assert engine.url.database=='cineagent_db' and engine.url.host=='postgres'
audit=json.loads(Path('/verified-links.json').read_text());valid={int(x['movie_id']):x for x in audit['verified']};assert len({x['imdb_id'] for x in valid.values()})==len(valid)
db=SessionLocal()
try:
    movies=db.query(Movie).all();assert len(movies)==3883
    # Clear stale identities first so swapped/colliding old IDs cannot violate unique constraints.
    for m in movies:
        m.imdb_id=None;m.imdb_rating=None;m.imdb_votes=None
    db.flush()
    quality=[]
    for m in movies:
        v=valid.get(m.movie_id)
        if v:
            m.imdb_id=v['imdb_id'];rating=db.get(TitleRating,v['imdb_id'])
            if rating:m.imdb_rating=rating.average_rating;m.imdb_votes=rating.num_votes
            if v['changed']:m.runtime_minutes=None;m.is_adult=None
            status='identity_verified';reason='Official metadata reference same ID and exact title/year; runtime not independently re-fetched'
        else:
            m.runtime_minutes=None;m.is_adult=None;status='unverified';reason='No exact ID plus title/year confirmation; IMDb attributes withheld'
        quality.append({'movie_id':m.movie_id,'status':status,'source':audit['reference_url'],'reason':reason})
    db.execute(text('CREATE TABLE IF NOT EXISTS movie_metadata_quality (movie_id INTEGER PRIMARY KEY REFERENCES movies(movie_id), status TEXT NOT NULL, source TEXT NOT NULL, reason TEXT NOT NULL)'))
    db.execute(text('INSERT INTO movie_metadata_quality (movie_id,status,source,reason) VALUES (:movie_id,:status,:source,:reason) ON CONFLICT(movie_id) DO UPDATE SET status=EXCLUDED.status,source=EXCLUDED.source,reason=EXCLUDED.reason'),quality)
    db.commit()
    report={'ok':True,'identity_verified':len(valid),'corrected_links':sum(x['changed'] for x in valid.values()),'unverified_attributes_withheld':len(movies)-len(valid),'training_data_or_models_changed':False,'review_source_hash':audit['reference_sha256']}
    Path('/artifacts/rec_v1/METADATA_REPAIR.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:db.close()
from scripts.index_movies_elasticsearch import index_movies
assert index_movies(recreate_index=False,batch_size=1000)
