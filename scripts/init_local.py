"""Generate independent local secrets only when absent; never print values."""
from pathlib import Path
import secrets
root=Path(__file__).resolve().parents[1]
for folder in ['configs/local-secrets','data','artifacts/rec_v1','reports','eval']:(root/folder).mkdir(parents=True,exist_ok=True)
p=root/'configs/.env'
if p.exists():print('Existing local configuration preserved.')
else:
 p.write_text('\n'.join(k+'='+secrets.token_hex(24) for k in ['POSTGRES_PASSWORD','SECRET_KEY','DEMO_PASSWORD'])+'\n',encoding='utf-8');print('Local credentials generated; values not displayed.')
