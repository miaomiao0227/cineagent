"""Add only new online business tables; never alter MovieLens ratings."""
from app.database import engine,Base
from app.models import User,Movie
from app.behavior.models import Behavior,BehaviorVersion
Base.metadata.create_all(engine,tables=[Behavior.__table__,BehaviorVersion.__table__])
print('online behavior tables ready')
