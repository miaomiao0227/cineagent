"""Only run against a dedicated disposable CI database."""
import os
if os.getenv('CINEAGENT_CI')!='1':raise RuntimeError('Dedicated CI flag required')
from app.database import Base,engine,SessionLocal
from app import models
Base.metadata.create_all(engine,tables=[models.User.__table__,models.Movie.__table__,models.Rating.__table__])
with SessionLocal.begin() as db:
    for i in [1,2,3]:db.add(models.Movie(movie_id=i,title=f'Synthetic CI movie {i}',genres=['Drama'],description='Synthetic fixture, not MovieLens data'))
