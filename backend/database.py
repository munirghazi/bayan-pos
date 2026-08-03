"""Database layer: PostgreSQL engine, tenant-aware connections, and models.

Multi-tenant isolation is enforced at TWO layers:
  1. Application: TenantMiddleware resolves the tenant from the JWT into a
     ContextVar; the engine 'checkout' listener pins every connection to that
     tenant via `SET app.current_tenant`.
  2. Database: PostgreSQL Row-Level Security policies (see the Alembic RLS
     migration) restrict every row to `tenant_id = current_setting(
     'app.current_tenant')`. The app connects as a non-superuser role so the
     policies actually apply.

`tenant_id` is filled automatically by a column DEFAULT that reads the same
session variable, so existing routers need no changes to stay tenant-safe.
"""
from datetime import datetime

from sqlalchemy import (
    create_engine, event, text,
    Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

from config import settings
from fastapi import Request

engine = create_engine(settings.database_url, pool_pre_ping=True, future=True,
                       connect_args={"client_encoding": "utf8"})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)
Base = declarative_base()

# SQL expression used both as the column DEFAULT and inside RLS policies.
_TENANT_GUC = "NULLIF(current_setting('app.current_tenant', true), '')::integer"




def _tenant_col(nullable=False):
    return Column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=nullable,
        index=True,
        server_default=text(_TENANT_GUC),
    )


# ===================== Tenancy =====================

class Tenant(Base):
    __tablename__ = "tenants"
    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String(50), unique=True, index=True, nullable=False)
    name = Column(String(200), nullable=False)
    cr_number = Column(String(30), nullable=True)
    vat_number = Column(String(20), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    settings = relationship("TenantSettings", back_populates="tenant", uselist=False,
                            cascade="all, delete-orphan")


class TenantSettings(Base):
    __tablename__ = "tenant_settings"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = _tenant_col()
    seller_name = Column(String(200), nullable=True)
    vat_number = Column(String(20), nullable=True)
    national_address = Column(String(300), nullable=True)
    vat_rate = Column(Float, default=15.0, nullable=False)
    inventory_mode = Column(String(20), default="per_branch", nullable=False)  # shared_pool | per_branch
    fatoora_enabled_default = Column(Boolean, default=False, nullable=False)
    payment_methods = Column(String(200), default="cash,card,transfer", nullable=False)

    tenant = relationship("Tenant", back_populates="settings")


# ===================== Existing models (now tenant-scoped) =====================

class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("tenant_id", "username", name="uq_user_tenant_username"),)

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = _tenant_col()
    username = Column(String(50), index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(100), nullable=False)
    role = Column(String(20), nullable=False, default="cashier")  # admin / manager / cashier
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=True)  # current branch
    is_active = Column(Boolean, default=True)
    must_change_password = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    sales = relationship("Sale", back_populates="user")
    donations = relationship("Donation", back_populates="user")


class Category(Base):
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = _tenant_col()
    name = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    products = relationship("Product", back_populates="category")


class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = _tenant_col()
    name = Column(String(200), nullable=False)
    price = Column(Float, nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    stock = Column(Integer, default=0)
    image_url = Column(String(500), nullable=True)
    is_active = Column(Boolean, default=True)
    is_tax_exempt = Column(Boolean, default=False)
    is_kit = Column(Boolean, default=False, nullable=False)  # composed of other products
    created_at = Column(DateTime, default=datetime.utcnow)

    category = relationship("Category", back_populates="products")
    sale_items = relationship("SaleItem", back_populates="product")


class Sale(Base):
    __tablename__ = "sales"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = _tenant_col()
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    register_id = Column(Integer, ForeignKey("registers.id"), nullable=True)  # where the sale happened
    total = Column(Float, nullable=False)
    payment_method = Column(String(20), nullable=False)
    card_ref = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="sales")
    items = relationship("SaleItem", back_populates="sale", cascade="all, delete-orphan")


class SaleItem(Base):
    __tablename__ = "sale_items"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = _tenant_col()
    sale_id = Column(Integer, ForeignKey("sales.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    price = Column(Float, nullable=False)
    is_tax_exempt = Column(Boolean, default=False)

    sale = relationship("Sale", back_populates="items")
    product = relationship("Product", back_populates="sale_items")


class Donation(Base):
    __tablename__ = "donations"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = _tenant_col()
    donor_name = Column(String(200), nullable=True)
    amount = Column(Float, nullable=False)
    note = Column(Text, nullable=True)
    payment_method = Column(String(20), nullable=False, default="cash")
    card_ref = Column(String(100), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="donations")


class KitComponent(Base):
    """One line of a kit's bill-of-materials: kit -> component x quantity.

    component_product_id may itself be a kit (nesting is allowed); cycles are
    rejected by the API. Stock is derived from leaf components, so a kit row in
    `products` keeps its own fixed price but its `stock` column is unused.
    """
    __tablename__ = "kit_components"
    __table_args__ = (
        UniqueConstraint("tenant_id", "kit_product_id", "component_product_id",
                         name="uq_kit_component"),
    )

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = _tenant_col()
    kit_product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"),
                            nullable=False, index=True)
    component_product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"),
                                  nullable=False, index=True)
    quantity = Column(Integer, nullable=False, default=1)


# Tables that carry tenant_id and must have RLS enabled.
TENANT_SCOPED_TABLES = [
    "tenant_settings", "users", "categories", "products",
    "sales", "sale_items", "donations", "kit_components",
    "locations", "registers",
]


class Location(Base):
    """A branch/site of a tenant."""
    __tablename__ = "locations"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = _tenant_col()
    name = Column(String(150), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    registers = relationship("Register", back_populates="location",
                             cascade="all, delete-orphan")


class Register(Base):
    """A point-of-sale register/till that belongs to a location."""
    __tablename__ = "registers"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = _tenant_col()
    location_id = Column(Integer, ForeignKey("locations.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    name = Column(String(150), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    location = relationship("Location", back_populates="registers")


def ensure_default_branch(db, tenant_id: int):
    """Create a default branch + register for a tenant if it has none.

    Idempotent. Assumes the caller may not have pinned the tenant, so it pins
    it here (RLS) before inserting.
    """
    db.execute(text("SELECT set_config('app.current_tenant', :t, false)"),
               {"t": str(int(tenant_id))})
    loc = db.query(Location).first()
    if loc is None:
        loc = Location(tenant_id=tenant_id, name="الفرع الرئيسي")
        db.add(loc)
        db.flush()
    if db.query(Register).filter(Register.location_id == loc.id).first() is None:
        db.add(Register(tenant_id=tenant_id, location_id=loc.id, name="الصندوق 1"))
    db.commit()


def get_db(request: Request):
    """Yield a session whose connection is pinned to the caller's tenant.

    The tenant is read from the request's JWT (cookie or Bearer). Setting the
    Postgres session variable here (not via middleware) avoids ContextVar/
    threadpool propagation issues and guarantees RLS is active for every query,
    including the DEFAULT that fills tenant_id on INSERT.
    """
    from tenancy import extract_token, decode_token
    tid = None
    sub = None
    token = extract_token(request)
    if token:
        payload = decode_token(token)
        if payload:
            tid = payload.get("tid")
            sub = payload.get("sub")
    db = SessionLocal()
    try:
        db.execute(text("SELECT set_config('app.current_tenant', :t, false)"),
                   {"t": "" if tid is None else str(int(tid))})
        request.state.tenant_id = int(tid) if tid is not None else None
        request.state.username = sub
        yield db
    finally:
        try:
            db.execute(text("SELECT set_config('app.current_tenant', '', false)"))
        except Exception:
            pass
        db.close()


def create_tables():
    Base.metadata.create_all(bind=engine)
