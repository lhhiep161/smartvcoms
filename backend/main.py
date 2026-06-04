from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import text

from backend.core.database import PortalBase, portal_engine
from backend.modules.auth.router import router as auth_router
from backend.modules.permissions.router import router as permissions_router
from backend.modules.portal_admin.router import router as portal_admin_router
from backend.modules.smartvcoms.router import router as vcoms_router

FRONTEND_DIST_DIR = Path(__file__).resolve().parents[1] / "frontend" / "dist"
FRONTEND_INDEX_FILE = FRONTEND_DIST_DIR / "index.html"

app = FastAPI(
    title="SmartVCOMS Package API",
    description="Backend API cho package SmartVCOMS nội bộ",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(permissions_router)
app.include_router(portal_admin_router)
app.include_router(vcoms_router)


@app.on_event("startup")
def startup_db_migrations() -> None:
    PortalBase.metadata.create_all(bind=portal_engine)


@app.get("/api/health")
def health_check() -> dict[str, object]:
    try:
        with portal_engine.begin() as portal_conn:
            portal_result = portal_conn.execute(text("SELECT 1")).fetchone()
        return {
            "status": "success",
            "portal_database": "connected",
            "portal_test_query_result": portal_result[0],
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


def _frontend_ready() -> bool:
    return FRONTEND_INDEX_FILE.exists()


def _safe_frontend_file(full_path: str) -> Path | None:
    if not full_path or full_path.startswith("api/"):
        return None
    candidate = (FRONTEND_DIST_DIR / full_path).resolve()
    if not FRONTEND_DIST_DIR.exists():
        return None
    try:
        candidate.relative_to(FRONTEND_DIST_DIR.resolve())
    except Exception:
        return None
    if candidate.is_file():
        return candidate
    return None


@app.get("/", include_in_schema=False)
def serve_frontend_root():
    if _frontend_ready():
        return FileResponse(FRONTEND_INDEX_FILE)
    return {"message": "SmartVCOMS package backend is running.", "frontend_dist_ready": False}


@app.get("/{full_path:path}", include_in_schema=False)
def serve_frontend_app(full_path: str):
    asset_file = _safe_frontend_file(full_path)
    if asset_file is not None:
        return FileResponse(asset_file)
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="API route not found.")
    if _frontend_ready():
        return FileResponse(FRONTEND_INDEX_FILE)
    raise HTTPException(status_code=404, detail="Frontend dist not found.")
