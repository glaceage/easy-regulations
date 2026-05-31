# Easy Regulations — 企业制度修订管理平台

**[English README](README.md)**

面向企业内部的制度（规章）全生命周期管理平台：以 Markdown 为中心起草、多部门征求意见、LLM 辅助改稿、发布 PDF，并保留完整审计轨迹。支持私有化部署。

## 架构概览

| 组件 | 技术 | 职责 |
|------|------|------|
| API | FastAPI + SQLAlchemy 2 | 认证、制度库、修订工作流、意见、导出、AI 接口 |
| Worker | ARQ | docx→md、md→pdf、LLM 分段起草与意见改稿 |
| Web | React 18 + Vite + TypeScript | 中文管理界面 |
| 数据库 | PostgreSQL 16 | 用户、制度元数据、修订状态、审计 |
| 对象存储 | MinIO (S3 兼容) | Markdown / PDF / docx 文件 |
| 队列 | Redis 7 | ARQ 任务队列 |

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

## 修订工作流

| 状态 | 页面 | 经办人主要操作 |
|------|------|----------------|
| `draft` 起草 | 起草工作台 | 编辑正文、AI 初稿、保存、**提交征求意见** |
| `in_consultation` 征求意见 | 征求意见页 | 指定评审人；评审人按**章节标题**提意见（无需填写 sec-1 等内部 ID） |
| `in_revision` 改稿 | 起草工作台 | 按意见改稿、处理 AI 建议、**提交发布审核** |
| `pending_publish` 待发布 | 发布审核页 | 制度管理员预览 PDF 并发布 |
| `published` 已发布 | 只读快照 | 查看最终 Markdown / PDF |

保存草案时会自动为标题注入稳定的 `{#section_id}` 锚点，便于意见与 AI 改稿精确定位到条款。

## 快速开始

### 1. Python 环境

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env        # 按需修改
```

### 2. 启动基础设施（Docker Compose）

在**项目根目录**执行（不要直接运行 `deploy/docker-compose.yml`，那是配置文件，不是可执行命令）：

```bash
make up
```

等价于：

```bash
docker compose --project-directory . -f deploy/docker-compose.yml up -d --build
```

说明：

- `docker compose` — Docker 的编排命令
- `-f deploy/docker-compose.yml` — 指定 Compose 配置文件
- `up -d --build` — 构建镜像并在后台启动

常见错误（会报 `permission denied`）：

```bash
# ❌ 错误：把 yml 当成 shell 命令执行
deploy/docker-compose.yml up -d --build
```

服务入口：

- 应用（Nginx 反代）：http://localhost:8080
- MinIO 控制台：http://localhost:9001

首次启动后，API 容器会自动执行 `alembic upgrade head`。还需写入开发种子数据：

```bash
# 方式 A：在宿主机（需 .env 中 DATABASE_URL 指向 localhost:5432）
alembic upgrade head
python scripts/seed_dev.py

# 方式 B：在 Docker 内执行（推荐，与 Compose 环境一致）
docker compose --project-directory . -f deploy/docker-compose.yml run --rm api python scripts/seed_dev.py
```

### 3. 本地开发 API

```bash
make run-api
# API 文档: http://localhost:8000/docs
```

### 4. 前端开发

```bash
cd apps/web
npm install
npm run dev
# 默认: http://localhost:5173
```

### 5. 运行测试

```bash
make test
# 或: SYNC_JOBS=1 pytest tests/ -q
```

## 开发种子账号

运行 `python scripts/seed_dev.py` 后可用以下账号登录（密码均为 `dev123`）：

| 用户名 | 角色 | 说明 |
|--------|------|------|
| `admin` | policy_admin | 制度管理员，可发布 |
| `owner1` | owner | 经办人，负责修订起草 |
| `reviewer1` | reviewer | 评审人，可提交意见 |

示例数据：制度 **HR-001 考勤管理办法**，含已发布版本 **v1.0** 与处于 **draft** 状态的修订任务（目标版本 v2.0）。

## Makefile 常用命令

| 命令 | 说明 |
|------|------|
| `make install` | `pip install -e ".[dev]"` |
| `make test` | 运行 pytest |
| `make run-api` | 本地启动 API（热重载） |
| `make lint` | ruff 代码检查 |
| `make up` | Docker Compose 构建并后台启动全栈 |
| `make down` | Docker Compose 停止并清理 |

## 环境变量

复制 `.env.example` 为 `.env` 后配置：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5432/easy_regulations` | PostgreSQL 连接串 |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis 连接串 |
| `JWT_SECRET` | `change-me-in-production` | JWT 签名密钥 |
| `JWT_ALGORITHM` | `HS256` | JWT 算法 |
| `JWT_EXPIRE_MINUTES` | `60` | Token 有效期（分钟） |
| `MINIO_ENDPOINT` | `http://localhost:9000` | MinIO / S3 端点 |
| `MINIO_ACCESS_KEY` | `minioadmin` | 对象存储 Access Key |
| `MINIO_SECRET_KEY` | `minioadmin` | 对象存储 Secret Key |
| `MINIO_BUCKET` | `easy-regulations` | 存储桶名称 |
| `MINIO_REGION` | `us-east-1` | S3 区域 |
| `XIAOMI_BASE_URL` | `https://api.xiaomi.com/v1` | LLM 网关地址 |
| `XIAOMI_API_KEY` | （空） | LLM API Key |
| `XIAOMI_MODEL` | `MiMo-V2.5-Pro` | LLM 模型名 |
| `AUTH_MODE` | `dev` | 认证模式：`dev`（本地账号）或 `ldap`（预留） |

## 目录结构

```
apps/api/          FastAPI 后端
apps/worker/       ARQ 异步任务
apps/web/          React 前端
deploy/            Docker Compose 与部署配置
scripts/           开发与运维脚本
tests/             pytest 测试
docs/superpowers/  设计规格文档
```

## 设计文档

- [制度修订平台设计](docs/superpowers/specs/2026-05-28-policy-revision-platform-design.md)
- [修订工作流 UI 规格](docs/superpowers/specs/2026-05-28-revision-workflow-ui-spec.md)

## 许可证

内部项目，仅供组织内部使用。
