from sqlalchemy import select,func
from sqlalchemy.dialects.postgresql import insert
from fastapi import HTTPException
from app.models import Movie
from .models import Behavior,BehaviorVersion

def serialize(row):
    return dict(movie_id=row.movie_id,favorite=row.favorite,seen=row.seen,rating=row.rating,updated_at=row.updated_at.isoformat())

def update(db,user_id,movie_id,changes):
    if not db.scalar(select(Movie.movie_id).where(Movie.movie_id==movie_id)):
        raise HTTPException(404,'电影不存在')
    # Serialize mutations for the same owner across workers, inside the DB transaction.
    db.execute(insert(BehaviorVersion).values(user_id=user_id,version=0).on_conflict_do_nothing())
    version=db.scalar(select(BehaviorVersion).where(BehaviorVersion.user_id==user_id).with_for_update())
    old=db.get(Behavior,(user_id,movie_id))
    if old and all(getattr(old,k)==v for k,v in changes.items()):
        result=serialize(old);result['behavior_version']=version.version;return result
    stmt=insert(Behavior).values(user_id=user_id,movie_id=movie_id,**changes)
    row=db.execute(stmt.on_conflict_do_update(index_elements=['user_id','movie_id'],set_={**changes,'updated_at':func.now()}).returning(Behavior),execution_options={'populate_existing':True}).scalar_one()
    version.version+=1
    db.flush()
    result=serialize(row);result['behavior_version']=version.version
    return result
