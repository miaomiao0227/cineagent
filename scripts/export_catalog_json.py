"""Approved isolated pickle -> inert gzip JSON, no credentials/network."""
import sys,json,gzip,pickle,pandas as pd
from pathlib import Path
raw=Path('/data')
meta=pickle.load((raw/'movie_metadata.pkl').open('rb'))
payload={'movies':json.loads(pd.read_pickle(raw/'movies.pkl').to_json(orient='records')),'metadata':{k:json.loads(v.to_json(orient='records')) for k,v in meta.items()}}
sys.stdout.buffer.write(gzip.compress(json.dumps(payload,ensure_ascii=False,allow_nan=False).encode('utf-8')))
