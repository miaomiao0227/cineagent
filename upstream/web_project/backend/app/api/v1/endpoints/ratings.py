"""Online ratings compatibility API; never writes frozen MovieLens training rows."""
import time
from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy.orm import Session
from app.api.deps import get_db
from app.core.auth import get_current_active_user
from app.schemas import RatingCreate
from app.behavior.models import Behavior
from app.behavior.service import update
router=APIRouter()
@router.post('/ratings',status_code=201,tags=['ratings'])
def rate(body:RatingCreate,user=Depends(get_current_active_user),db:Session=Depends(get_db)):
    try:
        r=update(db,user.user_id,body.movie_id,{'rating':body.rating});db.commit()
        return dict(user_id=user.user_id,movie_id=body.movie_id,rating=r['rating'],timestamp=int(time.time()))
    except Exception:db.rollback();raise
@router.get('/ratings/movie/{movie_id}',tags=['ratings'])
def read(movie_id:int,user=Depends(get_current_active_user),db:Session=Depends(get_db)):
    r=db.get(Behavior,(user.user_id,movie_id))
    return dict(rating=r.rating if r else None,has_rated=bool(r and r.rating is not None))
@router.delete('/ratings/movie/{movie_id}',tags=['ratings'])
def remove(movie_id:int,user=Depends(get_current_active_user),db:Session=Depends(get_db)):
    try:
        update(db,user.user_id,movie_id,{'rating':None});db.commit();return {'message':'评分已删除'}
    except Exception:db.rollback();raise
