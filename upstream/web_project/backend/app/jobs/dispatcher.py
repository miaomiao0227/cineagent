"""DB outbox publisher: retries publishing and recovers expired execution leases."""
import time,logging
from datetime import timedelta
from sqlalchemy import select,or_,and_
from app.database import SessionLocal
from .models import Job
from .tasks import celery_app,now
from app.config import settings
logging.basicConfig(level=logging.INFO)
def tick():
    with SessionLocal.begin() as db:
        jobs=db.scalars(select(Job).where(or_(and_(Job.state.in_(['queued','dispatched']),Job.next_run<=now()),and_(Job.state=='running',Job.lease_until<=now()))).order_by(Job.next_run).with_for_update(skip_locked=True).limit(10)).all()
        for j in jobs:
            if j.attempts>=3:j.state='failed';j.error_class='AttemptLimit';continue
            celery_app.send_task('cineagent.refresh_index',args=[str(j.id)],task_id=str(j.id),queue=settings.job_queue,retry=False)
            j.state='dispatched';j.next_run=now()+timedelta(seconds=30);j.updated_at=now()
if __name__=='__main__':
    while True:
        try:tick()
        except Exception as e:logging.warning('job_dispatch_failed:%s',type(e).__name__)
        time.sleep(2)
