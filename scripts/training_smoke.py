"""Legacy upstream execution smoke, NOT rec-v1 evaluation; no deployment."""
import os, json, time, random, traceback
from pathlib import Path
import numpy as np,pandas as pd,tensorflow as tf
SEED=20261018
random.seed(SEED);np.random.seed(SEED);tf.random.set_seed(SEED)
start=time.perf_counter();report={"kind":"execution_smoke_not_formal_evaluation","seed":SEED,"results":[]}
from offline.feature import preprocess_retrieval as pr, preprocess_ranking as pk
from offline.training import train_retrieval as tr, train_ranking as tk
from offline.config import config
m=pd.read_pickle("/data/movies.pkl");u=pd.read_pickle("/data/users.pkl");a=pd.read_pickle("/data/ratings.pkl")
a["timestamp"]=pd.to_numeric(a.timestamp,errors="raise");a["rating"]=a.rating/2
chosen=sorted(u.user_id.tolist(),key=int)[:32]
a=a[a.user_id.isin(chosen)].sort_values(["timestamp","user_id","movie_id"],kind="stable").groupby("user_id",sort=False).head(50).copy()
u=u[u.user_id.isin(chosen)].copy()
m["startYear"]=m.startYear.fillna("unknown").astype(str)
report["input"]={"users":len(u),"interactions":len(a),"movies":len(m),"timestamp_min":int(a.timestamp.min()),"timestamp_max":int(a.timestamp.max()),"rating_scale":"1-5 normalized; upstream legacy labels retained only for smoke"}
pr.load_raw_data=lambda:(m.copy(deep=True),a.copy(deep=True),u.copy(deep=True))
pk.load_raw_data=pr.load_raw_data
config.EPOCHS=1;config.BATCH_SIZE=64
captured={}
for module,name in [(tr,"retrieval"),(tk,"ranking")]:
    original=module.train_model
    def wrapped(training_config,feature_columns,processed_data,original=original,name=name):
        training_config=dict(training_config);training_config["epochs"]=1;training_config["verbose"]=0
        models=original(training_config,feature_columns,processed_data)
        losses=models[0].history.history.get("loss",[])
        assert losses and np.isfinite(losses).all(),"nonfinite training loss"
        captured[name]=(models,processed_data)
        report["results"].append({"check":name+"_one_epoch_fit","ok":True,"epochs":len(losses),"train_rows":len(processed_data["train"]["features"]["user_id"]),"test_rows":len(processed_data["test"]["features"]["user_id"])})
        return models
    module.train_model=wrapped
    module.evaluate_model=lambda *args,**kwargs:{}
    module.build_metrics_table=lambda *args,**kwargs:"Formal evaluation disabled for execution smoke"
try:
    pr.run_retrieval_preprocessing();pk.run_ranking_preprocessing()
    tr.run_retrieval_training();tk.run_ranking_training()
    for name,(models,data) in captured.items():
        model=models[1] if name=="retrieval" else models[0]
        batch={k:np.asarray(v)[:8] for k,v in data["test"]["features"].items() if k in model.input_names}
        before=model(batch,training=False).numpy();assert np.isfinite(before).all()
        folder=config.SAVED_MODELS_DIR/("user_model" if name=="retrieval" else "ranking_model")
        loaded=tf.keras.models.load_model(str(folder),compile=False)
        after=loaded(batch,training=False).numpy();np.testing.assert_allclose(before,after,rtol=1e-5,atol=1e-6)
        report["results"].append({"check":name+"_saved_reload_predictions","ok":True,"shape":list(after.shape)})
    ids=np.load(config.MOVIE_IDS_PATH,allow_pickle=False);emb=np.load(config.ITEM_EMB_PATH,allow_pickle=False)
    assert len(ids)==len(emb) and len(set(ids.tolist()))==len(ids) and np.isfinite(emb).all()
    report["results"].append({"check":"item_vectors_and_ids","ok":True,"items":len(ids),"embedding_shape":list(emb.shape)})
    report["ok"]=True
except Exception as error:
    report["ok"]=False;report["error_type"]=type(error).__name__;report["error"]=str(error);report["traceback"]=traceback.format_exc();raise
finally:
    report["seconds"]=round(time.perf_counter()-start,3)
    Path("/out/TRAINING_SMOKE.json").write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False),flush=True)
