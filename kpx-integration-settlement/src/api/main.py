import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI

# config/.env 우선 로드 (LANGCHAIN_*, OPENAI_API_KEY, DB_* 등)
load_dotenv(Path(__file__).parents[2] / "config" / ".env")
from fastapi.middleware.cors import CORSMiddleware
from src.api.routers import auth, dashboard, usage, settings, cashback, insights

app = FastAPI(title="ax_nilm Local API Server", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://localhost:4173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(dashboard.router, prefix="/api")
app.include_router(usage.router, prefix="/api")
app.include_router(settings.router, prefix="/api")
app.include_router(cashback.router, prefix="/api")
app.include_router(insights.router, prefix="/api")


@app.get("/health")
def health():
    hh = os.getenv("DEFAULT_HH", "HH001")
    return {"status": "ok", "default_hh": hh}
