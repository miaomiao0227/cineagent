import uuid
from sqlalchemy import Column,String,Integer,DateTime,ForeignKey,UniqueConstraint,func
from sqlalchemy.dialects.postgresql import UUID,JSONB
from app.database import Base
class Job(Base):
    __tablename__='background_jobs'
    id=Column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    owner_id=Column(Integer,ForeignKey('users.user_id'),nullable=False)
    request_key=Column(UUID(as_uuid=True),nullable=False)
    payload=Column(JSONB,nullable=False)
    state=Column(String(20),nullable=False,default='queued',index=True)
    attempts=Column(Integer,nullable=False,default=0)
    claim=Column(String(36))
    next_run=Column(DateTime(timezone=True),nullable=False,server_default=func.now(),index=True)
    lease_until=Column(DateTime(timezone=True))
    created_at=Column(DateTime(timezone=True),nullable=False,server_default=func.now())
    updated_at=Column(DateTime(timezone=True),nullable=False,server_default=func.now())
    result=Column(JSONB)
    error_class=Column(String(100))
    __table_args__=(UniqueConstraint('owner_id','request_key',name='uq_job_owner_request'),)
