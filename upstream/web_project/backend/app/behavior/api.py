from fastapi import APIRouter,Depends,Query,HTTPException
from pydantic import BaseModel,Field,ConfigDict
from sqlalchemy import select,func
from app.api.deps import get_db
from app.core.auth import get_current_active_user
from .models import Behavior
from .service import update,serialize
router=APIRouter(prefix='/api/me',tags=['user-behaviors'])
class Change(BaseModel):
    model_config=ConfigDict(extra='forbid')
    favorite:bool|None=None
    seen:bool|None=None
    rating:int|None=Field(default=None,ge=1,le=10)
@router.put('/movies/{movie_id}/behavior')
def mutate(movie_id:int,body:Change,user=Depends(get_current_active_user),db=Depends(get_db)):
    changes=body.model_dump(exclude_unset=True)
    if not changes or any(changes.get(k) is None for k in ('favorite','seen') if k in changes):raise HTTPException(422,'请提供有效的行为字段')
    try:
        result=update(db,user.user_id,movie_id,changes)
        db.commit()
        return result
    except Exception:
        db.rollback();raise
@router.get('/behaviors')
def listing(page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),kind:str=Query('all',pattern='^(all|favorite|seen|rated)$'),user=Depends(get_current_active_user),db=Depends(get_db)):
    filters=[Behavior.user_id==user.user_id]
    if kind=='favorite':filters.append(Behavior.favorite.is_(True))
    if kind=='seen':filters.append(Behavior.seen.is_(True))
    if kind=='rated':filters.append(Behavior.rating.is_not(None))
    from app.models import Movie
    rows=db.execute(select(Behavior,Movie.title).join(Movie,Movie.movie_id==Behavior.movie_id).where(*filters).order_by(Behavior.updated_at.desc(),Behavior.movie_id.desc()).offset((page-1)*page_size).limit(page_size)).all()
    total=db.scalar(select(func.count()).select_from(Behavior).where(*filters))
    return dict(items=[{**serialize(r),"title":title} for r,title in rows],total=total,page=page,page_size=page_size)

@router.get('/movies/{movie_id}/behavior')
def detail(movie_id:int,user=Depends(get_current_active_user),db=Depends(get_db)):
    from app.models import Movie
    if db.get(Movie,movie_id) is None:raise HTTPException(404,'电影不存在')
    row=db.get(Behavior,(user.user_id,movie_id))
    return serialize(row) if row else dict(movie_id=movie_id,favorite=False,seen=False,rating=None,updated_at=None)

@router.get('/recommendations')
def personal_recommendations(limit:int=Query(6,ge=1,le=20),q:str=Query('',max_length=200),user=Depends(get_current_active_user),db=Depends(get_db)):
    from .recommendations import recommendations
    return recommendations(db,user.user_id,limit,q)
