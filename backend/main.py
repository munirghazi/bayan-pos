from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from database import create_tables
from routers import auth, products, sales, donations, reports, settings
import os

app = FastAPI(title="نظام نقاط البيع - جمعية بيان", version="1.0.0")

# CORS - allow both dev and production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files for product images
os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# Routers
app.include_router(auth.router, prefix="/api/auth", tags=["المصادقة"])
app.include_router(products.router, prefix="/api/products", tags=["المنتجات"])
app.include_router(sales.router, prefix="/api/sales", tags=["المبيعات"])
app.include_router(donations.router, prefix="/api/donations", tags=["التبرعات"])
app.include_router(reports.router, prefix="/api/reports", tags=["التقارير"])
app.include_router(settings.router, prefix="/api/settings", tags=["الإعدادات"])

# --- Serve frontend build in production ---
FRONTEND_BUILD = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")

if os.path.isdir(FRONTEND_BUILD):
    # Serve static assets (JS, CSS, images, etc.)
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_BUILD, "assets")), name="frontend-assets")

    # Serve files from the build root (favicon, manifest, etc.)
    @app.get("/saudi-riyal-symbol.svg")
    async def sar_symbol():
        return FileResponse(os.path.join(FRONTEND_BUILD, "saudi-riyal-symbol.svg"))

    @app.get("/vite.svg")
    async def vite_svg():
        return FileResponse(os.path.join(FRONTEND_BUILD, "vite.svg"))

    # Catch-all: serve index.html for any non-API route (SPA support)
    @app.get("/{full_path:path}")
    async def serve_frontend(request: Request, full_path: str):
        # Don't intercept API or upload routes
        if full_path.startswith("api/") or full_path.startswith("uploads/"):
            return
        # Check if requesting a static file that exists
        file_path = os.path.join(FRONTEND_BUILD, full_path)
        if full_path and os.path.isfile(file_path):
            return FileResponse(file_path)
        # Otherwise serve index.html (SPA routing)
        return FileResponse(os.path.join(FRONTEND_BUILD, "index.html"))


@app.on_event("startup")
def startup():
    create_tables()

    # --- Database migration: add new columns if missing ---
    from database import engine
    import sqlite3
    conn = sqlite3.connect(engine.url.database)
    cursor = conn.cursor()

    # Add is_tax_exempt to products table
    try:
        cursor.execute("ALTER TABLE products ADD COLUMN is_tax_exempt BOOLEAN DEFAULT 0")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Add is_tax_exempt to sale_items table
    try:
        cursor.execute("ALTER TABLE sale_items ADD COLUMN is_tax_exempt BOOLEAN DEFAULT 0")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # Add card_ref to sales table
    try:
        cursor.execute("ALTER TABLE sales ADD COLUMN card_ref VARCHAR(100)")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # Add card_ref to donations table
    try:
        cursor.execute("ALTER TABLE donations ADD COLUMN card_ref VARCHAR(100)")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    conn.close()

    # Seed default admin user
    from database import SessionLocal, User
    from passlib.context import CryptContext
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.username == "admin").first()
        if not admin:
            pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
            admin_user = User(
                username="admin",
                password_hash=pwd_context.hash("admin123"),
                full_name="مدير النظام",
                role="admin",
            )
            db.add(admin_user)

            cashier_user = User(
                username="cashier",
                password_hash=pwd_context.hash("cashier123"),
                full_name="كاشير",
                role="cashier",
            )
            db.add(cashier_user)
            db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
