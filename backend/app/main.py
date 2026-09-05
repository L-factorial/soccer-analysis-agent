import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import field_configurations_router, rag_ingestion_router, rag_query_router

app = FastAPI(title="Soccer Analysis Agent API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=(
        [
            origin.strip()
            for origin in os.environ["CORS_ALLOW_ORIGINS"].split(",")
            if origin.strip()
        ]
        if "CORS_ALLOW_ORIGINS" in os.environ
        else [
            "http://localhost:8081",
            "http://127.0.0.1:8081",
            "http://localhost:19006",
            "http://127.0.0.1:19006",
        ]
    ),
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(field_configurations_router, prefix="/api/v1")
app.include_router(rag_ingestion_router, prefix="/api/v1")
app.include_router(rag_query_router, prefix="/api/v1")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
