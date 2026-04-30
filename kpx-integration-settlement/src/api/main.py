import os
from fastapi import FastAPI
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
