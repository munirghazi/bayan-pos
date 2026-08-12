import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from passlib.context import CryptContext
from sqlalchemy import text

from config import settings
from database import SessionLocal, Tenant, TenantSettings, User, ensure_default_branch, ensure_default_uom
from routers import auth, products, sales, donations, reports, locations, customers, returns, delivery, suppliers, uom, stock, purchase_orders, goods_receipts, settings as settings_router


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

        ensure_default_branch(db, tenant.id)
        ensure_default_uom(db, tenant.id)
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
app.include_router(locations.router, prefix="/api/locations", tags=["الفروع"])
app.include_router(locations.registers_router, prefix="/api/registers", tags=["الصناديق"])
app.include_router(customers.router, prefix="/api/customers", tags=["العملاء"])
app.include_router(returns.router, prefix="/api/returns", tags=["المرتجعات"])
app.include_router(delivery.router, prefix="/api/delivery", tags=["الإرسال"])
app.include_router(suppliers.router, prefix="/api/suppliers", tags=["الموردون"])
app.include_router(uom.router, prefix="/api/uom", tags=["وحدات القياس"])
app.include_router(stock.router, prefix="/api/stock", tags=["المخزون"])
app.include_router(purchase_orders.router, prefix="/api/purchase-orders", tags=["أوامر الشراء"])
app.include_router(goods_receipts.router, prefix="/api/goods-receipts", tags=["سندات الاستلام"])
app.include_router(settings_router.router, prefix="/api/settings", tags=["الإعدادات"])

# --- Serve frontend build in production ---
FRONTEND_BUILD = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(FRONTEND_BUILD):
    _assets = os.path.join(FRONTEND_BUILD, "assets")
    if os.path.isdir(_assets):
        app.mount("/assets", StaticFiles(directory=_assets), name="frontend-assets")

    # Serve the SPA via a 404 fallback instead of a greedy catch-all route.
    # A catch-all `/{path}` route would shadow the API (e.g. POST /api/products
    # -> 405) and break trailing-slash redirects; a 404 handler leaves every real
    # API route intact and only steps in for unknown GET paths (client routes).
    @app.exception_handler(StarletteHTTPException)
    async def spa_fallback(request: Request, exc: StarletteHTTPException):
        path = request.url.path
        if (exc.status_code == 404 and request.method == "GET"
                and not path.startswith("/api") and not path.startswith("/uploads")):
            candidate = os.path.join(FRONTEND_BUILD, path.lstrip("/"))
            if path not in ("", "/") and os.path.isfile(candidate):
                return FileResponse(candidate)
            index = os.path.join(FRONTEND_BUILD, "index.html")
            if os.path.isfile(index):
                return FileResponse(index)
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code,
                            headers=getattr(exc, "headers", None))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
