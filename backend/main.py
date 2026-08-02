import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from passlib.context import CryptContext
from sqlalchemy import text

from config import settings
from database import SessionLocal, Tenant, TenantSettings, User
from routers import auth, products, sales, donations, reports, settings as settings_router


def bootstrap():
    """Create the first tenant (and optional admin) on first run."""
    pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.slug == settings.bootstrap_tenant_slug).first()
        if not tenant:
            tenant = Tenant(slug=settings.bootstrap_tenant_slug,
                            name=settings.bootstrap_tenant_name)
            db.add(tenant)
            db.commit()
            db.refresh(tenant)

        # Pin this connection to the tenant so RLS lets us seed its rows.
        db.execute(text("SELECT set_config('app.current_tenant', :t, false)"),
                   {"t": str(tenant.id)})

        if not db.query(TenantSettings).filter(TenantSettings.tenant_id == tenant.id).first():
            db.add(TenantSettings(tenant_id=tenant.id, seller_name=tenant.name))
            db.commit()

        if settings.bootstrap_admin_password:
            admin = db.query(User).filter(User.username == settings.bootstrap_admin_username).first()
            if not admin:
                db.add(User(
                    tenant_id=tenant.id,
                    username=settings.bootstrap_admin_username,
                    password_hash=pwd.hash(settings.bootstrap_admin_password),
                    full_name="مدير النظام",
                    role="admin",
                    must_change_password=True,
                ))
                db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    bootstrap()
    yield


app = FastAPI(title="نظام نقاط البيع - متعدد الجهات", version="2.0.0", lifespan=lifespan)

# CORS: explicit allow-list, never "*".
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")


@app.get("/health")
def health():
    return {"status": "ok", "environment": settings.environment}


app.include_router(auth.router, prefix="/api/auth", tags=["المصادقة"])
app.include_router(products.router, prefix="/api/products", tags=["المنتجات"])
app.include_router(sales.router, prefix="/api/sales", tags=["المبيعات"])
app.include_router(donations.router, prefix="/api/donations", tags=["التبرعات"])
app.include_router(reports.router, prefix="/api/reports", tags=["التقارير"])
app.include_router(settings_router.router, prefix="/api/settings", tags=["الإعدادات"])

# --- Serve frontend build in production ---
FRONTEND_BUILD = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(FRONTEND_BUILD):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_BUILD, "assets")),
              name="frontend-assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(request: Request, full_path: str):
        if full_path.startswith("api/") or full_path.startswith("uploads/"):
            return
        file_path = os.path.join(FRONTEND_BUILD, full_path)
        if full_path and os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(FRONTEND_BUILD, "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
