"""Export non-secret local catalogue attributes for a bounded tool smoke test."""
import json
from pathlib import Path
from app.database import SessionLocal
from app.models import Movie
with SessionLocal() as db:
    rows=db.query(Movie.movie_id,Movie.title,Movie.genres,Movie.runtime_minutes).order_by(Movie.movie_id).all()
out=[{'movie_id':r.movie_id,'title':r.title,'genres':r.genres or [],'runtime_minutes':r.runtime_minutes} for r in rows]
p=Path('/artifacts/content_v1/local_catalogue.json');p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(out,ensure_ascii=False),encoding='utf-8')
print(json.dumps({'catalogue_rows':len(out),'runtime_present':sum(x['runtime_minutes'] is not None for x in out)}))
