"""Pinned small official references; never load the latest-small interactions."""
import csv,gzip,hashlib,io,json,re,unicodedata,urllib.request,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
REFS=[('ml-1m-reference.zip','https://files.grouplens.org/datasets/movielens/ml-1m.zip','a6898adb50b9ca05aa231689da44c217cb524e7ebd39d264c56e2832f2c54e20'),('ml-latest-small-links-reference.zip','https://files.grouplens.org/datasets/movielens/ml-latest-small.zip','696d65a3dfceac7c45750ad32df2c259311949efec81f0f144fdfb91ebc9e436')]
def prepare_refs():
 (ROOT/'data').mkdir(exist_ok=True)
 for filename,url,sha in REFS:
  dest=ROOT/'data'/filename
  if dest.exists():
   if hashlib.sha256(dest.read_bytes()).hexdigest()!=sha:raise RuntimeError('existing_reference_hash_mismatch:'+filename)
   print('Reused verified reference:',filename);continue
  with urllib.request.urlopen(url,timeout=30) as response:data=response.read(15*1024*1024+1)
  if hashlib.sha256(data).hexdigest()!=sha:raise RuntimeError('reference_changed_do_not_substitute:'+filename)
  with dest.open('xb') as f:f.write(data)
  print('Saved verified reference:',filename)
def audit():
 filename,url,sha=REFS[1];src=ROOT/'data'/filename
 if hashlib.sha256(src.read_bytes()).hexdigest()!=sha:raise RuntimeError('reference_hash_mismatch')
 with zipfile.ZipFile(src) as z:
  # Only these two metadata members may be opened. No ratings/tags member access.
  titles={int(x['movieId']):x['title'] for x in csv.DictReader(io.StringIO(z.read('ml-latest-small/movies.csv').decode('utf-8-sig')))}
  links={int(x['movieId']):'tt'+x['imdbId'].zfill(7) for x in csv.DictReader(io.StringIO(z.read('ml-latest-small/links.csv').decode('utf-8-sig'))) if x['imdbId']}
 movies=json.loads(gzip.decompress((ROOT/'data/catalog.safe.json.gz').read_bytes()))['movies']
 def norm(s):return re.sub(r'\s+',' ',unicodedata.normalize('NFKC',s)).strip().casefold()
 verified=[];unresolved=[]
 for m in movies:
  mid=int(m['movie_id']);title=m['title'];old=m.get('imdb_id')
  if mid in titles and norm(title)==norm(titles[mid]) and mid in links:
   verified.append({'movie_id':mid,'title':title,'imdb_id':links[mid],'previous_imdb_id':old,'changed':old!=links[mid],'verification':'same numeric ID AND exact normalized title including year in official reference'})
  else:unresolved.append({'movie_id':mid,'title':title,'reason':'missing reference ID/link or exact normalized title/year mismatch'})
 if len({v['imdb_id'] for v in verified})!=len(verified):raise RuntimeError('duplicate_verified_imdb_identity')
 report={'reference_url':url,'reference_sha256':sha,'use':'metadata identity only; reference interactions NOT read or used for training/evaluation','verified_count':len(verified),'changed_count':sum(v['changed'] for v in verified),'unresolved_count':len(unresolved),'verified':verified,'unresolved':unresolved}
 dest=ROOT/'reports/METADATA_OFFICIAL_LINKS.json'
 if dest.exists():
  prior=json.loads(dest.read_text(encoding='utf-8-sig'))
  expected={(int(v['movie_id']),v['imdb_id'],v['changed']) for v in prior['verified']}
  actual={(v['movie_id'],v['imdb_id'],v['changed']) for v in verified}
  if actual!=expected:raise RuntimeError('audit_differs_from_existing_manual_review')
  print('Existing metadata review exactly reproduced:',len(verified),report['changed_count'],len(unresolved));return
 dest.parent.mkdir(exist_ok=True);dest.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print('Metadata audit created:',len(verified),report['changed_count'],len(unresolved))
if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('action',choices=['references','audit']);a=p.parse_args()
 prepare_refs() if a.action=='references' else audit()
