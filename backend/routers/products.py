from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from pydantic import BaseModel
from database import get_db, Product, Category, KitComponent, Uom
from routers.auth import get_current_user, require_admin, User
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
                    current_user: User = Depends(require_admin)):
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
def create_category(request: CategoryCreate, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    category = Category(name=request.name)
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


@router.put("/categories/{category_id}", response_model=CategoryResponse)
def update_category(category_id: int, request: CategoryCreate, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="التصنيف غير موجود")
    category.name = request.name
    db.commit()
    db.refresh(category)
    return category


@router.delete("/categories/{category_id}")
def delete_category(category_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
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
                     current_user: User = Depends(require_admin)):
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
def create_product(request: ProductCreate, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
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
def update_product(product_id: int, request: ProductUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
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
def delete_product(product_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="المنتج غير موجود")
    product.is_active = False
    db.commit()
    return {"message": "تم حذف المنتج بنجاح"}


@router.post("/upload-image")
async def upload_image(file: UploadFile = File(...), current_user: User = Depends(require_admin)):
    allowed_extensions = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed_extensions:
        raise HTTPException(status_code=400, detail="نوع الملف غير مدعوم")

    filename = f"{uuid.uuid4()}{ext}"
    filepath = os.path.join("uploads", filename)

    with open(filepath, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    return {"url": f"/uploads/{filename}"}


@router.put("/{product_id}/stock")
def update_stock(product_id: int, quantity: float, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="المنتج غير موجود")
    if product.is_kit:
        raise HTTPException(status_code=400, detail="لا يمكن تعديل مخزون منتج مُجمّع (kit) مباشرة؛ المخزون مشتق من المكوّنات")
    product.stock = quantity
    db.commit()
    return {"message": "تم تحديث المخزون", "stock": product.stock}
