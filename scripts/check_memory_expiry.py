import uuid,json
from datetime import datetime,timedelta,timezone
from pathlib import Path
from app.database import SessionLocal
from app.cineagent.models import Preference
from app.cineagent.api import prefs
who='test:'+str(uuid.uuid4());now=datetime.now(timezone.utc)
with SessionLocal() as db:
 for name,status,expiry in [('active','active',now+timedelta(days=1)),('expired','active',now-timedelta(seconds=1)),('revoked','revoked',None)]:db.add(Preference(id=str(uuid.uuid4()),owner=who,key='exclude_genres',value=name,scope='long_term',source_turn=1,status=status,expires_at=expiry))
 db.flush();actual=prefs(db,who);result={'scope':'isolated transaction rolled back; no user memory changed','expired_ignored':all(p.value!='expired' for p in actual),'revoked_ignored':all(p.value!='revoked' for p in actual),'active_loaded':len(actual)==1 and actual[0].value=='active'};db.rollback()
Path('/trial-ledger/MEMORY_EXPIRY_CHECK.json').write_text(json.dumps(result,indent=2));print(json.dumps(result));assert result['expired_ignored'] and result['revoked_ignored'] and result['active_loaded']
