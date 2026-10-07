import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from sqlalchemy import text

from app.db import create_session_factory
from app.api import router
from app.profile_api import router as profile_router
from app.analytics.api import router as analytics_router
from app.recommendations.api import router as recommendations_router
from app.intelligence.api import router as intelligence_router
from app.ai.api import router as ai_router
from app.market.api import router as market_router
from app.mobility.api import router as mobility_router

app = FastAPI(title="МЕСТО API", version="0.1.0")
app.include_router(router)
app.include_router(profile_router)
app.include_router(analytics_router)
app.include_router(recommendations_router)
app.include_router(intelligence_router)
app.include_router(ai_router)
app.include_router(market_router)
app.include_router(mobility_router)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    """Check API and database connectivity; unhealthy dependencies return 503."""
    from fastapi import HTTPException

    try:
        _, engine = create_session_factory()
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        engine.dispose()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
    return {"status": "ok", "database": "ok"}
