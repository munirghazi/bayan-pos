# Kitting (product kits / bundles)

Adds "kit" products — a product composed of other products (e.g. a food basket =
rice ×2 + oil ×1 + dates ×3). Built on the multi-tenant + RLS foundation, so the
new table is tenant-isolated like everything else.

**Verified:** `pytest tests/test_kitting.py` — 2/2 pass (full lifecycle + tenant
isolation of `kit_components`), and the existing isolation suite still passes.

## Chosen semantics

- **Stock is derived from components** — a kit has no own stock.
  `available(kit) = min over components of floor(available(component) / qty)`.
- **Price is fixed** — you set the kit's price; it is **not** the sum of components.
- **Nesting allowed** — a component may itself be a kit. Selling explodes down to
  leaf (non-kit) products. **Cycles and self-reference are rejected** (HTTP 400).

## Files

**New**
- `kits.py` — availability (recursive), explode-to-leaves, cycle detection.
- `migrations/versions/0002_kitting.py` — `is_kit` column + `kit_components` table + RLS.
- `tests/test_kitting.py`

**Changed**
- `database.py` — `Product.is_kit`; new `KitComponent` model; `kit_components` added
  to the RLS table list.
- `routers/products.py` — create/update accept `is_kit` + `components`; responses add
  `is_kit`, `available_stock`, `components`; direct stock edits blocked on kits.
- `routers/sales.py` — a kit line is priced at the kit's fixed price and deducts stock
  from its **leaf** components; stock is validated across the whole sale before any
  deduction (prevents oversell and partial writes).

## API

**Create a kit**
```http
POST /api/products
{
  "name": "سلة غذائية",
  "price": 75,
  "is_kit": true,
  "components": [
    { "product_id": 11, "quantity": 2 },
    { "product_id": 12, "quantity": 1 },
    { "product_id": 13, "quantity": 3 }
  ]
}
```

**Update** — `PUT /api/products/{id}`; sending `components` **replaces** the kit's
components (validated again for cycles). Toggling `is_kit:false` clears components.

**Product response** now includes:
```json
{ "...": "...", "is_kit": true, "available_stock": 10,
  "components": [ { "product_id": 11, "product_name": "أرز", "quantity": 2 } ] }
```

**Selling** — unchanged request shape (`POST /api/sales`); if a line's product is a
kit it is charged at the kit price and deducts leaf-component stock. Insufficient leaf
stock returns 400 naming the short component. `PUT /api/products/{id}/stock` returns
400 for kits (stock is derived).

Validation errors (400) are returned in Arabic, e.g. cycle → «... تُنشئ حلقة مكوّنات».

## Apply

```bash
# adds migration 0002 on top of Phase 0
APP_DB_ROLE=pos_app alembic upgrade head
pytest tests/test_kitting.py
```

The migration is **idempotent** (safe whether or not `is_kit`/`kit_components` already
exist), because the Phase-0 baseline builds tables from the live models.

## Notes / limitations

- A soft-deleted (`is_active=false`) component still contributes stock to its parent
  kit's availability — deactivating a leaf doesn't hide it from kits. Handle in a later
  pass if needed.
- Availability is computed per request (small N+1 on the product list). Fine at charity
  scale; can be memoised/denormalised later if catalogues grow large.
- The kit's own `stock` column is forced to 0 and ignored.

## Frontend

The backend contract above is all the UI needs. The product-creation form
(`frontend/src/pages/Products.jsx`) still needs a **"This is a kit" toggle + component
picker** (add rows of product + quantity) and to show `available_stock`/`components`.
Say the word and I'll wire that into `Products.jsx`.
