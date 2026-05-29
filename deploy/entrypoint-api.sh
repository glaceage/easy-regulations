#!/bin/sh
set -e
alembic upgrade head
exec uvicorn apps.api.main:create_app --factory --host 0.0.0.0 --port 8000
