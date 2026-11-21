"""Explicit local administrator provisioning; never prints credentials."""
import argparse,os
from sqlalchemy import select
from app.database import SessionLocal
from app.models import User
from app.core.security import get_password_hash
p=argparse.ArgumentParser();p.add_argument('--email',required=True);args=p.parse_args()
password=os.environ.get('DEMO_PASSWORD')
if not password or len(password)<12:raise RuntimeError('Configure a strong local DEMO_PASSWORD first')
with SessionLocal.begin() as db:
    user=db.scalar(select(User).where(User.email==args.email))
    if user is None:
        user=User(email=args.email,username=args.email,is_active=1,is_superuser=1,hashed_password=get_password_hash(password));db.add(user)
    elif not user.is_superuser:raise RuntimeError('Existing ordinary user retained; choose a separate administrator account')
print('Local administrator ready. Credentials remain in local configuration; not displayed.')
