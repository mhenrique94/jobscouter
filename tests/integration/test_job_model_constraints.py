from __future__ import annotations

from jobscouter.db.models import Job


def test_job_model_has_expected_table_name() -> None:
    assert Job.__tablename__ == "jobs"
