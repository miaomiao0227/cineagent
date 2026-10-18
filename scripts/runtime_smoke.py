import importlib, json, sys, traceback, time
from pathlib import Path
results=[]
for name in ["tensorflow", "tf_keras", "numpy", "pandas", "scipy", "gensim", "funrec", "offline.pipeline", "online.pipeline", "app.main"]:
    start=time.perf_counter()
    try:
        m=importlib.import_module(name)
        results.append({"module":name,"ok":True,"version":getattr(m,"__version__",None),"seconds":round(time.perf_counter()-start,3)})
    except Exception as e:
        results.append({"module":name,"ok":False,"error_type":type(e).__name__,"error":str(e),"traceback":traceback.format_exc()})
try:
    import tensorflow as tf
    actual=tf.linalg.matmul(tf.constant([[1.,2.]]),tf.constant([[3.],[4.]])).numpy().tolist()
    assert actual==[[11.]]
    results.append({"check":"tensorflow_cpu_matmul","ok":True,"result":actual})
except Exception as e:
    results.append({"check":"tensorflow_cpu_matmul","ok":False,"error":str(e)})
try:
    from app.core.security import get_password_hash, verify_password
    hashed=get_password_hash("runtime-smoke-placeholder")
    assert verify_password("runtime-smoke-placeholder",hashed)
    assert not verify_password("wrong-placeholder",hashed)
    results.append({"check":"password_hash_roundtrip","ok":True})
except Exception as e:
    results.append({"check":"password_hash_roundtrip","ok":False,"error":str(e)})
try:
    import tf_keras, numpy as np, tempfile, shutil
    folder=tempfile.mkdtemp(prefix="smoke-model-",dir="/artifacts")
    try:
        model=tf_keras.Sequential([tf_keras.layers.Input(shape=(2,)),tf_keras.layers.Dense(1)])
        x=np.array([[1.,2.]],dtype=np.float32)
        expected=model(x).numpy()
        model.save(folder+"/model")
        loaded=tf_keras.models.load_model(folder+"/model",compile=False)
        np.testing.assert_allclose(loaded(x).numpy(),expected)
        results.append({"check":"keras_save_reload_untrained","ok":True})
    finally:
        shutil.rmtree(folder)
except Exception as e:
    results.append({"check":"keras_save_reload_untrained","ok":False,"error":str(e)})
Path("/artifacts/runtime_smoke.json").write_text(json.dumps({"python":sys.version,"results":results},ensure_ascii=False,indent=2))
for x in results: print(json.dumps(x,ensure_ascii=False))
raise SystemExit(0 if all(x["ok"] for x in results) else 1)
