from typing import Any

from pydantic import BaseModel


class PublishRequestResponse(BaseModel):
    job_id: str


class ImportDocxResponse(BaseModel):
    job_id: str
    docx_key: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    result: dict[str, Any] | None = None
    error: str | None = None
