# 企业制度修订管理平台 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a privatized v1 platform for internal policy revision: Markdown-centric drafting, consultation workflow, LLM-assisted draft/patch, and PDF publish — with audit trail.

**Architecture:** Modular monolith — FastAPI (`apps/api`) + ARQ worker (`apps/worker`) + React SPA (`apps/web`). PostgreSQL for metadata/workflow; MinIO for docx/pdf/md blobs; Redis for queue. LLM calls only from worker via OpenAI-compatible Xiaomi gateway.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, ARQ, PostgreSQL 16, Redis 7, MinIO, React 18, Vite, TypeScript, pytest, httpx, pandoc (docx), WeasyPrint (pdf), OpenAI Python SDK

**Spec:** `docs/superpowers/specs/2026-05-28-policy-revision-platform-design.md`

---

## File Structure Map

| Path | Responsibility |
|------|----------------|
| `apps/api/main.py` | FastAPI app factory, router mount, `/health` |
| `apps/api/config.py` | Pydantic settings from env |
| `apps/api/db/session.py` | SQLAlchemy engine + session |
| `apps/api/models/` | ORM: User, Policy, PolicyVersion, Revision, Comment, AuditEvent, LlmSuggestion |
| `apps/api/schemas/` | Pydantic request/response DTOs |
| `apps/api/services/sections.py` | Parse MD headings → section tree + stable IDs |
| `apps/api/services/workflow.py` | Revision state machine + publish gates |
| `apps/api/services/storage.py` | MinIO upload/download + sha256 |
| `apps/api/services/audit.py` | Append-only audit writer |
| `apps/api/routers/` | HTTP: auth, policies, revisions, comments, export, ai |
| `apps/api/ai/client.py` | OpenAI-compatible LLM client |
| `apps/api/ai/templates/` | YAML prompts: `draft_v1.yaml`, `comment_patch_v1.yaml` |
| `apps/api/ai/suggestions.py` | Parse/validate LLM JSON suggestions |
| `apps/worker/main.py` | ARQ worker settings + task registration |
| `apps/worker/tasks/convert.py` | docx→md, md→pdf jobs |
| `apps/worker/tasks/llm.py` | Section-chunked draft + comment patch jobs |
| `apps/web/src/` | React SPA (中文 UI) |
| `packages/shared/openapi/` | Generated TS types (optional phase) |
| `deploy/docker-compose.yml` | postgres, redis, minio, api, worker, web |
| `tests/` | pytest unit + API integration |

---

### Task 1: Monorepo scaffold + dev tooling

**Files:**
- Create: `pyproject.toml`
- Create: `apps/api/__init__.py`
- Create: `apps/worker/__init__.py`
- Create: `tests/conftest.py`
- Create: `Makefile`
- Modify: `.env.example`

- [ ] **Step 1: Write the failing test**

Create `tests/test_health.py`:

```python
import pytest
from httpx import ASGITransport, AsyncClient

from apps.api.main import create_app


@pytest.mark.asyncio
async def test_health_returns_ok():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/glace/Downloads/baidu_sync/py/code-Master/easy-regulations && python -m pytest tests/test_health.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'apps'`

- [ ] **Step 3: Create pyproject.toml and minimal API**

Create `pyproject.toml`:

```toml
[project]
name = "easy-regulations"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.115.0",
  "uvicorn[standard]>=0.32.0",
  "pydantic-settings>=2.6.0",
  "sqlalchemy>=2.0.36",
  "asyncpg>=0.30.0",
  "alembic>=1.14.0",
  "httpx>=0.28.0",
  "python-multipart>=0.0.17",
  "pyyaml>=6.0.2",
  "openai>=1.57.0",
  "boto3>=1.35.0",
  "arq>=0.26.1",
  "python-jose[cryptography]>=3.3.0",
  "passlib[bcrypt]>=1.7.4",
  "weasyprint>=63.0",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.3.0",
  "pytest-asyncio>=0.24.0",
  "ruff>=0.8.0",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
pythonpath = ["."]
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py312"
```

Create `apps/api/config.py`:

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "easy-regulations"
    database_url: str = "postgresql+asyncpg://regulations:regulations@localhost:5432/regulations"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "dev-only-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 480

    minio_endpoint: str = "http://localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "policies"
    minio_region: str = "us-east-1"

    xiaomi_base_url: str = "https://api.xiaomi.com/v1"
    xiaomi_api_key: str = ""
    xiaomi_model: str = "MiMo-V2.5-Pro"

    auth_mode: str = "dev"  # dev | ldap


settings = Settings()
```

Create `apps/api/main.py`:

```python
from fastapi import FastAPI

from apps.api.config import settings


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


app = create_app()
```

Create empty `apps/api/__init__.py`, `apps/worker/__init__.py`, `tests/conftest.py`.

Update `.env.example` (remove real keys):

```env
DATABASE_URL=postgresql+asyncpg://regulations:regulations@localhost:5432/regulations
REDIS_URL=redis://localhost:6379/0
JWT_SECRET=dev-only-change-me
MINIO_ENDPOINT=http://localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=policies
XIAOMI_BASE_URL=https://api.xiaomi.com/v1
XIAOMI_API_KEY=
XIAOMI_MODEL=MiMo-V2.5-Pro
AUTH_MODE=dev
```

Create `Makefile`:

```makefile
.PHONY: install test run-api lint

install:
	pip install -e ".[dev]"

test:
	pytest -v

run-api:
	uvicorn apps.api.main:app --reload --host 0.0.0.0 --port 8000

lint:
	ruff check apps tests
```

- [ ] **Step 4: Install and run test**

Run:

```bash
cd /Users/glace/Downloads/baidu_sync/py/code-Master/easy-regulations
pip install -e ".[dev]"
pytest tests/test_health.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml apps/api tests Makefile .env.example
git commit -m "chore: scaffold FastAPI monorepo with health endpoint"
```

---

### Task 2: Database models + Alembic

**Files:**
- Create: `apps/api/db/session.py`
- Create: `apps/api/models/base.py`
- Create: `apps/api/models/user.py`
- Create: `apps/api/models/policy.py`
- Create: `apps/api/models/revision.py`
- Create: `apps/api/models/comment.py`
- Create: `apps/api/models/audit.py`
- Create: `apps/api/models/__init__.py`
- Create: `alembic.ini`
- Create: `apps/api/db/migrations/env.py`
- Create: `apps/api/db/migrations/versions/001_initial.py`
- Test: `tests/models/test_revision_state.py`

- [ ] **Step 1: Write the failing test**

Create `tests/models/test_revision_state.py`:

```python
from apps.api.models.revision import RevisionState, can_transition


def test_draft_to_in_consultation():
    assert can_transition(RevisionState.DRAFT, RevisionState.IN_CONSULTATION) is True


def test_draft_to_published_blocked():
    assert can_transition(RevisionState.DRAFT, RevisionState.PUBLISHED) is False


def test_in_consultation_to_in_revision():
    assert can_transition(RevisionState.IN_CONSULTATION, RevisionState.IN_REVISION) is True
```

- [ ] **Step 2: Run test — expect FAIL**

Run: `pytest tests/models/test_revision_state.py -v`

Expected: FAIL — `can_transition` not defined

- [ ] **Step 3: Implement models**

Create `apps/api/models/base.py`:

```python
import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


def new_uuid() -> uuid.UUID:
    return uuid.uuid4()
```

Create `apps/api/models/user.py`:

```python
import enum
import uuid

from sqlalchemy import Enum, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.models.base import Base, TimestampMixin


class UserRole(str, enum.Enum):
    OWNER = "owner"
    REVIEWER = "reviewer"
    POLICY_ADMIN = "policy_admin"
    READER = "reader"
    SYS_ADMIN = "sys_admin"


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(256))
    department: Mapped[str] = mapped_column(String(256), default="")
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.READER)
    password_hash: Mapped[str] = mapped_column(String(256), default="")
    is_active: Mapped[bool] = mapped_column(default=True)
```

Create `apps/api/models/policy.py`:

```python
import enum
import uuid
from datetime import date

from sqlalchemy import Date, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.models.base import Base, TimestampMixin


class PolicyStatus(str, enum.Enum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"


class Policy(Base, TimestampMixin):
    __tablename__ = "policies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(512))
    category: Mapped[str] = mapped_column(String(128), default="")
    owner_department: Mapped[str] = mapped_column(String(256))
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("policy_versions.id"), nullable=True
    )


class PolicyVersion(Base, TimestampMixin):
    __tablename__ = "policy_versions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    policy_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("policies.id"))
    version_label: Mapped[str] = mapped_column(String(32))
    status: Mapped[PolicyStatus] = mapped_column(Enum(PolicyStatus), default=PolicyStatus.ACTIVE)
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    markdown_key: Mapped[str] = mapped_column(String(512))
    pdf_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    content_sha256: Mapped[str] = mapped_column(String(64))
    section_tree: Mapped[dict] = mapped_column(JSONB, default=dict)
    published_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    policy: Mapped["Policy"] = relationship(back_populates="versions")


Policy.versions = relationship("PolicyVersion", back_populates="policy", foreign_keys=[PolicyVersion.policy_id])
```

Create `apps/api/models/revision.py`:

```python
import enum
import uuid

from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.models.base import Base, TimestampMixin


class RevisionState(str, enum.Enum):
    DRAFT = "draft"
    IN_CONSULTATION = "in_consultation"
    IN_REVISION = "in_revision"
    PENDING_PUBLISH = "pending_publish"
    PUBLISHED = "published"
    CANCELLED = "cancelled"


ALLOWED_TRANSITIONS: dict[RevisionState, set[RevisionState]] = {
    RevisionState.DRAFT: {RevisionState.IN_CONSULTATION, RevisionState.CANCELLED},
    RevisionState.IN_CONSULTATION: {
        RevisionState.IN_REVISION,
        RevisionState.IN_CONSULTATION,
        RevisionState.CANCELLED,
    },
    RevisionState.IN_REVISION: {
        RevisionState.IN_CONSULTATION,
        RevisionState.PENDING_PUBLISH,
        RevisionState.CANCELLED,
    },
    RevisionState.PENDING_PUBLISH: {RevisionState.PUBLISHED, RevisionState.CANCELLED},
    RevisionState.PUBLISHED: set(),
    RevisionState.CANCELLED: set(),
}


def can_transition(current: RevisionState, target: RevisionState) -> bool:
    return target in ALLOWED_TRANSITIONS.get(current, set())


class Revision(Base, TimestampMixin):
    __tablename__ = "revisions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    policy_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("policies.id"))
    base_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("policy_versions.id"))
    owner_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    state: Mapped[RevisionState] = mapped_column(Enum(RevisionState), default=RevisionState.DRAFT)
    change_brief: Mapped[str] = mapped_column(Text, default="")
    draft_markdown_key: Mapped[str] = mapped_column(String(512))
    draft_content_sha256: Mapped[str] = mapped_column(String(64), default="")
    target_version_label: Mapped[str] = mapped_column(String(32), default="")
```

Create `apps/api/models/comment.py`:

```python
import enum
import uuid

from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.models.base import Base, TimestampMixin


class CommentStatus(str, enum.Enum):
    OPEN = "open"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    DEFERRED = "deferred"


class Comment(Base, TimestampMixin):
    __tablename__ = "comments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    revision_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("revisions.id"))
    section_id: Mapped[str] = mapped_column(String(64))
    author_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[CommentStatus] = mapped_column(Enum(CommentStatus), default=CommentStatus.OPEN)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_suggestion_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    is_mandatory_reviewer: Mapped[bool] = mapped_column(default=True)
```

Create `apps/api/models/audit.py`:

```python
import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.models.base import Base, TimestampMixin


class AuditEvent(Base, TimestampMixin):
    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(128))
    resource_type: Mapped[str] = mapped_column(String(64))
    resource_id: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
```

Create `apps/api/models/__init__.py` exporting all models.

Create `apps/api/db/session.py`:

```python
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from apps.api.config import settings

engine = create_async_engine(settings.database_url, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
```

Initialize Alembic with autogenerate migration `001_initial.py` covering all tables (run `alembic init apps/api/db/migrations` then configure `target_metadata = Base.metadata`).

- [ ] **Step 4: Run tests**

Run: `pytest tests/models/test_revision_state.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/api/models apps/api/db alembic.ini tests/models
git commit -m "feat: add core ORM models and revision state machine"
```

---

### Task 3: Section parser (Markdown → section tree)

**Files:**
- Create: `apps/api/services/sections.py`
- Test: `tests/services/test_sections.py`

- [ ] **Step 1: Write the failing test**

Create `tests/services/test_sections.py`:

```python
from apps.api.services.sections import build_section_tree, ensure_section_ids


SAMPLE = """---
title: 测试制度
version: 1.0
---

# 总则 {#sec-1}

## 1.1 目的 {#sec-1-1}

为规范考勤。
"""


def test_build_section_tree_finds_headings():
    tree = build_section_tree(SAMPLE)
    ids = {node["section_id"] for node in tree}
    assert ids == {"sec-1", "sec-1-1"}


def test_ensure_section_ids_adds_missing_ids():
    md = "## 新章节\n\n内容"
    updated, tree = ensure_section_ids(md)
    assert "{#" in updated
    assert len(tree) >= 1
```

- [ ] **Step 2: Run — expect FAIL**

Run: `pytest tests/services/test_sections.py -v`

- [ ] **Step 3: Implement**

Create `apps/api/services/sections.py`:

```python
import re
import uuid

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)(?:\s+\{#([a-zA-Z0-9_-]+)\})?\s*$", re.MULTILINE)


def build_section_tree(markdown: str) -> list[dict]:
    tree: list[dict] = []
    for match in HEADING_RE.finditer(markdown):
        level = len(match.group(1))
        title = match.group(2).strip()
        section_id = match.group(3) or _slugify(title)
        tree.append({"section_id": section_id, "level": level, "title": title})
    return tree


def ensure_section_ids(markdown: str) -> tuple[str, list[dict]]:
    seen: set[str] = set()

    def repl(match: re.Match[str]) -> str:
        hashes = match.group(1)
        title = match.group(2).strip()
        existing = match.group(3)
        section_id = existing or _unique_slug(title, seen)
        return f"{hashes} {title} {{#{section_id}}}"

    updated = HEADING_RE.sub(repl, markdown)
    return updated, build_section_tree(updated)


def _slugify(title: str) -> str:
    base = re.sub(r"\s+", "-", title.lower())
    base = re.sub(r"[^a-z0-9\u4e00-\u9fff-]", "", base)
    return f"sec-{base[:32] or uuid.uuid4().hex[:8]}"


def _unique_slug(title: str, seen: set[str]) -> str:
    candidate = _slugify(title)
    if candidate not in seen:
        seen.add(candidate)
        return candidate
    suffix = uuid.uuid4().hex[:6]
    unique = f"{candidate}-{suffix}"
    seen.add(unique)
    return unique


def extract_section_body(markdown: str, section_id: str) -> str:
    pattern = re.compile(rf"^#{{1,6}}\s+.+?\{{#{re.escape(section_id)}\}}\s*$", re.MULTILINE)
    match = pattern.search(markdown)
    if not match:
        return ""
    start = match.end()
    next_heading = re.search(r"^#{1,6}\s+", markdown[start:], re.MULTILINE)
    end = start + next_heading.start() if next_heading else len(markdown)
    return markdown[start:end].strip()
```

- [ ] **Step 4: Run tests — PASS**

- [ ] **Step 5: Commit**

```bash
git add apps/api/services/sections.py tests/services
git commit -m "feat: parse markdown headings into stable section tree"
```

---

### Task 4: Dev auth (JWT) + RBAC dependency

**Files:**
- Create: `apps/api/services/auth.py`
- Create: `apps/api/routers/auth.py`
- Modify: `apps/api/main.py`
- Test: `tests/api/test_auth.py`

- [ ] **Step 1: Write failing test**

Create `tests/api/test_auth.py`:

```python
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from apps.api.main import create_app
from apps.api.models.base import Base
from apps.api.models.user import User, UserRole
from apps.api.db.session import get_db
from passlib.context import CryptContext

pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


@pytest.fixture
async def client():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        session.add(
            User(
                username="owner1",
                display_name="经办人",
                department="人力部",
                role=UserRole.OWNER,
                password_hash=pwd.hash("secret"),
            )
        )
        await session.commit()

    app = create_app()

    async def override_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    await engine.dispose()


@pytest.mark.asyncio
async def test_login_returns_token(client):
    response = await client.post("/api/auth/login", json={"username": "owner1", "password": "secret"})
    assert response.status_code == 200
    assert "access_token" in response.json()
```

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Implement auth router + service**

Create `apps/api/services/auth.py` with `authenticate_user`, `create_access_token`, `get_current_user` dependency using `HTTPBearer`.

Create `apps/api/routers/auth.py`:

```python
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.db.session import get_db
from apps.api.models.user import User
from apps.api.services.auth import authenticate_user, create_access_token

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = await authenticate_user(db, body.username, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = create_access_token(str(user.id), user.role.value)
    return TokenResponse(access_token=token)
```

Wire router in `create_app()`.

Add `aiosqlite` to dev dependencies for tests.

- [ ] **Step 4: PASS**

- [ ] **Step 5: Commit**

```bash
git commit -m "feat: add dev JWT login and RBAC foundation"
```

---

### Task 5: Policy + Revision CRUD APIs

**Files:**
- Create: `apps/api/services/policies.py`
- Create: `apps/api/services/revisions.py`
- Create: `apps/api/routers/policies.py`
- Create: `apps/api/routers/revisions.py`
- Test: `tests/api/test_revisions_workflow.py`

- [ ] **Step 1: Write failing integration test**

Create `tests/api/test_revisions_workflow.py` covering:

1. Create policy
2. Create revision in `DRAFT`
3. `POST /api/revisions/{id}/transition` → `in_consultation`
4. Invalid transition → 409

Example assertion:

```python
@pytest.mark.asyncio
async def test_transition_draft_to_consultation(auth_client):
    policy = await auth_client.post("/api/policies", json={
        "code": "HR-001", "title": "考勤办法", "owner_department": "人力部"
    })
    revision = await auth_client.post("/api/revisions", json={
        "policy_id": policy.json()["id"],
        "change_brief": "根据新劳动法调整年假",
    })
    resp = await auth_client.post(
        f"/api/revisions/{revision.json()['id']}/transition",
        json={"target_state": "in_consultation"},
    )
    assert resp.status_code == 200
    assert resp.json()["state"] == "in_consultation"
```

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Implement services**

`apps/api/services/revisions.py` must:

- Create revision with empty draft MD in storage (in-memory stub for unit tests; MinIO in Task 6)
- Call `can_transition` + audit log on transition
- Enforce `change_brief` min length before leaving `DRAFT`

Implement routers with owner-only edit checks.

- [ ] **Step 4: PASS**

- [ ] **Step 5: Commit**

```bash
git commit -m "feat: policy and revision CRUD with workflow transitions"
```

---

### Task 6: MinIO storage layer

**Files:**
- Create: `apps/api/services/storage.py`
- Test: `tests/services/test_storage.py`

- [ ] **Step 1: Write failing test with moto or mock boto3**

```python
from unittest.mock import MagicMock, patch
from apps.api.services.storage import StorageService


def test_put_and_get_roundtrip():
    with patch("apps.api.services.storage.boto3.client") as mock_client:
        s3 = MagicMock()
        mock_client.return_value = s3
        store = {"obj": b"# md"}
        s3.put_object.side_effect = lambda **kw: store.update({kw["Key"]: kw["Body"]})
        s3.get_object.side_effect = lambda **kw: {"Body": MagicMock(read=lambda: store[kw["Key"]])}
        svc = StorageService()
        key = svc.put_bytes(b"# md", suffix=".md")
        assert svc.get_bytes(key) == b"# md"
```

- [ ] **Step 2–4: Implement StorageService with sha256 + key naming `policies/{policy_id}/{revision_id}/{uuid}.md`**

- [ ] **Step 5: Commit**

```bash
git commit -m "feat: MinIO storage service with content hashing"
```

---

### Task 7: Comments API + publish gates

**Files:**
- Create: `apps/api/services/comments.py`
- Create: `apps/api/services/workflow.py`
- Create: `apps/api/routers/comments.py`
- Test: `tests/api/test_comments_gate.py`

- [ ] **Step 1: Failing test — open comment blocks pending_publish**

```python
@pytest.mark.asyncio
async def test_open_comment_blocks_pending_publish(auth_client, revision_in_revision):
    await auth_client.post(f"/api/revisions/{revision_in_revision}/comments", json={
        "section_id": "sec-1", "body": "请明确年假天数"
    })
    resp = await auth_client.post(
        f"/api/revisions/{revision_in_revision}/transition",
        json={"target_state": "pending_publish"},
    )
    assert resp.status_code == 409
    assert "open comments" in resp.json()["detail"].lower()
```

- [ ] **Step 3: Implement `workflow.assert_can_enter_pending_publish(revision_id, db)`**

Rules:

- No `CommentStatus.OPEN`
- `REJECTED`/`DEFERRED` require `resolution_note`

- [ ] **Step 5: Commit**

```bash
git commit -m "feat: comments API and publish gate validation"
```

---

### Task 8: Audit service (append-only)

**Files:**
- Create: `apps/api/services/audit.py`
- Modify: revision/comment/ai routers to call audit
- Test: `tests/services/test_audit.py`

- [ ] **Step 1: Test audit row created on transition**

```python
@pytest.mark.asyncio
async def test_audit_on_transition(db_session, revision):
    from apps.api.services.audit import record_event
    await record_event(db_session, actor_id=None, action="revision.transition", resource_type="revision", resource_id=str(revision.id), payload={"to": "in_consultation"})
    rows = (await db_session.execute(select(AuditEvent))).scalars().all()
    assert len(rows) == 1
```

- [ ] **Step 5: Commit**

```bash
git commit -m "feat: append-only audit logging"
```

---

### Task 9: ARQ worker + md→PDF export

**Files:**
- Create: `apps/worker/main.py`
- Create: `apps/worker/tasks/convert.py`
- Create: `apps/api/services/export.py`
- Create: `apps/api/routers/export.py`
- Test: `tests/worker/test_pdf_export.py`

- [ ] **Step 1: Test HTML wrapper renders title**

```python
from apps.api.services.export import markdown_to_html


def test_markdown_to_html_includes_title():
    html = markdown_to_html("# 制度\n\n内容", title="考勤办法", version="2.0")
    assert "考勤办法" in html
    assert "2.0" in html
```

- [ ] **Step 3: Implement `markdown_to_html` + WeasyPrint PDF in worker task `export_pdf_task(revision_id)`**

- [ ] **Step 4: API `POST /api/revisions/{id}/publish` enqueues job; poll `GET /api/jobs/{id}`**

- [ ] **Step 5: Commit**

```bash
git commit -m "feat: async PDF publish via ARQ worker"
```

---

### Task 10: docx import (pandoc)

**Files:**
- Create: `apps/worker/tasks/convert.py` function `docx_to_markdown_task`
- Modify: `apps/api/routers/revisions.py` upload endpoint
- Test: `tests/worker/test_docx_import.py`

- [ ] **Step 1: Test with fixture `tests/fixtures/sample.docx`**

```python
import subprocess
from pathlib import Path


def test_pandoc_available():
    result = subprocess.run(["pandoc", "--version"], capture_output=True, text=True)
    assert result.returncode == 0
```

- [ ] **Step 3: Worker runs `pandoc -f docx -t gfm`, then `ensure_section_ids`**

- [ ] **Step 5: Commit**

```bash
git commit -m "feat: docx import to markdown via pandoc worker"
```

---

### Task 11: LLM client + draft suggestions

**Files:**
- Create: `apps/api/ai/client.py`
- Create: `apps/api/ai/templates/draft_v1.yaml`
- Create: `apps/api/ai/suggestions.py`
- Create: `apps/api/models/llm_suggestion.py`
- Create: `apps/worker/tasks/llm.py`
- Create: `apps/api/routers/ai.py`
- Test: `tests/ai/test_suggestions_parse.py`

- [ ] **Step 1: Test JSON schema validation**

```python
from apps.api.ai.suggestions import parse_draft_suggestions


def test_parse_draft_suggestions_valid():
    raw = [{"section_id": "sec-1", "action": "replace", "suggested_markdown": "新文本", "rationale": "说明"}]
    result = parse_draft_suggestions(raw)
    assert result[0].section_id == "sec-1"
```

- [ ] **Step 3: Implement OpenAI client**

```python
from openai import AsyncOpenAI
from apps.api.config import settings

def get_llm_client() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=settings.xiaomi_api_key, base_url=settings.xiaomi_base_url)
```

- [ ] **Step 4: Worker task loops sections, stores `LlmSuggestion` rows, audit `llm.draft.generated`**

- [ ] **Step 5: API `POST /api/revisions/{id}/ai/draft` enqueues; `POST /api/ai/suggestions/{id}/accept` applies patch**

- [ ] **Step 6: Commit**

```bash
git commit -m "feat: LLM draft generation with per-section accept flow"
```

---

### Task 12: LLM comment → patch

**Files:**
- Create: `apps/api/ai/templates/comment_patch_v1.yaml`
- Modify: `apps/worker/tasks/llm.py`
- Test: `tests/ai/test_comment_patch.py`

- [ ] **Step 1: Test accept patch updates markdown and comment status**

- [ ] **Step 3: `POST /api/comments/{id}/ai/patch` enqueues job using `extract_section_body`**

- [ ] **Step 5: Commit**

```bash
git commit -m "feat: LLM comment patch suggestions with accept flow"
```

---

### Task 13: Publish flow (immutable PDF + supersede)

**Files:**
- Modify: `apps/api/services/revisions.py`
- Test: `tests/api/test_publish.py`

- [ ] **Step 1: Test publish creates PolicyVersion, marks old superseded**

```python
@pytest.mark.asyncio
async def test_publish_creates_new_policy_version(auth_client, ready_revision):
    resp = await auth_client.post(f"/api/revisions/{ready_revision}/publish")
    assert resp.status_code == 202
    # after job completes:
    policy = await auth_client.get(f"/api/policies/{policy_id}")
    assert policy.json()["current_version"]["version_label"] == "2.0"
```

- [ ] **Step 5: Commit**

```bash
git commit -m "feat: publish revision to immutable policy version"
```

---

### Task 14: React SPA scaffold (中文 UI)

**Files:**
- Create: `apps/web/package.json`
- Create: `apps/web/vite.config.ts`
- Create: `apps/web/src/main.tsx`
- Create: `apps/web/src/App.tsx`
- Create: `apps/web/src/api/client.ts`

- [ ] **Step 1: Manual smoke — `npm run dev` shows 登录页**

- [ ] **Step 3: Pages (minimal v1)**

| Route | 功能 |
|-------|------|
| `/login` | 登录 |
| `/policies` | 制度库列表 |
| `/policies/:id` | 制度详情 + 版本历史 |
| `/revisions/:id` | 修订工作台：MD 编辑器、Mermaid 预览、意见列表、LLM 建议侧栏 |
| `/revisions/:id/review` | 评审人提交意见 |

Use `@uiw/react-md-editor` + `mermaid` for preview.

- [ ] **Step 5: Commit**

```bash
git commit -m "feat: React SPA with revision workspace UI"
```

---

### Task 15: Docker Compose (私有化 v1)

**Files:**
- Create: `deploy/docker-compose.yml`
- Create: `deploy/Dockerfile.api`
- Create: `deploy/Dockerfile.worker`
- Create: `deploy/Dockerfile.web`
- Create: `deploy/nginx.conf`

- [ ] **Step 1: `docker compose up` brings all services healthy**

`deploy/docker-compose.yml` services: `postgres`, `redis`, `minio`, `api`, `worker`, `web`, `nginx`.

- [ ] **Step 3: Nginx routes `/api` → api:8000, `/` → web**

- [ ] **Step 5: Commit**

```bash
git commit -m "chore: docker compose stack for private deployment"
```

---

### Task 16: Seed data + README

**Files:**
- Create: `scripts/seed_dev.py`
- Create: `README.md`

- [ ] **Step 1: Seed creates admin, owner, reviewer, sample policy + revision**

Run: `python scripts/seed_dev.py`

- [ ] **Step 3: README documents 中文 quickstart, env vars, make targets**

- [ ] **Step 5: Commit**

```bash
git commit -m "docs: add README and dev seed script"
```

---

## Spec Coverage Self-Review

| Spec requirement | Task |
|------------------|------|
| 制度库 | Task 5, 13 |
| 修订任务 + 状态机 | Task 2, 5, 7 |
| Markdown + section_id | Task 3 |
| docx / pdf 流水线 | Task 9, 10 |
| 征求意见 + 意见锚定 | Task 7 |
| LLM 初稿 + 意见改稿 | Task 11, 12 |
| 发布门禁 | Task 7, 13 |
| RBAC + JWT/LDAP-ready | Task 4 |
| 审计 | Task 8 |
| 私有化部署 | Task 15 |
| MinIO 存储 | Task 6 |
| 中文 UI | Task 14 |
| 通知邮件 | **Deferred v1.1** — add `Task 17-email` if needed before pilot |
| LDAP 生产 | **Deferred** — `AUTH_MODE=ldap` stub in Task 4; implement bind in v1.1 |
| Webhook `revision.published` | **Deferred v1.1** |

No TBD placeholders in task steps. LDAP/email/webhook explicitly deferred with follow-up task names.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-28-policy-revision-platform.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks, fast iteration  
2. **Inline Execution** — execute tasks in this session using executing-plans, batch execution with checkpoints  

**Which approach?**
