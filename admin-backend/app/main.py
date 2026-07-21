from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    from app.database import async_session
    from app.seed import seed_admin_user

    async with async_session() as db:
        await seed_admin_user(db)
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.api.auth import router as auth_router  # noqa: E402
from app.api.audit import router as audit_router  # noqa: E402
from app.api.backends import router as backends_router  # noqa: E402
from app.api.capabilities import router as capabilities_router  # noqa: E402
from app.api.companies import router as companies_router  # noqa: E402
from app.api.governance import router as governance_router  # noqa: E402
from app.api.knowledge import router as knowledge_router  # noqa: E402
from app.api.providers import router as providers_router  # noqa: E402
from app.api.prompts import router as prompts_router  # noqa: E402
from app.api.skills import router as skills_router  # noqa: E402
from app.api.sync import router as sync_router  # noqa: E402
from app.api.templates import router as templates_router  # noqa: E402

app.include_router(auth_router)
app.include_router(companies_router)
app.include_router(capabilities_router)
app.include_router(skills_router)
app.include_router(prompts_router)
app.include_router(templates_router)
app.include_router(knowledge_router)
app.include_router(providers_router)
app.include_router(backends_router)
app.include_router(governance_router)
app.include_router(audit_router)
app.include_router(sync_router)


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "admin-backend"}


def run():
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=True)
