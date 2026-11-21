"""Adopt additive online tables; do not alter original recommendation tables."""
from alembic import op
from app.behavior.models import Behavior,BehaviorVersion,MovieVersion
from app.jobs.models import Job
revision='0001_online_backend'
down_revision=None
branch_labels=None
depends_on=None
def upgrade():
    for table in [BehaviorVersion.__table__,Behavior.__table__,MovieVersion.__table__,Job.__table__]:table.create(op.get_bind(),checkfirst=True)
def downgrade():
    raise RuntimeError('Destructive downgrade intentionally requires an explicit data preservation plan')
