"""HTTP acceptance; credentials stay local and are never written to report."""
from pathlib import Path
import urllib.request,json,time,collections,zipfile
r=Path(__file__).resolve().parents[1];base='http://127.0.0.1:13000';results=[]
def request(path,body=None,token=None,binary=False):
    headers={}
    if token:headers['Authorization']='Bearer '+token
    data=None
    if body is not None:data=json.dumps(body).encode();headers['Content-Type']='application/json'
    start=time.perf_counter()
    with urllib.request.urlopen(urllib.request.Request(base+path,data=data,headers=headers),timeout=60) as response:
        raw=response.read();out=raw if binary else json.loads(raw);results.append({'path':path,'status':response.status,'seconds':round(time.perf_counter()-start,3),'bytes':len(raw)})
    return out
try:
    h=request('/health');assert h['status']=='healthy'
    movies=request('/api/movies?limit=10');assert movies['total']==3883 and len(movies['items'])>0
    popular=request('/api/movies/popular?limit=10');assert popular
    detail=request('/api/movies/1');assert detail['movie_id']==1
    crew=request('/api/movies/1/crew');cast=request('/api/movies/1/cast')
    assert crew.get('directors'), 'Verified Toy Story director missing'
    assert cast.get('cast'), 'Verified Toy Story cast missing'
    search=request('/api/search/movies?q=Toy%20Story&limit=10');assert any(x['movie_id']==1 for x in search)
    image=request('/api/posters/1.png',binary=True);assert image[:8]==b'\x89PNG\r\n\x1a\n'
    local={line.split('=',1)[0]:line.split('=',1)[1] for line in (r/'configs/.env').read_text().splitlines() if '=' in line}
    auth=request('/api/auth/login',{'email':'demo@cineagent.local','password':local['DEMO_PASSWORD']});token=auth['access_token']
    me=request('/api/users/me',token=token);assert me['user_id']==635
    recommendation=request('/api/recommendations/recommend?top_k=20',{'user_id':635},token=token);assert recommendation['ranking_strategy']=='deepfm' and len(recommendation['items'])==20
    ids=[x['movie_id'] for x in recommendation['items']];assert len(set(ids))==20
    with zipfile.ZipFile(r/'data/ml-1m-reference.zip') as z:
        seen=set();catalogue=set()
        for line in z.read('ml-1m/movies.dat').decode('latin-1').splitlines():catalogue.add(int(line.split('::')[0]))
        for line in z.read('ml-1m/ratings.dat').splitlines():
            u,m,_,t=map(int,line.split(b'::'))
            if u==635 and t<975768738:seen.add(m)
    assert not set(ids)&seen and set(ids)<=catalogue
    for item in recommendation['items'][:3]:assert request(item['poster_url'],binary=True)[:8]==b'\x89PNG\r\n\x1a\n'
    cold=request('/api/recommendations/recommend?top_k=10',{'preferred_genres':['Sci-Fi']});assert cold['items']
    mh=request('/api/recommendations/health');assert mh['ranking']['ready'] and mh['recall']['strategies']==4
    report={'ok':True,'checks':results,'recommendation':{'user_id':635,'ids':ids,'ranking_strategy':recommendation['ranking_strategy'],'recall_count':recommendation['recall_count'],'recall_types':dict(collections.Counter(x['recall_type'] for x in recommendation['items'])),'all_ids_exist':True,'seen_intersection':0},'cold_start':{'items':len(cold['items']),'ranking_strategy':cold['ranking_strategy']},'model_health':mh,'credentials_recorded':False,'note':'Functional acceptance only; timings are individual requests, not load-test P50/P95. No feedback writes.'}
except Exception as e:
    report={'ok':False,'checks':results,'error_type':type(e).__name__,'error':str(e)}
(r/'reports/ONLINE_HTTP_ACCEPTANCE.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False));raise SystemExit(0 if report['ok'] else 1)
