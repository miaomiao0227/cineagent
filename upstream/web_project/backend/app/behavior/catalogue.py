import json
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from app.models import Movie
from app.schemas import MovieDetail
from .models import MovieVersion
from .recommendations import cache
import redis

def detail(db,movie_id,client=None):
    client=cache if client is None else client
    version=db.scalar(select(MovieVersion.version).where(MovieVersion.movie_id==movie_id)) or 0
    key=f'ca:movie:v1:{movie_id}:{version}'
    try:
        raw=client.get(key)
        if raw:
            value=json.loads(raw)
            if value.get('not_found'):raise HTTPException(404,'电影不存在')
            return MovieDetail.model_validate(value)
    except (redis.RedisError,ValueError,TypeError):pass
    movie=db.get(Movie,movie_id)
    if movie is None:
        try:client.setex(key,15,json.dumps({'not_found':True}))
        except redis.RedisError:pass
        raise HTTPException(404,'电影不存在')
    data={k:getattr(movie,k) for k in MovieDetail.model_fields if hasattr(movie,k)}
    data['genres']=movie.genres or []
    value=MovieDetail.model_validate(data)
    try:client.setex(key,300,value.model_dump_json())
    except redis.RedisError:pass
    return value

def change_description(db,movie_id,description):
    movie=db.scalar(select(Movie).where(Movie.movie_id==movie_id).with_for_update())
    if movie is None:raise HTTPException(404,'电影不存在')
    db.execute(insert(MovieVersion).values(movie_id=movie_id,version=0).on_conflict_do_nothing())
    version=db.scalar(select(MovieVersion).where(MovieVersion.movie_id==movie_id).with_for_update())
    if movie.description!=description:movie.description=description;version.version+=1
    db.flush()
    return {'movie_id':movie_id,'version':version.version}
