"""Download once, resume partial archive, verify ZIP and extract without loading pickle."""
from pathlib import Path, PurePosixPath
import urllib.request, json, hashlib, zipfile, time, shutil, stat, zlib
ROOT=Path(__file__).resolve().parents[1]
URL="https://funrec-datasets.s3.eu-west-3.amazonaws.com/funrec-movielens-1m.zip"
archive=ROOT/"data/funrec-movielens-1m.zip"
partial=archive.with_suffix(".zip.partial")
head=urllib.request.urlopen(urllib.request.Request(URL,method="HEAD"),timeout=30)
size=int(head.headers["Content-Length"])
etag=head.headers.get("ETag")
state=partial.with_suffix(".state.json")
if partial.exists():
    if not state.exists() or json.loads(state.read_text()).get("etag")!=etag:
        raise RuntimeError("Partial archive source changed or has no state; manual inspection required")
state.write_text(json.dumps({"url":URL,"etag":etag,"bytes":size}))
if not archive.exists():
    for attempt in range(3):
        offset=partial.stat().st_size if partial.exists() else 0
        if offset==size: break
        if offset>size: raise RuntimeError("Partial archive exceeds expected size")
        try:
            headers={"Range":f"bytes={offset}-"} if offset else {}
            with urllib.request.urlopen(urllib.request.Request(URL,headers=headers),timeout=45) as response:
                if offset and (response.status!=206 or not response.headers.get("Content-Range","").startswith(f"bytes {offset}-")):
                    raise RuntimeError("Server did not honor resume range")
                with partial.open("ab" if offset else "wb") as output:
                    last=time.monotonic()
                    while True:
                        chunk=response.read(1024*1024)
                        if not chunk: break
                        output.write(chunk); offset+=len(chunk)
                        if time.monotonic()-last>=20:
                            print(f"download_bytes={offset} total_bytes={size}",flush=True);last=time.monotonic()
            if partial.stat().st_size==size: break
        except Exception as error:
            print(f"attempt={attempt+1} error={type(error).__name__}: {error}",flush=True)
            if attempt==2: raise
            time.sleep(2**attempt)
    if not partial.exists() or partial.stat().st_size!=size: raise RuntimeError("Incomplete archive")
    partial.rename(archive)
if archive.stat().st_size!=size: raise RuntimeError("Archive length mismatch")
h=hashlib.sha256()
with archive.open("rb") as f:
    for block in iter(lambda:f.read(8*1024*1024),b""):h.update(block)
if h.hexdigest()!='989d9677930fcb716cdc0e318484c9dfc515a482963eb0a8c5a4fd5dfce76abb':raise RuntimeError('Pinned archive SHA256 mismatch')
raw=ROOT/"data/raw"
manifest=[]
with zipfile.ZipFile(archive) as z:
    for info in z.infolist():
        p=PurePosixPath(info.filename)
        if p.is_absolute() or ".." in p.parts or not p.parts or p.parts[0]!="funrec-movielens-1m":raise RuntimeError("Unsafe ZIP member")
        if stat.S_ISLNK(info.external_attr>>16):raise RuntimeError("ZIP symlink rejected")
        if any(":" in part or "\\" in part for part in p.parts):raise RuntimeError("Unsafe path component")
        manifest.append({"name":info.filename,"bytes":info.file_size,"crc32":info.CRC})
    bad=z.testzip()
    if bad:raise RuntimeError("ZIP CRC failure: "+bad)
    for info in z.infolist():
        parts=PurePosixPath(info.filename).parts[1:]
        if not parts:continue
        target=raw.joinpath(*parts)
        if info.is_dir():target.mkdir(parents=True,exist_ok=True);continue
        if target.exists():
            crc=0
            with target.open('rb') as existing:
                for block in iter(lambda:existing.read(1024*1024),b''):crc=zlib.crc32(block,crc)
            if target.stat().st_size!=info.file_size or crc!=info.CRC:raise RuntimeError('Existing extraction differs; refusing overwrite: '+str(target))
            continue
        target.parent.mkdir(parents=True,exist_ok=True)
        with z.open(info) as src,target.open("xb") as dst:shutil.copyfileobj(src,dst)
report={"url":URL,"etag":etag,"archive_bytes":size,"sha256":h.hexdigest(),"zip_crc_ok":True,"files":manifest,"pickle_loaded":False,"license_and_id_mapping":"not yet verified"}
(ROOT/"reports/DATA_DOWNLOAD.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
state.unlink(missing_ok=True)
print(json.dumps({k:v for k,v in report.items() if k!="files"},ensure_ascii=False),flush=True)

