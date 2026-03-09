from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from pydantic import BaseModel
from database import get_db, Product, Category
from routers.auth import get_current_user, require_admin, User
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


class ProductResponse(BaseModel):
    id: int
    name: str
    price: float
    category_id: int | None
    category: CategoryResponse | None
    stock: int
    image_url: str | None
    is_active: bool
    is_tax_exempt: bool = False

    class Config:
        from_attributes = True


class ProductCreate(BaseModel):
    name: str
    price: float
    category_id: int | None = None
    stock: int = 0
    image_url: str | None = None
    is_tax_exempt: bool = False


class ProductUpdate(BaseModel):
    name: str | None = None
    price: float | None = None
    category_id: int | None = None
    stock: int | None = None
    image_url: str | None = None
    is_active: bool | None = None
    is_tax_exempt: bool | None = None


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
    return db.query(Product).filter(Product.is_active == True).all()


@router.get("/all", response_model=list[ProductResponse])
def get_all_products(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    return db.query(Product).all()


@router.get("/{product_id}", response_model=ProductResponse)
def get_product(product_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="المنتج غير موجود")
    return product


@router.post("/", response_model=ProductResponse)
def create_product(request: ProductCreate, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    product = Product(
        name=request.name,
        price=request.price,
        category_id=request.category_id,
        stock=request.stock,
        image_url=request.image_url,
        is_tax_exempt=request.is_tax_exempt,
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


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
    if request.stock is not None:
        product.stock = request.stock
    if request.image_url is not None:
        product.image_url = request.image_url
    if request.is_active is not None:
        product.is_active = request.is_active
    if request.is_tax_exempt is not None:
        product.is_tax_exempt = request.is_tax_exempt

    db.commit()
    db.refresh(product)
    return product


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
def update_stock(product_id: int, quantity: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="المنتج غير موجود")
    product.stock = quantity
    db.commit()
    return {"message": "تم تحديث المخزون", "stock": product.stock}
