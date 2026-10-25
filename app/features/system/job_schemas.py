from datetime import date, datetime

from pydantic import BaseModel, Field


class JobAdmissionResponse(BaseModel):
    job_id: str
    message: str
    status: str | None = None
    status_url: str | None = None


class JobRetryResponse(BaseModel):
    job_id: str
    status: str


class JobFailureResponse(BaseModel):
    user_id: int
    date: date


class JobPartResponse(BaseModel):
    kind: str
    status: str
    attempts: int
    filename: str | None
    detail: str | None


class JobDetailResponse(BaseModel):
    id: int
    kind: str
    status: str
    attempts: int
    created_at: datetime
    updated_at: datetime
    finished_at: datetime | None
    progress: dict[str, int | str]
    failures: list[JobFailureResponse]
    parts: list[JobPartResponse]


class ReadinessResponse(BaseModel):
    status: str
    database: str
    schema_status: str = Field(alias='schema')


class JobCountResponse(BaseModel):
    kind: str
    status: str
    count: int


class RoutineExecutionResponse(BaseModel):
    status: str
    execution_time: datetime
    target_date: date | None
    details: str | None


class RecentJobResponse(BaseModel):
    id: int
    kind: str
    routine_type: str | None
    status: str
    created_at: datetime
    progress: dict[str, int | str]


class OperationsResponse(ReadinessResponse):
    version: str
    environment: str
    timezone: str
    jobs: list[JobCountResponse]
    oldest_pending_at: datetime | None
    routines: dict[str, RoutineExecutionResponse]
    recent_jobs: list[RecentJobResponse]
