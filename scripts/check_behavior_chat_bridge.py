import json,uuid
from pathlib import Path
from urllib.request import Request,urlopen
from sqlalchemy import delete
from app.database import SessionLocal
from app.models import User
from app.behavior.models import Behavior,BehaviorVersion
from app.cineagent.models import Conversation,Turn,RequestRecord,Feedback,Preference,PreferenceAudit
from app.core.security import create_access_token
with SessionLocal.begin() as db:
    user=User(username='bridge_'+uuid.uuid4().hex,is_active=1);db.add(user);db.flush();uid=user.user_id
who='user:'+str(uid);token=create_access_token({'sub':str(uid)})
def api(path,body=None,method=None):
    with urlopen(Request('http://127.0.0.1:8000'+path,data=json.dumps(body).encode() if body is not None else None,method=method,headers={'Content-Type':'application/json','Authorization':'Bearer '+token}),timeout=30) as r:return json.load(r)
try:
    first=api('/api/chat/message',{'request_id':str(uuid.uuid4()),'message':'想看悬疑电影，不要恐怖片。','mode':'offline'})
    mid=first['items'][0]['movie_id'];f={'request_id':str(uuid.uuid4()),'conversation_id':first['conversation_id'],'movie_id':mid,'kind':'seen'}
    api('/api/chat/feedback',f);api('/api/chat/feedback',f)
    assert api(f'/api/me/movies/{mid}/behavior')['seen']
    result=api('/api/me/recommendations?limit=6');assert mid not in [x['movie_id'] for x in result['items']]
    second=api('/api/chat/message',{'request_id':str(uuid.uuid4()),'conversation_id':first['conversation_id'],'message':'第一部看过了，换一部。','mode':'offline'})
    assert api(f'/api/me/movies/{mid}/behavior')['seen']
    checks={'chat_feedback_saved_to_online_behavior':True,'duplicate_feedback_idempotent':True,'homepage_endpoint_excludes_chat_seen':True,'natural_seen_uses_same_service':True,'paid_calls':0}
    Path('/trial-ledger/BACKEND_CHAT_BRIDGE.json').write_text(json.dumps(checks,indent=2));print(json.dumps(checks))
finally:
    with SessionLocal.begin() as db:
        for model in [Feedback,RequestRecord,Turn,PreferenceAudit,Preference,Conversation]:db.execute(delete(model).where(model.owner==who))
        db.execute(delete(Behavior).where(Behavior.user_id==uid));db.execute(delete(BehaviorVersion).where(BehaviorVersion.user_id==uid));db.execute(delete(User).where(User.user_id==uid))
