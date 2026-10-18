from datetime import datetime,timezone
from sqlalchemy import Column,String,Integer,DateTime,Text,UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from app.database import Base
now=lambda:datetime.now(timezone.utc)
class Conversation(Base):
    __tablename__='ca_conversations'
    id=Column(String(36),primary_key=True);owner=Column(String(100),index=True,nullable=False);state=Column(JSONB,default=dict,nullable=False);created_at=Column(DateTime(timezone=True),default=now)
class Turn(Base):
    __tablename__='ca_turns'
    id=Column(String(36),primary_key=True);conversation_id=Column(String(36),index=True,nullable=False);owner=Column(String(100),index=True,nullable=False);number=Column(Integer,nullable=False);text=Column(Text,nullable=False);created_at=Column(DateTime(timezone=True),default=now)
    __table_args__=(UniqueConstraint('conversation_id','number'),)
class Preference(Base):
    __tablename__='ca_preferences'
    id=Column(String(36),primary_key=True);owner=Column(String(100),index=True,nullable=False);key=Column(String(40),nullable=False);value=Column(JSONB,nullable=False);source_conversation=Column(String(36));source_turn=Column(Integer);scope=Column(String(30),default='long_term');created_at=Column(DateTime(timezone=True),default=now);expires_at=Column(DateTime(timezone=True),nullable=True);status=Column(String(20),default='active')
class PreferenceAudit(Base):
    __tablename__='ca_preference_audit'
    id=Column(String(36),primary_key=True);owner=Column(String(100),index=True,nullable=False);preference_id=Column(String(36));action=Column(String(30));request_id=Column(String(36));created_at=Column(DateTime(timezone=True),default=now)
class Feedback(Base):
    __tablename__='ca_feedback'
    id=Column(String(36),primary_key=True);owner=Column(String(100),index=True,nullable=False);request_id=Column(String(36),nullable=False);movie_id=Column(Integer,nullable=False);kind=Column(String(20),nullable=False);source_conversation=Column(String(36));source_turn=Column(Integer);created_at=Column(DateTime(timezone=True),default=now)
    __table_args__=(UniqueConstraint('owner','request_id','movie_id','kind'),)
class RequestRecord(Base):
    __tablename__='ca_requests'
    id=Column(String(36),primary_key=True);owner=Column(String(100),index=True,nullable=False);request_id=Column(String(36),nullable=False);body_sha256=Column(String(64),nullable=False);response=Column(JSONB,nullable=False);created_at=Column(DateTime(timezone=True),default=now)
    __table_args__=(UniqueConstraint('owner','request_id'),)
