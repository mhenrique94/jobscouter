from __future__ import annotations

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from jobscouter.api.routes.jobs import router as jobs_router


app = FastAPI(title="JobScouter API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(jobs_router, prefix="/api/v1")


if __name__ == "__main__":
    uvicorn.run("jobscouter.api.main:app", host="0.0.0.0", port=8000)
