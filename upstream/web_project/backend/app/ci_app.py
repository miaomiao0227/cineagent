"""Minimal CI API: synthetic DB fixtures, no datasets, weights or external LLM."""
from fastapi import FastAPI
from app.behavior.api import router as behaviors
from app.jobs.api import router as jobs
from app.api.v1.endpoints.ratings import router as ratings
from app.behavior.catalogue import detail
from app.api.deps import get_db
from fastapi import Depends
from app.observability import router as metrics,install
app=FastAPI();app.include_router(behaviors);app.include_router(jobs);app.include_router(ratings,prefix='/api');app.include_router(metrics);install(app)

@app.get('/api/movies/{movie_id}')
def movie(movie_id:int,db=Depends(get_db)):return detail(db,movie_id)

from app.api.v1.endpoints.users import router as users_router
app.include_router(users_router,prefix="/api")
