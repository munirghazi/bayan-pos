"""Kit (bill-of-materials) logic.

Rules for this build:
  - A kit's stock is DERIVED from its components (the kit has no own stock).
  - A kit's price is FIXED (set on the product itself).
  - Nesting is allowed (a component may be a kit); cycles are rejected.

All queries below run on the caller's tenant-pinned session, so RLS keeps
everything scoped to one tenant automatically.
"""
from sqlalchemy.orm import Session

from database import Product, KitComponent


def components_of(db: Session, kit_id: int) -> list[KitComponent]:
    return db.query(KitComponent).filter(KitComponent.kit_product_id == kit_id).all()


def _product(db: Session, pid: int) -> Product | None:
    return db.query(Product).filter(Product.id == pid).first()


def available_quantity(db: Session, product: Product, memo: dict | None = None) -> int:
    """How many of `product` can be fulfilled from current stock.

    Leaf product -> its own stock. Kit -> min over components of
    floor(available(component) / qty). Missing/zero components -> 0.
    """
    if memo is None:
        memo = {}
    if product.id in memo:
        return memo[product.id]
    if not product.is_kit:
        memo[product.id] = max(int(product.stock or 0), 0)
        return memo[product.id]

    memo[product.id] = 0  # break any accidental cycle during recursion
    rows = components_of(db, product.id)
    if not rows:
        return 0
    best: int | None = None
    for row in rows:
        cp = _product(db, row.component_product_id)
        if cp is None or row.quantity <= 0:
            best = 0
            break
        can = available_quantity(db, cp, memo) // row.quantity
        best = can if best is None else min(best, can)
    result = max(best or 0, 0)
    memo[product.id] = result
    return result


def explode_to_leaves(db: Session, product: Product, quantity: int,
                      acc: dict[int, int] | None = None) -> dict[int, int]:
    """Aggregate leaf-product demand for selling `quantity` of `product`."""
    if acc is None:
        acc = {}
    if not product.is_kit:
        acc[product.id] = acc.get(product.id, 0) + quantity
        return acc
    for row in components_of(db, product.id):
        cp = _product(db, row.component_product_id)
        if cp is not None:
            explode_to_leaves(db, cp, quantity * row.quantity, acc)
    return acc


def reachable(db: Session, start_id: int, target_id: int, seen: set | None = None) -> bool:
    """True if `target_id` is reachable from `start_id` following components.

    Used to reject cycles: adding kit -> component is unsafe when the component
    can already reach the kit (reachable(component_id, kit_id)). Also catches
    self-reference since reachable(x, x) is True.
    """
    if start_id == target_id:
        return True
    if seen is None:
        seen = set()
    if start_id in seen:
        return False
    seen.add(start_id)
    for row in components_of(db, start_id):
        if reachable(db, row.component_product_id, target_id, seen):
            return True
    return False
