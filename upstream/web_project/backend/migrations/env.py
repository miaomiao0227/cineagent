from alembic import context
from app.database import engine,Base
from app import models
from app.behavior.models import Behavior,BehaviorVersion
from app.jobs.models import Job
if context.is_offline_mode():raise RuntimeError('Use online migrations with explicit DB target')
with engine.connect() as connection:
    context.configure(connection=connection,target_metadata=Base.metadata)
    with context.begin_transaction():context.run_migrations()
