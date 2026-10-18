"""FastAPI 应用入口"""

import logging

# 配置日志，显示 INFO 级别及以上
logging.basicConfig(
    level=logging.INFO,    
    format="%(levelname)s: %(message)s",
)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.config import settings
from app.api.v1.api import api_router
from app.api.v1.endpoints.health import router as health_router

# 创建 FastAPI 应用实例
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug,
)

# CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境请适当配置
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载电影海报静态文件目录
poster_dir = Path(settings.poster_dir)
if poster_dir.exists():
    app.mount(f"{settings.api_prefix}/posters", StaticFiles(directory=str(poster_dir)), name="posters")
    print(f"✓ 海报服务已启动: {poster_dir} -> {settings.api_prefix}/posters")
else:
    print(f"⚠ 警告: 海报目录不存在: {poster_dir}")
    print(f"  在创建目录之前，海报请求将返回 404")


@app.get("/")
async def root():
    """根路由"""
    return {
        "message": "欢迎使用 FunRec 电影推荐系统",
        "version": settings.app_version,
        "docs": "/docs",
    }


# 在根路径下注册健康检查路由（无前缀）
app.include_router(health_router)
from app.cineagent.api import router as conversation_router, initialize as initialize_conversation
app.include_router(conversation_router)
app.on_event('startup')(initialize_conversation)

# 注册 API 路由，使用 /api 前缀
app.include_router(api_router, prefix=settings.api_prefix)




@app.on_event("startup")
def warm_recommendation_models():
    """Load local models before serving the first recommendation request."""
    from app.database import SessionLocal
    from app.models import Movie
    from online.pipeline import get_pipeline
    app.state.recommendation_ready = False
    try:
        pipeline = get_pipeline()
        with SessionLocal() as db:
            pipeline.set_movie_genre_map(db.query(Movie).all())
        recall = pipeline.recall_service.resource_manager
        app.state.recommendation_ready = bool(
            recall.user_model is not None and recall.item_embedding_matrix is not None
            and pipeline.is_ranking_ready
        )
        logging.info("Local recommendation warmup ready=%s", app.state.recommendation_ready)
    except Exception:
        logging.exception("Local recommendation warmup failed")


@app.get("/ready")
def recommendation_readiness():
    from fastapi.responses import JSONResponse
    ready = bool(getattr(app.state, "recommendation_ready", False))
    return JSONResponse(status_code=200 if ready else 503, content={"ready": ready, "model_version": "rec-v1"})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )


