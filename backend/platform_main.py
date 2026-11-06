"""Release 2b — the platform console as its OWN process.

    uvicorn platform_main:app --host 127.0.0.1 --port 8001

Same code and database as the tenant app (main.py), but it mounts ONLY the
platform API and the console page. The tenant app never mounts the platform
router, so /api/platform/* does not exist on the tenant domain at all.

Served on admin.<domain> by Caddy. Runs as the same non-superuser DB role, so
RLS still applies: tenant rows are read one tenant at a time.
"""
import logging
import os

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from config import settings
from database import engine
from routers import platform

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')

app = FastAPI(title="SahlPOS platform console", version="2b",
              docs_url=None if settings.is_production else "/docs",
              redoc_url=None, openapi_url=None if settings.is_production else "/openapi.json")


CSP = ("default-src 'self'; script-src 'self'; "
       "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; "
       "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")


@app.middleware("http")
async def _security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    if request.url.path.startswith("/api"):
        response.headers["Cache-Control"] = "no-store"
    response.headers.setdefault("X-Robots-Tag", "noindex, nofollow")
    response.headers.setdefault("Content-Security-Policy", CSP)
    return response


@app.get("/health")
def health():
    db_ok = True
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        db_ok = False
    return {"status": "ok" if db_ok else "degraded", "service": "platform",
            "database": "up" if db_ok else "down"}


app.include_router(platform.router, prefix="/api/platform", tags=["platform"])

# --- console page (frontend/dist/platform.html + shared /assets) ---
FRONTEND_BUILD = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
_assets = os.path.join(FRONTEND_BUILD, "assets")
if os.path.isdir(_assets):
    app.mount("/assets", StaticFiles(directory=_assets), name="assets")


@app.exception_handler(StarletteHTTPException)
async def _fallback(request: Request, exc: StarletteHTTPException):
    page = os.path.join(FRONTEND_BUILD, "platform.html")
    if (exc.status_code == 404 and request.method == "GET"
            and not request.url.path.startswith("/api") and os.path.isfile(page)):
        return FileResponse(page, headers={"Cache-Control": "no-cache"})
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code,
                        headers=getattr(exc, "headers", None))
