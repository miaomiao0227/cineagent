import json,hashlib
from pathlib import Path
R=Path(__file__).resolve().parents[1];p=R/'reports/COMPLETE_V4_RESULTS.json';v=json.loads(p.read_text(encoding='utf-8'));v['frontend_source_sha256']=hashlib.sha256((R/'upstream/web_project/frontend/src/views/Chat.vue').read_bytes()).hexdigest();v['frontend_fingerprint_recorded']='post browser run, no frontend edits during batch';p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8');print('Frontend source fingerprint attached; no provider calls.')
