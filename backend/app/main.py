from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.visitor_sessions import router as visitor_sessions_router
from app.config import settings
from app.db import get_db
from app.lifespan import lifespan

app = FastAPI(title="SmartCampus AI API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
app.include_router(visitor_sessions_router)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe: the API process is up (does not touch the database)."""
    return {"status": "ok"}


@app.get("/health/db")
def health_db(db: Session = Depends(get_db)) -> dict[str, str]:
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
    return {"status": "ok"}
