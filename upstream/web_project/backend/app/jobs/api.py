import uuid
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,Field,ConfigDict
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from app.api.deps import get_db
from app.core.auth import get_current_admin_user
from app.models import Movie
from .models import Job
router=APIRouter(prefix='/api/admin/jobs',tags=['background-jobs'])
class CreateJob(BaseModel):
    model_config=ConfigDict(extra='forbid')
    request_id:uuid.UUID
    movie_ids:list[int]=Field(min_length=1,max_length=100)
def serialize(j):
    return dict(id=str(j.id),state=j.state,attempts=j.attempts,movie_ids=j.payload['movie_ids'],result=j.result,error_class=j.error_class,created_at=j.created_at.isoformat(),updated_at=j.updated_at.isoformat())
@router.post('',status_code=202)
def create(body:CreateJob,user=Depends(get_current_admin_user),db=Depends(get_db)):
    payload={'movie_ids':sorted(set(body.movie_ids))}
    found=set(db.scalars(select(Movie.movie_id).where(Movie.movie_id.in_(payload['movie_ids']))))
    if found!=set(payload['movie_ids']):raise HTTPException(422,'部分电影不存在')
    stmt=insert(Job).values(id=uuid.uuid4(),owner_id=user.user_id,request_key=body.request_id,payload=payload,state='queued',attempts=0).on_conflict_do_nothing(index_elements=['owner_id','request_key'])
    db.execute(stmt)
    job=db.scalar(select(Job).where(Job.owner_id==user.user_id,Job.request_key==body.request_id))
    if job.payload!=payload:db.rollback();raise HTTPException(409,'请求ID已用于其他任务')
    result=serialize(job);db.commit();return result
@router.get('')
def listing(page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),user=Depends(get_current_admin_user),db=Depends(get_db)):
    rows=db.scalars(select(Job).where(Job.owner_id==user.user_id).order_by(Job.created_at.desc(),Job.id).offset((page-1)*page_size).limit(page_size)).all()
    return {'items':[serialize(j) for j in rows],'page':page,'page_size':page_size}
@router.get('/{job_id}')
def detail(job_id:uuid.UUID,user=Depends(get_current_admin_user),db=Depends(get_db)):
    job=db.scalar(select(Job).where(Job.id==job_id,Job.owner_id==user.user_id))
    if job is None:raise HTTPException(404,'任务不存在')
    return serialize(job)

class DescriptionChange(BaseModel):
    model_config=ConfigDict(extra='forbid')
    description:str=Field(max_length=12000)
@router.patch('/movies/{movie_id}/description')
def metadata(movie_id:int,body:DescriptionChange,user=Depends(get_current_admin_user),db=Depends(get_db)):
    from app.behavior.catalogue import change_description
    try:result=change_description(db,movie_id,body.description);db.commit();return result
    except Exception:db.rollback();raise
