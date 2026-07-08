"""In-memory job registry for slice 2.

``Job`` holds mutable status / progress / results. ``JobStore`` is a thin
``dict[job_id, Job]`` wrapper. No persistence — jobs vanish on restart
(slice 3 replaces this with ``pkg-job-orch`` + SQLite).

Concurrency: a job is mutated by at most one background task and read by
``GET /api/translate/{job_id}`` polling. Both run on the same asyncio event
loop, so attribute writes are atomic from the loop's perspective — no lock
needed.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Literal

__all__ = ["Job", "JobStatus", "JobStore"]

JobStatus = Literal["pending", "processing", "done", "failed"]


@dataclass
class Job:
    job_id: str
    status: JobStatus = "pending"
    progress: float = 0.0
    results: list[dict[str, str]] | None = None
    error: str | None = None


@dataclass
class JobStore:
    """Process-local registry of translation jobs."""

    _jobs: dict[str, Job] = field(default_factory=dict[str, Job])

    def create(self) -> Job:
        job = Job(job_id=uuid.uuid4().hex)
        self._jobs[job.job_id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def all(self) -> list[Job]:
        return list(self._jobs.values())
