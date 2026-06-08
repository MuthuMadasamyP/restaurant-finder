import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from source.backend.database import SessionLocal
from backend.routes.admin import router as admin_router
from routes.auth import router as auth_router
from routes.export import router as export_router
from routes.feedback import router as feedback_router
from routes.search import router as search_router
from routes.speech import router as speech_router
from services.bootstrap import init_database, seed_defaults

if sys.platform.startswith("win") and hasattr(asyncio, "WindowsProactorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_database()
    with SessionLocal() as db:
        seed_defaults(db)
    logger.info("Restaurant Finder API starting up.")
    yield
    logger.info("Restaurant Finder API shut down.")


app = FastAPI(
    title="Restaurant Finder API",
    description="Searches Google Maps for restaurants and exports formatted Excel results.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(search_router, prefix="/api", tags=["Search"])
app.include_router(export_router, prefix="/api", tags=["Export"])
app.include_router(speech_router, prefix="/api", tags=["Speech"])
app.include_router(auth_router, prefix="/api", tags=["Authentication"])
app.include_router(feedback_router, prefix="/api", tags=["Feedback"])
app.include_router(admin_router, prefix="/api", tags=["Admin"])
app.mount("/static", StaticFiles(directory=FRONTEND_DIR / "static"), name="static")


@app.get("/", tags=["Info"])
async def root():
    response = FileResponse(FRONTEND_DIR / "auth.html")
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/login", tags=["Info"])
async def login_page():
    response = FileResponse(FRONTEND_DIR / "auth.html")
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/app", tags=["Info"])
async def app_page():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/admin", tags=["Admin"])
async def admin_portal():
    response = FileResponse(FRONTEND_DIR / "admin.html")
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/admin/{page_path:path}", tags=["Admin"])
async def admin_portal_page(page_path: str):
    response = FileResponse(FRONTEND_DIR / "admin.html")
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/api", tags=["Info"])
async def api_info():
    return {
        "message": "Welcome to Restaurant Finder API",
        "docs": "/docs",
        "redoc": "/redoc",
        "health": "/health",
    }


@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "ok", "service": "Restaurant Finder API"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
