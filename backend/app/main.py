from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .database import init_db
from .routers import health, imports, companies, persons, api
from .config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create tables
    await init_db()
    yield
    # Shutdown: nothing needed


app = FastAPI(
    title="CompanyDB",
    description="NorthData Import and Search API",
    version="0.1.0",
    lifespan=lifespan
)

# CORS for frontend - configured via CORS_ORIGINS environment variable
cors_origins = [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(health.router)
app.include_router(imports.router)
app.include_router(companies.router)
app.include_router(persons.router)
app.include_router(api.router)


@app.get("/")
async def root():
    return {"message": "CompanyDB API", "docs": "/docs"}
