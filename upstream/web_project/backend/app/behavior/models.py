from sqlalchemy import Column,Integer,Boolean,DateTime,ForeignKey,CheckConstraint,Index,func
from app.database import Base
class Behavior(Base):
    __tablename__='online_behaviors'
    user_id=Column(Integer,ForeignKey('users.user_id'),primary_key=True)
    movie_id=Column(Integer,ForeignKey('movies.movie_id'),primary_key=True)
    favorite=Column(Boolean,nullable=False,server_default='false')
    seen=Column(Boolean,nullable=False,server_default='false')
    rating=Column(Integer,nullable=True)
    updated_at=Column(DateTime(timezone=True),nullable=False,server_default=func.now())
    __table_args__=(CheckConstraint('rating IS NULL OR rating BETWEEN 1 AND 10',name='ck_online_rating'),Index('ix_online_user_updated','user_id','updated_at','movie_id'))
class BehaviorVersion(Base):
    __tablename__='online_behavior_versions'
    user_id=Column(Integer,ForeignKey('users.user_id'),primary_key=True)
    version=Column(Integer,nullable=False,server_default='0')

class MovieVersion(Base):
    __tablename__='movie_cache_versions'
    movie_id=Column(Integer,ForeignKey('movies.movie_id'),primary_key=True)
    version=Column(Integer,nullable=False,server_default='0')
