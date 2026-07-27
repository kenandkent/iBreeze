"""FastAPI application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ibreeze_backend.api.errors import (
    ProblemDetailError,
    generic_exception_handler,
    problem_detail_handler,
)
from ibreeze_backend.auth.router import admin_router
from ibreeze_backend.auth.router import router as auth_router
from ibreeze_backend.catalog.router import router as catalog_router
from ibreeze_backend.compatibility.router import public_router as compatibility_public_router
from ibreeze_backend.compatibility.router import router as compatibility_router
from ibreeze_backend.middleware import AuditMiddleware, IdempotencyMiddleware, RateLimitMiddleware, RequestLogMiddleware
from ibreeze_backend.observability.logging_config import get_logger, setup_logging
from ibreeze_backend.observability.router import router as audit_router
from ibreeze_backend.releases.router import admin_router as releases_admin_router
from ibreeze_backend.releases.router import public_router as releases_public_router
from ibreeze_backend.routers import health
from ibreeze_backend.settings import settings
from ibreeze_backend.skills.router import admin_router as skills_admin_router
from ibreeze_backend.skills.router import public_router as skills_public_router
from ibreeze_backend.users.router import router as admin_users_router

logger = get_logger("ibreeze.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_logging(level=settings.log_level, json_format=settings.log_json)
    logger.info("backend.startup", extra={"version": app.version, "log_level": settings.log_level})
    yield
    logger.info("backend.shutdown")


app = FastAPI(
    title="iBreeze Backend API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_exception_handler(ProblemDetailError, problem_detail_handler)  # type: ignore[arg-type]
app.add_exception_handler(Exception, generic_exception_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins or ["http://localhost:1420"],
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Request-ID", "Idempotency-Key"],
    allow_credentials=True,
    expose_headers=["X-Request-ID"],
    max_age=600,
)
app.add_middleware(RequestLogMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(AuditMiddleware)
app.add_middleware(IdempotencyMiddleware)

app.include_router(health.router)
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(releases_admin_router)
app.include_router(releases_public_router)
app.include_router(skills_admin_router)
app.include_router(skills_public_router)
app.include_router(admin_users_router)
app.include_router(catalog_router)
app.include_router(compatibility_router)
app.include_router(compatibility_public_router)
app.include_router(audit_router)
