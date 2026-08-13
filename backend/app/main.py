from fastapi import FastAPI

app = FastAPI(title="Soccer Analysis Agent API")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

