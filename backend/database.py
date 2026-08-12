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
    Column, Integer, String, Float, Numeric, Boolean, DateTime, Date, ForeignKey, Text,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

from config import settings
from fastapi import Request

engine = create_engine(settings.database_url, pool_pre_ping=True, future=True,
                       connect_args={"client_encoding": "utf8"})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)
Base = declarative_base()

# Quantities/stock: exact NUMERIC(14,3) storage, float in Python (fractional units).
_QTY = Numeric(14, 3, asdecimal=False)

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
    city = Column(String(100), nullable=True)
    country = Column(String(100), nullable=True)
    website = Column(String(200), nullable=True)
    logo_url = Column(String(500), nullable=True)
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
    stock = Column(_QTY, default=0)
    barcode = Column(String(64), nullable=True, index=True)
    cost_price = Column(Float, default=0, nullable=False)      # for margin/COGS
    unit = Column(String(30), nullable=True)                   # e.g. حبة، كرتون، كجم
    reorder_level = Column(_QTY, default=0, nullable=False)
    default_supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True)
    uom_id = Column(Integer, ForeignKey("uoms.id"), nullable=True)            # base/stock unit
    purchase_uom_id = Column(Integer, ForeignKey("uoms.id"), nullable=True)   # default buying unit
    sales_uom_id = Column(Integer, ForeignKey("uoms.id"), nullable=True)      # default selling unit
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
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)  # optional buyer
    total = Column(Float, nullable=False)
    payment_method = Column(String(20), nullable=False)
    card_ref = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="sales")
    items = relationship("SaleItem", back_populates="sale", cascade="all, delete-orphan")
    customer = relationship("Customer")


class SaleItem(Base):
    __tablename__ = "sale_items"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = _tenant_col()
    sale_id = Column(Integer, ForeignKey("sales.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity = Column(_QTY, nullable=False)
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
    quantity = Column(_QTY, nullable=False, default=1)


# Tables that carry tenant_id and must have RLS enabled.
TENANT_SCOPED_TABLES = [
    "tenant_settings", "users", "categories", "products",
    "sales", "sale_items", "donations", "kit_components",
    "locations", "registers", "customers", "returns", "return_items",
    "suppliers", "supplier_documents", "uom_categories", "uoms",
    "stock_movements",
]


class StockMovement(Base):
    """Append-only stock ledger. `qty` is the signed change (in +, out -),
    `balance_after` is the product's base-unit stock right after the movement."""
    __tablename__ = "stock_movements"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = _tenant_col()
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    type = Column(String(20), nullable=False)              # in | out | adjust
    qty = Column(Numeric(14, 3, asdecimal=False), nullable=False)
    balance_after = Column(Numeric(14, 3, asdecimal=False), nullable=False)
    unit_cost = Column(Numeric(14, 3, asdecimal=False), nullable=True)
    ref_type = Column(String(30), nullable=True)           # sale | return | manual | adjustment
    ref_id = Column(Integer, nullable=True)
    note = Column(String(300), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class UomCategory(Base):
    """A unit-of-measure category (e.g. عدد/Unit, وزن/Weight, حجم/Volume).
    Conversions are only valid WITHIN a category."""
    __tablename__ = "uom_categories"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = _tenant_col()
    name = Column(String(100), nullable=False)
    decimal_places = Column(Integer, nullable=False, default=3)  # display/rounding precision
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    uoms = relationship("Uom", back_populates="category", cascade="all, delete-orphan")


class Uom(Base):
    """A unit within a category. `factor` = how many REFERENCE units make up one
    of this unit (reference unit has factor 1). e.g. Weight ref=kg: g=0.001, ton=1000."""
    __tablename__ = "uoms"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = _tenant_col()
    category_id = Column(Integer, ForeignKey("uom_categories.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    name = Column(String(100), nullable=False)
    factor = Column(Numeric(18, 6, asdecimal=False), nullable=False, default=1)
    is_reference = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    category = relationship("UomCategory", back_populates="uoms")


# (category_name, decimal_places, [(unit_name, factor, is_reference), ...])
DEFAULT_UOM_SEED = [
    ("عدد", 0, [("حبة", 1, True), ("دستة", 12, False), ("كرتون", 24, False)]),
    ("وزن", 3, [("كجم", 1, True), ("جرام", 0.001, False), ("طن", 1000, False)]),
    ("حجم", 3, [("لتر", 1, True), ("مل", 0.001, False)]),
]


def ensure_default_uom(db, tenant_id: int):
    """Seed default UoM categories + units for a tenant if it has none. Idempotent."""
    db.execute(text("SELECT set_config('app.current_tenant', :t, false)"),
               {"t": str(int(tenant_id))})
    if db.query(UomCategory).first() is not None:
        return
    for cat_name, dp, units in DEFAULT_UOM_SEED:
        cat = UomCategory(tenant_id=tenant_id, name=cat_name, decimal_places=dp)
        db.add(cat)
        db.flush()
        for uname, factor, is_ref in units:
            db.add(Uom(tenant_id=tenant_id, category_id=cat.id, name=uname,
                       factor=factor, is_reference=is_ref))
    db.commit()


class Supplier(Base):
    """A vendor. Cannot be issued a purchase order unless compliant (see
    supplier_documents): CR + VAT + National Address, each verified and unexpired.
    """
    __tablename__ = "suppliers"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = _tenant_col()
    name = Column(String(200), nullable=False)
    iban = Column(String(34), nullable=True)
    payment_terms = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    documents = relationship("SupplierDocument", back_populates="supplier",
                             cascade="all, delete-orphan")


class SupplierDocument(Base):
    """One compliance document per (supplier, doc_type): cr | vat | national_address."""
    __tablename__ = "supplier_documents"
    __table_args__ = (UniqueConstraint("supplier_id", "doc_type",
                                        name="uq_supplier_doc_type"),)
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = _tenant_col()
    supplier_id = Column(Integer, ForeignKey("suppliers.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    doc_type = Column(String(30), nullable=False)     # cr | vat | national_address
    number = Column(String(100), nullable=True)
    issue_date = Column(Date, nullable=True)
    expiry_date = Column(Date, nullable=True)
    file_url = Column(String(500), nullable=True)
    is_verified = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    supplier = relationship("Supplier", back_populates="documents")


class Return(Base):
    """A return / credit note against an existing sale (full or partial)."""
    __tablename__ = "returns"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = _tenant_col()
    sale_id = Column(Integer, ForeignKey("sales.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    register_id = Column(Integer, ForeignKey("registers.id"), nullable=True)
    credit_note_number = Column(Integer, nullable=False)   # per-tenant sequential
    total = Column(Float, nullable=False)                  # amount refunded
    reason = Column(String(300), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    items = relationship("ReturnItem", back_populates="return_ref",
                         cascade="all, delete-orphan")
    sale = relationship("Sale")


class ReturnItem(Base):
    __tablename__ = "return_items"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = _tenant_col()
    return_id = Column(Integer, ForeignKey("returns.id", ondelete="CASCADE"),
                       nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity = Column(_QTY, nullable=False)
    price = Column(Float, nullable=False)                   # unit price at sale time

    return_ref = relationship("Return", back_populates="items")
    product = relationship("Product")


class Customer(Base):
    """A buyer, captured at the POS. Optional on a sale (walk-ins have none).

    vat_number + address support ZATCA standard (B2B) invoices later; simplified
    (B2C) receipts need only a name/phone.
    """
    __tablename__ = "customers"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = _tenant_col()
    name = Column(String(200), nullable=False)
    phone = Column(String(30), nullable=True, index=True)
    email = Column(String(200), nullable=True)
    vat_number = Column(String(20), nullable=True)
    address = Column(String(300), nullable=True)
    city = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


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
    """Yield a session bound to ONE dedicated connection, pinned to the caller's
    tenant for the whole request.

    Pinning a single connection (rather than 'a session') is essential: after a
    commit, SQLAlchemy may otherwise use a different pooled connection for a
    refresh/lazy-load — one where app.current_tenant isn't set — and RLS would
    hide the just-written row (InvalidRequestError: Could not refresh instance).
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

    connection = engine.connect()
    connection.execute(text("SELECT set_config('app.current_tenant', :t, false)"),
                       {"t": "" if tid is None else str(int(tid))})
    connection.commit()

    db = SessionLocal(bind=connection)
    request.state.tenant_id = int(tid) if tid is not None else None
    request.state.username = sub
    try:
        yield db
    finally:
        db.close()
        try:
            connection.execute(text("SELECT set_config('app.current_tenant', '', false)"))
            connection.commit()
        except Exception:
            pass
        connection.close()


def create_tables():
    Base.metadata.create_all(bind=engine)
