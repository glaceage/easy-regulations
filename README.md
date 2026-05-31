# Easy Regulations

**[中文文档](README.zh-CN.md)**

Enterprise policy revision platform for drafting regulations in Markdown, multi-department consultation, LLM-assisted rewriting, PDF publishing, and full audit trails. Designed for private/on-prem deployment.

## Architecture

| Component | Stack | Role |
|-----------|-------|------|
| API | FastAPI + SQLAlchemy 2 | Auth, policy library, revision workflow, comments, export, AI endpoints |
| Worker | ARQ | docx→md, md→pdf, LLM draft & comment-driven patches |
| Web | React 18 + Vite + TypeScript | Chinese UI (bilingual README) |
| Database | PostgreSQL 16 | Users, policies, revision state, audit |
| Object storage | MinIO (S3-compatible) | Markdown / PDF / docx |
| Queue | Redis 7 | ARQ job queue |

```
┌─────────┐     ┌─────────┐     ┌──────────┐
│  Web    │────▶│  API    │────▶│ Postgres │
│ (React) │     │(FastAPI)│     └──────────┘
└─────────┘     │         │     ┌──────────┐
                │         │────▶│  MinIO   │
                └────┬────┘     └──────────┘
                     │
                ┌────▼────┐     ┌──────────┐
                │ Worker  │────▶│  Redis   │
                │  (ARQ)  │     └──────────┘
                └─────────┘
```

## Revision workflow

| State | Page | Owner actions |
|-------|------|----------------|
| `draft` | Revision workspace | Edit Markdown, AI draft, save, **submit for consultation** |
| `in_consultation` | Consultation | Assign reviewers; reviewers comment by **section title** (not raw IDs) |
| `in_revision` | Revision workspace | Edit draft, resolve comments, AI patches, submit for publish |
| `pending_publish` | Publish review | Admin preview PDF and publish |
| `published` | Read-only snapshot | View final Markdown / PDF |

Headings in drafts automatically receive stable `{#section_id}` anchors on save so comments and AI patches stay anchored to the right clause.

## Quick start

### 1. Python environment

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env        # edit as needed
```

### 2. Start the stack (Docker Compose)

Run from the **repository root**. Do **not** execute the YAML file directly:

```bash
make up
```

Equivalent:

```bash
docker compose --project-directory . -f deploy/docker-compose.yml up -d --build
```

Common mistake (causes `permission denied`):

```bash
# Wrong — treats the config file as a shell command
deploy/docker-compose.yml up -d --build
```

Endpoints:

- App (via Nginx): http://localhost:8080
- MinIO console: http://localhost:9001

The API container runs `alembic upgrade head` on start. Seed dev data once:

```bash
# Option A: on the host (.env DATABASE_URL → localhost:5432)
alembic upgrade head
python scripts/seed_dev.py

# Option B: inside Docker (recommended)
docker compose --project-directory . -f deploy/docker-compose.yml run --rm api python scripts/seed_dev.py
```

### 3. Local API development

```bash
make run-api
# OpenAPI: http://localhost:8000/docs
```

### 4. Frontend development

```bash
cd apps/web
npm install
npm run dev
# http://localhost:5173
```

### 5. Tests

```bash
make test
# or: SYNC_JOBS=1 pytest tests/ -q
```

## Dev seed accounts

After `seed_dev.py`, log in with password **`dev123`**:

| Username | Role | Purpose |
|----------|------|---------|
| `admin` | policy_admin | Publish approved revisions |
| `owner1` | owner | Draft and manage revisions |
| `reviewer1` | reviewer | Submit consultation comments |

Sample data: policy **HR-001 Attendance Policy**, published **v1.0**, plus a **draft** revision targeting **v2.0**.

## Makefile

| Command | Description |
|---------|-------------|
| `make install` | `pip install -e ".[dev]"` |
| `make test` | Run pytest |
| `make run-api` | API with hot reload |
| `make lint` | ruff check |
| `make up` | Build and start full Docker stack |
| `make down` | Stop Docker stack |

## Environment variables

Copy `.env.example` to `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5432/easy_regulations` | PostgreSQL |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis |
| `JWT_SECRET` | `change-me-in-production` | JWT signing secret |
| `JWT_ALGORITHM` | `HS256` | JWT algorithm |
| `JWT_EXPIRE_MINUTES` | `60` | Token TTL (minutes) |
| `MINIO_ENDPOINT` | `http://localhost:9000` | MinIO / S3 endpoint |
| `MINIO_ACCESS_KEY` | `minioadmin` | Access key |
| `MINIO_SECRET_KEY` | `minioadmin` | Secret key |
| `MINIO_BUCKET` | `easy-regulations` | Bucket name |
| `MINIO_REGION` | `us-east-1` | S3 region |
| `XIAOMI_BASE_URL` | `https://api.xiaomi.com/v1` | LLM gateway URL |
| `XIAOMI_API_KEY` | (empty) | LLM API key |
| `XIAOMI_MODEL` | `MiMo-V2.5-Pro` | Model name |
| `AUTH_MODE` | `dev` | `dev` (local accounts) or `ldap` (reserved) |

## Repository layout

```
apps/api/          FastAPI backend
apps/worker/       ARQ workers
apps/web/          React frontend
deploy/            Docker Compose & deployment
scripts/           Dev/ops scripts
tests/             pytest suite
docs/superpowers/  Design specs
```

## Documentation

- [Policy revision platform design (中文)](docs/superpowers/specs/2026-05-28-policy-revision-platform-design.md)
- [Revision workflow UI spec (中文)](docs/superpowers/specs/2026-05-28-revision-workflow-ui-spec.md)

## License

Internal use only — not for public redistribution.
