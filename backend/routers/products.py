from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from pydantic import BaseModel
from database import get_db, Product, Category, KitComponent, Uom
from routers.auth import get_current_user, require_admin, User
from perms import require_perm
from kits import available_quantity, reachable, components_of
import os
import shutil
import uuid

router = APIRouter()


# ===================== Schemas =====================

class CategoryCreate(BaseModel):
    name: str


class CategoryResponse(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True


class KitComponentIn(BaseModel):
    product_id: int
    quantity: float = 1


class KitComponentOut(BaseModel):
    product_id: int
    product_name: str | None = None
    quantity: float


class ProductResponse(BaseModel):
    id: int
    name: str
    price: float
    category_id: int | None
    category: CategoryResponse | None
    stock: float
    barcode: str | None = None
    cost_price: float = 0
    unit: str | None = None
    reorder_level: float = 0
    default_supplier_id: int | None = None
    uom_id: int | None = None
    purchase_uom_id: int | None = None
    sales_uom_id: int | None = None
    uom_name: str | None = None
    image_url: str | None
    is_active: bool
    is_tax_exempt: bool = False
    is_kit: bool = False
    available_stock: float = 0
    is_low_stock: bool = False
    components: list[KitComponentOut] = []

    class Config:
        from_attributes = True


class ProductCreate(BaseModel):
    name: str
    price: float
    category_id: int | None = None
    stock: float = 0
    barcode: str | None = None
    cost_price: float = 0
    unit: str | None = None
    reorder_level: float = 0
    default_supplier_id: int | None = None
    uom_id: int | None = None
    purchase_uom_id: int | None = None
    sales_uom_id: int | None = None
    image_url: str | None = None
    is_tax_exempt: bool = False
    is_kit: bool = False
    components: list[KitComponentIn] | None = None


class ProductUpdate(BaseModel):
    name: str | None = None
    price: float | None = None
    category_id: int | None = None
    stock: float | None = None
    barcode: str | None = None
    cost_price: float | None = None
    unit: str | None = None
    reorder_level: float | None = None
    default_supplier_id: int | None = None
    uom_id: int | None = None
    purchase_uom_id: int | None = None
    sales_uom_id: int | None = None
    image_url: str | None = None
    is_active: bool | None = None
    is_tax_exempt: bool | None = None
    is_kit: bool | None = None
    components: list[KitComponentIn] | None = None


# ===================== Kit helpers =====================

def _apply_kit_components(db: Session, product: Product, components: list[KitComponentIn]):
    """Replace a kit's components after validation (existence, self, cycles)."""
    db.query(KitComponent).filter(KitComponent.kit_product_id == product.id).delete()
    db.flush()

    merged: dict[int, int] = {}
    for c in components:
        merged[c.product_id] = merged.get(c.product_id, 0) + c.quantity

    for cid, qty in merged.items():
        if qty <= 0:
            raise HTTPException(status_code=400, detail="كمية المكوّن يجب أن تكون أكبر من صفر")
        if cid == product.id:
            raise HTTPException(status_code=400, detail="لا يمكن أن يحتوي المنتج على نفسه")
        comp = db.query(Product).filter(Product.id == cid).first()
        if comp is None:
            raise HTTPException(status_code=400, detail=f"المكوّن رقم {cid} غير موجود")
        if reachable(db, cid, product.id):
            raise HTTPException(status_code=400,
                                detail=f"إضافة '{comp.name}' تُنشئ حلقة مكوّنات (kit دائري)")
        db.add(KitComponent(kit_product_id=product.id, component_product_id=cid, quantity=qty))
    db.flush()


def _uom_name(db, uom_id):
    if not uom_id:
        return None
    u = db.query(Uom).filter(Uom.id == uom_id).first()
    return u.name if u else None


def _validate_uoms(db, uom_id, purchase_uom_id, sales_uom_id):
    """Purchase/sales units must belong to the same category as the base unit."""
    if uom_id is None:
        if purchase_uom_id or sales_uom_id:
            raise HTTPException(status_code=400, detail="حدد وحدة القياس الأساسية أولاً")
        return
    base = db.query(Uom).filter(Uom.id == uom_id).first()
    if not base:
        raise HTTPException(status_code=400, detail="وحدة القياس الأساسية غير موجودة")
    for other_id, label in ((purchase_uom_id, "وحدة الشراء"), (sales_uom_id, "وحدة البيع")):
        if other_id:
            o = db.query(Uom).filter(Uom.id == other_id).first()
            if not o:
                raise HTTPException(status_code=400, detail=f"{label} غير موجودة")
            if o.category_id != base.category_id:
                raise HTTPException(status_code=400,
                                    detail=f"{label} يجب أن تكون من نفس فئة الوحدة الأساسية")


class EnsureBarcodes(BaseModel):
    product_ids: list[int]


@router.post("/ensure-barcodes")
def ensure_barcodes(req: EnsureBarcodes, db: Session = Depends(get_db),
                    current_user: User = Depends(require_perm("products"))):
    """Ensure each product has a barcode (generate + save PR######## when empty).
    Returns id/name/barcode/price for label printing."""
    out = []
    for pid in req.product_ids:
        prod = db.query(Product).filter(Product.id == pid).first()
        if not prod:
            continue
        if not prod.barcode:
            prod.barcode = f"PR{prod.id:08d}"
        out.append({"id": prod.id, "name": prod.name, "barcode": prod.barcode, "price": prod.price})
    db.commit()
    return out


def _serialize(db: Session, product: Product) -> dict:
    comps = []
    if product.is_kit:
        for row in components_of(db, product.id):
            cp = db.query(Product).filter(Product.id == row.component_product_id).first()
            comps.append({"product_id": row.component_product_id,
                          "product_name": cp.name if cp else None,
                          "quantity": row.quantity})
    cat = product.category
    avail = available_quantity(db, product)
    reorder = product.reorder_level or 0
    return {
        "id": product.id,
        "name": product.name,
        "price": product.price,
        "category_id": product.category_id,
        "category": {"id": cat.id, "name": cat.name} if cat else None,
        "stock": product.stock or 0,
        "barcode": product.barcode,
        "cost_price": product.cost_price or 0,
        "unit": product.unit,
        "reorder_level": reorder,
        "default_supplier_id": product.default_supplier_id,
        "uom_id": product.uom_id,
        "purchase_uom_id": product.purchase_uom_id,
        "sales_uom_id": product.sales_uom_id,
        "uom_name": _uom_name(db, product.uom_id),
        "image_url": product.image_url,
        "is_active": product.is_active,
        "is_tax_exempt": product.is_tax_exempt,
        "is_kit": product.is_kit,
        "available_stock": avail,
        "is_low_stock": bool(reorder > 0 and avail <= reorder),
        "components": comps,
    }


# ===================== Categories =====================

@router.get("/categories", response_model=list[CategoryResponse])
def get_categories(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return db.query(Category).all()


@router.post("/categories", response_model=CategoryResponse)
def create_category(request: CategoryCreate, db: Session = Depends(get_db), current_user: User = Depends(require_perm("products"))):
    category = Category(name=request.name)
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


@router.put("/categories/{category_id}", response_model=CategoryResponse)
def update_category(category_id: int, request: CategoryCreate, db: Session = Depends(get_db), current_user: User = Depends(require_perm("products"))):
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="التصنيف غير موجود")
    category.name = request.name
    db.commit()
    db.refresh(category)
    return category


@router.delete("/categories/{category_id}")
def delete_category(category_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_perm("products"))):
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="التصنيف غير موجود")
    db.delete(category)
    db.commit()
    return {"message": "تم حذف التصنيف بنجاح"}


# ===================== Products =====================

@router.get("/", response_model=list[ProductResponse])
def get_products(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return [_serialize(db, p) for p in db.query(Product).filter(Product.is_active == True, Product.is_consignment == False).all()]


@router.get("/all", response_model=list[ProductResponse])
def get_all_products(include_inactive: bool = False, db: Session = Depends(get_db),
                     current_user: User = Depends(require_perm("products"))):
    q = db.query(Product).filter(Product.is_consignment == False)
    if not include_inactive:
        q = q.filter(Product.is_active == True)  # noqa: E712
    return [_serialize(db, p) for p in q.all()]


@router.get("/{product_id}", response_model=ProductResponse)
def get_product(product_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="المنتج غير موجود")
    return _serialize(db, product)


@router.post("/", response_model=ProductResponse)
def create_product(request: ProductCreate, db: Session = Depends(get_db), current_user: User = Depends(require_perm("products"))):
    if request.is_kit and not request.components:
        raise HTTPException(status_code=400, detail="المنتج المُجمّع (kit) يجب أن يحتوي على مكوّن واحد على الأقل")

    _validate_uoms(db, request.uom_id, request.purchase_uom_id, request.sales_uom_id)

    product = Product(
        name=request.name,
        price=request.price,
        category_id=request.category_id,
        stock=0 if request.is_kit else request.stock,
        barcode=request.barcode,
        cost_price=request.cost_price or 0,
        unit=request.unit,
        reorder_level=request.reorder_level or 0,
        default_supplier_id=request.default_supplier_id,
        uom_id=request.uom_id,
        purchase_uom_id=request.purchase_uom_id,
        sales_uom_id=request.sales_uom_id,
        image_url=request.image_url,
        is_tax_exempt=request.is_tax_exempt,
        is_kit=request.is_kit,
    )
    db.add(product)
    db.flush()

    if request.is_kit:
        _apply_kit_components(db, product, request.components)

    db.commit()
    db.refresh(product)
    return _serialize(db, product)


@router.put("/{product_id}", response_model=ProductResponse)
def update_product(product_id: int, request: ProductUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_perm("products"))):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="المنتج غير موجود")

    if request.name is not None:
        product.name = request.name
    if request.price is not None:
        product.price = request.price
    if request.category_id is not None:
        product.category_id = request.category_id
    if request.barcode is not None:
        product.barcode = request.barcode
    if request.cost_price is not None:
        product.cost_price = request.cost_price
    if request.unit is not None:
        product.unit = request.unit
    if request.reorder_level is not None:
        product.reorder_level = request.reorder_level
    if request.default_supplier_id is not None:
        product.default_supplier_id = request.default_supplier_id
    if request.uom_id is not None:
        product.uom_id = request.uom_id
    if request.purchase_uom_id is not None:
        product.purchase_uom_id = request.purchase_uom_id
    if request.sales_uom_id is not None:
        product.sales_uom_id = request.sales_uom_id
    _validate_uoms(db, product.uom_id, product.purchase_uom_id, product.sales_uom_id)
    if request.image_url is not None:
        product.image_url = request.image_url
    if request.is_active is not None:
        product.is_active = request.is_active
    if request.is_tax_exempt is not None:
        product.is_tax_exempt = request.is_tax_exempt
    if request.is_kit is not None:
        product.is_kit = request.is_kit

    db.flush()

    if product.is_kit:
        if request.components is not None:
            if not request.components:
                raise HTTPException(status_code=400, detail="المنتج المُجمّع (kit) يجب أن يحتوي على مكوّن واحد على الأقل")
            _apply_kit_components(db, product, request.components)
        elif not components_of(db, product.id):
            raise HTTPException(status_code=400, detail="المنتج المُجمّع (kit) يجب أن يحتوي على مكوّن واحد على الأقل")
        product.stock = 0
    else:
        db.query(KitComponent).filter(KitComponent.kit_product_id == product.id).delete()
        if request.stock is not None:
            product.stock = request.stock

    db.commit()
    db.refresh(product)
    return _serialize(db, product)


@router.delete("/{product_id}")
def delete_product(product_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_perm("products"))):
    """Permanent delete ONLY for a product with no history and no stock (e.g. added by
    mistake). Anything else must be archived (tester: stock and history vanished)."""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="المنتج غير موجود")
    u = product_usage(db, product)
    if not u["deletable"]:
        raise HTTPException(status_code=409, detail=(
            "لا يمكن حذف منتج له حركات أو رصيد: " + u["summary"] + ". يمكنك أرشفته بدلاً من ذلك."))
    db.query(KitComponent).filter(KitComponent.kit_product_id == product.id).delete()
    db.delete(product)
    db.commit()
    return {"message": "تم حذف المنتج نهائياً"}


def product_usage(db: Session, product: Product) -> dict:
    from sqlalchemy import text as _t
    q = lambda sql: db.execute(_t(sql), {"p": product.id}).scalar() or 0   # noqa: E731
    counts = {
        "sales": q("SELECT count(*) FROM sale_items WHERE product_id = :p"),
        "returns": q("SELECT count(*) FROM return_items WHERE product_id = :p"),
        "purchase_orders": q("SELECT count(*) FROM purchase_order_lines WHERE product_id = :p"),
        "receipts": q("SELECT count(*) FROM goods_receipt_lines WHERE product_id = :p"),
        "movements": q("SELECT count(*) FROM stock_movements WHERE product_id = :p"),
        "consignment": q("SELECT count(*) FROM consignment_items WHERE product_id = :p"),
        "in_kits": q("SELECT count(*) FROM kit_components kc JOIN products k ON k.id = kc.kit_product_id "
                     "WHERE kc.component_product_id = :p AND k.is_active"),
    }
    stock = 0 if product.is_kit else float(product.stock or 0)
    labels = {"sales": "فواتير", "returns": "مرتجعات", "purchase_orders": "أوامر شراء", "receipts": "سندات استلام",
              "movements": "حركات مخزون", "consignment": "أمانات", "in_kits": "مكوّن في منتج مجمّع"}
    parts = [f"{labels[k]} ({v})" for k, v in counts.items() if v]
    if stock:
        parts.insert(0, f"رصيد حالي {stock:g}")
    blockers = []
    if stock:
        blockers.append(f"الرصيد الحالي {stock:g} — سوِّه إلى صفر أولاً من «حركة المخزون»")
    if counts["in_kits"]:
        blockers.append("مكوّن في منتج مجمّع نشط — أزله من المنتج المجمّع أولاً")
    return {"counts": counts, "stock": stock, "summary": "، ".join(parts) or "لا يوجد",
            "deletable": not any(counts.values()) and not stock,
            "archivable": not blockers, "archive_blockers": blockers, "is_active": bool(product.is_active)}


@router.get("/{product_id}/usage")
def get_product_usage(product_id: int, db: Session = Depends(get_db),
                      current_user: User = Depends(require_perm("products"))):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="المنتج غير موجود")
    return product_usage(db, product)


@router.post("/{product_id}/archive")
def archive_product(product_id: int, db: Session = Depends(get_db),
                    current_user: User = Depends(require_perm("products"))):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="المنتج غير موجود")
    u = product_usage(db, product)
    if not u["archivable"]:
        raise HTTPException(status_code=409, detail="لا يمكن أرشفة المنتج: " + "؛ ".join(u["archive_blockers"]))
    product.is_active = False
    db.commit()
    return {"message": "تمت أرشفة المنتج — يبقى سجله وحركاته، ويمكن استعادته"}


@router.post("/{product_id}/restore")
def restore_product(product_id: int, db: Session = Depends(get_db),
                    current_user: User = Depends(require_perm("products"))):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="المنتج غير موجود")
    product.is_active = True
    db.commit()
    return {"message": "تمت استعادة المنتج"}


@router.post("/upload-image")
async def upload_image(file: UploadFile = File(...), current_user: User = Depends(require_perm("products"))):
    from upload_guard import IMAGE, read_checked
    data, ext = await read_checked(file, IMAGE, 5 * 1024 * 1024)

    filename = f"{uuid.uuid4()}{ext}"
    filepath = os.path.join("uploads", filename)

    with open(filepath, "wb") as buffer:
        buffer.write(data)

    return {"url": f"/uploads/{filename}"}


@router.put("/{product_id}/stock")
def update_stock(product_id: int, quantity: float, db: Session = Depends(get_db), current_user: User = Depends(require_perm("stock_adjust"))):
    # Security test AUTH-12: admin only, and recorded in the stock ledger like /stock/adjust.
    from stock import record_movement
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="المنتج غير موجود")
    if product.is_kit:
        raise HTTPException(status_code=400, detail="لا يمكن تعديل مخزون منتج مُجمّع (kit) مباشرة؛ المخزون مشتق من المكوّنات")
    if quantity < 0:
        raise HTTPException(status_code=400, detail="الكمية لا يمكن أن تكون سالبة")
    delta = round(float(quantity) - float(product.stock or 0), 3)
    product.stock = quantity
    record_movement(db, product, delta, "adjust", ref_type="adjustment", user_id=current_user.id,
                    note="تعديل مباشر للمخزون")
    db.commit()
    return {"message": "تم تحديث المخزون", "stock": product.stock}
