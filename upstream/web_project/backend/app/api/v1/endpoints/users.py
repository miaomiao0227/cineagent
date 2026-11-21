"""Signed-in profile based on isolated online interactions."""
from collections import Counter
from fastapi import APIRouter,Depends
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from app.api.deps import get_db
from app.core.auth import get_current_active_user
from app.models import Movie
from app.behavior.models import Behavior,BehaviorVersion
from app.schemas import UserProfile,UserUpdate,RecentRating
router=APIRouter()
def profile(db,user):
    rows=db.execute(select(Behavior,Movie).join(Movie,Behavior.movie_id==Movie.movie_id).where(Behavior.user_id==user.user_id,Behavior.rating.is_not(None)).order_by(Behavior.updated_at.desc(),Behavior.movie_id.desc()).limit(100)).all()
    result=UserProfile.model_validate(user)
    result.recent_ratings=[RecentRating(movie_id=r.movie_id,title=m.title,genres=m.genres or [],rating=r.rating,timestamp=int(r.updated_at.timestamp())) for r,m in rows[:10]]
    genres=Counter(g for r,m in rows if r.rating>=8 for g in (m.genres or []));result.frequent_genres=[g for g,n in genres.most_common(5)]
    return result
@router.get('/users/me',response_model=UserProfile,tags=['users'])
def get_current_user_profile(user=Depends(get_current_active_user),db=Depends(get_db)):return profile(db,user)
@router.put('/users/me',response_model=UserProfile,tags=['users'])
def update_user_profile(body:UserUpdate,user=Depends(get_current_active_user),db=Depends(get_db)):
    try:
        db.execute(insert(BehaviorVersion).values(user_id=user.user_id,version=0).on_conflict_do_nothing())
        version=db.scalar(select(BehaviorVersion).where(BehaviorVersion.user_id==user.user_id).with_for_update())
        changes=body.model_dump(exclude_unset=True)
        if 'preferred_genres' in changes and changes['preferred_genres'] is None:changes['preferred_genres']=[]
        if any(getattr(user,k)!=v for k,v in changes.items()):
            for k,v in changes.items():setattr(user,k,v)
            version.version+=1
        db.commit();return profile(db,user)
    except Exception:db.rollback();raise
