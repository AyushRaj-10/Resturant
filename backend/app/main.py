from fastapi import FastAPI, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.config import get_settings
from app.database import get_db

settings = get_settings()

app = FastAPI(
    title="Restaurant Order Management System",
    version="0.1.0",
    description="Backend API for Restaurant Order Management System with multi-agent architecture.",
)

# Enable CORS for local frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["Health"])
def health_check() -> dict[str, str]:
    """Basic health check endpoint."""
    return {"status": "ok"}


@app.get("/health/db", tags=["Health"])
def health_db_check(db: Session = Depends(get_db)):
    """Check connectivity to MySQL database."""
    try:
        db.execute(text("SELECT 1"))
        return {
            "status": "ok",
            "database": "reachable",
            "message": "Successfully connected to MySQL database",
        }
    except Exception as exc:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "error",
                "database": "unreachable",
                "message": f"Could not connect to MySQL database: {exc}",
            },
        )
