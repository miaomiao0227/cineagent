"""Run in isolated container only after archive CRC and SHA256 recording."""
from pathlib import Path
import pandas as pd, pickle, json, sys, zipfile, numpy as np
raw=Path("/data")
report={"source":"upstream prepared MovieLens/IMDb bundle","metadata_license":"unverified","datasets":{},"checks":{}}
frames={}
for name in ["movies","users","ratings"]:
    df=pd.read_pickle(raw/(name+".pkl"))
    if not isinstance(df,pd.DataFrame):raise TypeError(name+" must be DataFrame")
    frames[name]=df
    report["datasets"][name]={"rows":len(df),"columns":list(df.columns),"dtypes":{k:str(v) for k,v in df.dtypes.items()},"missing":{k:int(v) for k,v in df.isna().sum().items()}}
movies,users,ratings=(frames[k] for k in ["movies","users","ratings"])
for df,cols in [(movies,["movie_id"]),(users,["user_id"]),(ratings,["user_id","movie_id","rating","timestamp"])]:
    if any(c not in df for c in cols):raise ValueError("Missing required columns: "+str(cols))
c=report["checks"]
c["duplicate_movie_ids"]=int(movies.movie_id.duplicated().sum())
c["duplicate_user_ids"]=int(users.user_id.duplicated().sum())
c["ratings_unknown_movie"]=int((~ratings.movie_id.isin(movies.movie_id)).sum())
c["ratings_unknown_user"]=int((~ratings.user_id.isin(users.user_id)).sum())
c["ratings_missing_required"]=int(ratings[["user_id","movie_id","rating","timestamp"]].isna().any(axis=1).sum())
c["rating_range"]=[float(ratings.rating.min()),float(ratings.rating.max())]
c["timestamp_range"]=[int(pd.to_numeric(ratings.timestamp,errors="raise").min()),int(pd.to_numeric(ratings.timestamp,errors="raise").max())]
c["duplicate_user_movie_pairs"]=int(ratings.duplicated(["user_id","movie_id"]).sum())
with (raw/"movie_metadata.pkl").open("rb") as f:metadata=pickle.load(f)
report["metadata"]={str(k):{"type":type(v).__name__,"rows":len(v) if hasattr(v,"__len__") else None,"columns":list(v.columns) if isinstance(v,pd.DataFrame) else None} for k,v in metadata.items()}
images=[p for p in (raw/"image").rglob("*") if p.is_file()]
report["images"]={"files":len(images),"suffix_counts":{s:sum(p.suffix.lower()==s for p in images) for s in sorted({p.suffix.lower() for p in images})},"id_mapping_verified":False,"decoding_verified":False}
if Path("/reference.zip").exists():
    with zipfile.ZipFile("/reference.zip") as z:
        with z.open("ml-1m/ratings.dat") as f:
            ref=pd.read_csv(f,sep=":",header=None,usecols=[0,2,4,6],names=["user_id","movie_id","rating","timestamp"],dtype="int64")
    current=ratings[["user_id","movie_id","rating","timestamp"]].apply(pd.to_numeric,errors="raise")
    a=current.sort_values(["user_id","movie_id"]).reset_index(drop=True)
    b=ref.sort_values(["user_id","movie_id"]).reset_index(drop=True)
    c["official_row_count_match"]=len(a)==len(b)
    c["official_keys_match"]=bool(np.array_equal(a[["user_id","movie_id"]].values,b[["user_id","movie_id"]].values))
    c["official_timestamps_match"]=bool(np.array_equal(a.timestamp.values,b.timestamp.values))
    c["upstream_rating_exactly_twice_official"]=bool(np.array_equal(a.rating.values,2*b.rating.values))
    c["official_rating_range"]=[int(b.rating.min()),int(b.rating.max())]
    c["timestamp_is_string"]=ratings.timestamp.dtype==object
report["validation_ok"]=all(c[k]==0 for k in ["duplicate_movie_ids","duplicate_user_ids","ratings_unknown_movie","ratings_unknown_user","ratings_missing_required"])
if "--stdout" in sys.argv:
    print(json.dumps(report,ensure_ascii=False))
else:
    Path("/artifacts/data_inspection.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps({"counts":{k:v["rows"] for k,v in report["datasets"].items()},"checks":c,"images":report["images"],"validation_ok":report["validation_ok"]},ensure_ascii=False))
raise SystemExit(0 if report["validation_ok"] else 1)
