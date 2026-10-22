import logging
from fastapi import Depends, FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.config import get_settings
from app.database import get_db
from app.routers import agent, ai, menu, orders
from app.services.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationRuleError,
)

logger = logging.getLogger(__name__)
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


# Domain exception handlers mapping service exceptions to HTTP responses
@app.exception_handler(NotFoundError)
async def not_found_exception_handler(_: Request, exc: NotFoundError):
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": exc.message, "code": exc.code},
    )


@app.exception_handler(ValidationRuleError)
async def validation_rule_exception_handler(_: Request, exc: ValidationRuleError):
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": exc.message, "code": exc.code},
    )


@app.exception_handler(ConflictError)
async def conflict_exception_handler(_: Request, exc: ConflictError):
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": exc.message, "code": exc.code},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(_: Request, exc: Exception):
    logger.exception("Unhandled server exception: %s", exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "An unexpected internal server error occurred.",
            "code": "INTERNAL_SERVER_ERROR",
        },
    )


# Register Routers
app.include_router(agent.router)
app.include_router(ai.router)
app.include_router(menu.router)
app.include_router(orders.router)


# Health Endpoints
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
