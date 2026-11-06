"""Performance (stress test): indexes for the selling / report / return paths.

`sale_items.sale_id` had no index, so every receipt, report and return scanned
all of a tenant's invoice lines; it gets slower every day of trading.
Date-range reports filter by (tenant_id, issued_at).

Plain CREATE INDEX (short lock); the tables are small today.

Revision ID: 0031_hot_path_indexes
Revises: 0030_token_revocation
Create Date: 2026-11-06
"""
from alembic import op

revision = "0031_hot_path_indexes"
down_revision = "0030_token_revocation"
branch_labels = None
depends_on = None

INDEXES = {
    "ix_sale_items_sale": "sale_items (sale_id)",
    "ix_sale_items_product": "sale_items (product_id)",
    "ix_sales_tenant_issued": "sales (tenant_id, issued_at)",
    "ix_sales_customer": "sales (customer_id)",
    "ix_sales_register": "sales (register_id)",
    "ix_returns_tenant_issued": "returns (tenant_id, issued_at)",
    "ix_returns_register": "returns (register_id)",
    "ix_return_items_product": "return_items (product_id)",
    "ix_donations_tenant_issued": "donations (tenant_id, issued_at)",
    "ix_donations_register": "donations (register_id)",
    "ix_consignment_ledger_sale": "consignment_ledger (sale_id)",
    "ix_products_category": "products (category_id)",
}


def upgrade() -> None:
    for name, target in INDEXES.items():
        op.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {target}")


def downgrade() -> None:
    for name in INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {name}")
