from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, cast, Date
from database import get_db, Sale, SaleItem, Donation, Product
from routers.auth import get_current_user, User
from datetime import datetime, timedelta

router = APIRouter()


# ===================== Routes =====================

@router.get("/dashboard")
def get_dashboard(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    today = datetime.utcnow().date()
    today_start = datetime.combine(today, datetime.min.time())
    today_end = datetime.combine(today, datetime.max.time())

    # Today's sales
    today_sales = db.query(func.coalesce(func.sum(Sale.total), 0)).filter(
        Sale.created_at.between(today_start, today_end)
    ).scalar()

    today_sales_count = db.query(func.count(Sale.id)).filter(
        Sale.created_at.between(today_start, today_end)
    ).scalar()

    # Today's donations
    today_donations = db.query(func.coalesce(func.sum(Donation.amount), 0)).filter(
        Donation.created_at.between(today_start, today_end)
    ).scalar()

    today_donations_count = db.query(func.count(Donation.id)).filter(
        Donation.created_at.between(today_start, today_end)
    ).scalar()

    # Total sales (all time)
    total_sales = db.query(func.coalesce(func.sum(Sale.total), 0)).scalar()
    total_sales_count = db.query(func.count(Sale.id)).scalar()

    # Total donations (all time)
    total_donations = db.query(func.coalesce(func.sum(Donation.amount), 0)).scalar()
    total_donations_count = db.query(func.count(Donation.id)).scalar()

    # Low stock products
    low_stock = db.query(Product).filter(Product.stock <= 5, Product.is_active == True).all()
    low_stock_list = [{"id": p.id, "name": p.name, "stock": p.stock} for p in low_stock]

    # Recent sales (last 5)
    recent_sales = db.query(Sale).order_by(Sale.created_at.desc()).limit(5).all()
    recent_sales_list = [
        {
            "id": s.id,
            "total": s.total,
            "payment_method": s.payment_method,
            "created_at": s.created_at.isoformat(),
            "user_name": s.user.full_name if s.user else None,
        }
        for s in recent_sales
    ]

    # Recent donations (last 5)
    recent_donations = db.query(Donation).order_by(Donation.created_at.desc()).limit(5).all()
    recent_donations_list = [
        {
            "id": d.id,
            "amount": d.amount,
            "donor_name": d.donor_name,
            "created_at": d.created_at.isoformat(),
        }
        for d in recent_donations
    ]

    return {
        "today": {
            "sales_total": round(float(today_sales), 2),
            "sales_count": today_sales_count,
            "donations_total": round(float(today_donations), 2),
            "donations_count": today_donations_count,
        },
        "all_time": {
            "sales_total": round(float(total_sales), 2),
            "sales_count": total_sales_count,
            "donations_total": round(float(total_donations), 2),
            "donations_count": total_donations_count,
        },
        "low_stock": low_stock_list,
        "recent_sales": recent_sales_list,
        "recent_donations": recent_donations_list,
    }


@router.get("/sales-report")
def get_sales_report(
    start_date: str = Query(None, description="YYYY-MM-DD"),
    end_date: str = Query(None, description="YYYY-MM-DD"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(Sale).order_by(Sale.created_at.desc())

    if start_date:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        query = query.filter(Sale.created_at >= start)
    if end_date:
        end = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
        query = query.filter(Sale.created_at < end)

    sales = query.all()

    total = sum(s.total for s in sales)
    cash_total = sum(s.total for s in sales if s.payment_method == "cash")
    card_total = sum(s.total for s in sales if s.payment_method == "card")
    transfer_total = sum(s.total for s in sales if s.payment_method == "transfer")

    sales_list = []
    for s in sales:
        items_detail = []
        for item in s.items:
            items_detail.append({
                "product_id": item.product_id,
                "product_name": item.product.name if item.product else "منتج محذوف",
                "quantity": item.quantity,
                "price": item.price,
                "subtotal": round(item.price * item.quantity, 2),
                "is_tax_exempt": item.is_tax_exempt,
            })
        
        # Build a summary string of product names
        products_summary = " | ".join(
            f"{it['product_name']} ×{it['quantity']}" for it in items_detail
        )
        
        sales_list.append({
            "id": s.id,
            "total": s.total,
            "payment_method": s.payment_method,
            "created_at": s.created_at.isoformat(),
            "user_name": s.user.full_name if s.user else None,
            "items_count": len(s.items),
            "items": items_detail,
            "products_summary": products_summary,
        })

    return {
        "sales": sales_list,
        "summary": {
            "total": round(total, 2),
            "count": len(sales),
            "cash_total": round(cash_total, 2),
            "card_total": round(card_total, 2),
            "transfer_total": round(transfer_total, 2),
        }
    }


@router.get("/donations-report")
def get_donations_report(
    start_date: str = Query(None, description="YYYY-MM-DD"),
    end_date: str = Query(None, description="YYYY-MM-DD"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(Donation).order_by(Donation.created_at.desc())

    if start_date:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        query = query.filter(Donation.created_at >= start)
    if end_date:
        end = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
        query = query.filter(Donation.created_at < end)

    donations = query.all()

    total = sum(d.amount for d in donations)
    cash_total = sum(d.amount for d in donations if d.payment_method == "cash")
    card_total = sum(d.amount for d in donations if d.payment_method == "card")
    transfer_total = sum(d.amount for d in donations if d.payment_method == "transfer")

    donations_list = [
        {
            "id": d.id,
            "amount": d.amount,
            "donor_name": d.donor_name,
            "note": d.note,
            "payment_method": d.payment_method,
            "created_at": d.created_at.isoformat(),
            "user_name": d.user.full_name if d.user else None,
        }
        for d in donations
    ]

    return {
        "donations": donations_list,
        "summary": {
            "total": round(total, 2),
            "count": len(donations),
            "cash_total": round(cash_total, 2),
            "card_total": round(card_total, 2),
            "transfer_total": round(transfer_total, 2),
        }
    }
