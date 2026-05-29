from arq.connections import RedisSettings

from apps.api.config import get_settings
from apps.worker.tasks.convert import export_pdf_task

_settings = get_settings()


class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(_settings.redis_url)
    functions = [export_pdf_task]
