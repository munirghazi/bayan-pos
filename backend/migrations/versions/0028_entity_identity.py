"""Release 2a: organization identity (entity type + registration numbers) and the
national address in the order of the official address proof, Arabic + English.

tenants:          entity_type, name_en, unified_number, freelance_doc_number
                  (cr_number, license_number, vat_number, vat_enabled already exist)
tenant_settings:  short_address, street_name_en, district_en, city_en, country_en,
                  address_proof_number, address_proof_expiry, show_en_address,
                  receipt_thanks
                  (building_number, street_name, additional_number = الرقم الفرعي,
                   district, postal_code, city, region, country already exist)

Identity becomes platform-controlled: the legal name and VAT number the tenant
had typed into Settings are copied into `tenants` (the authoritative record).
Existing tenants become "جمعية أهلية"; country defaults to KSA in both languages.

Revision ID: 0028_entity_identity
Revises: 0027_payments_drafts
Create Date: 2026-11-06
"""
import sqlalchemy as sa
from alembic import op

revision = "0028_entity_identity"
down_revision = "0027_payments_drafts"
branch_labels = None
depends_on = None

_TYPES = ("nonprofit_association", "nonprofit_foundation", "endowment", "cooperative",
          "company", "sole_establishment", "online_store", "freelancer", "other")


def _forced(bind, tables):
    rows = bind.execute(sa.text(
        "SELECT relname FROM pg_class WHERE relkind='r' AND relforcerowsecurity "
        "AND relnamespace='public'::regnamespace")).scalars().all()
    return [t for t in tables if t in set(rows)]


def upgrade() -> None:
    bind = op.get_bind()
    forced = _forced(bind, ("tenant_settings",))
    for t in forced:
        op.execute(f"ALTER TABLE {t} NO FORCE ROW LEVEL SECURITY")

    types = ", ".join(f"'{t}'" for t in _TYPES)
    op.execute(f"""ALTER TABLE tenants
        ADD COLUMN IF NOT EXISTS entity_type varchar(30) NOT NULL DEFAULT 'nonprofit_association',
        ADD COLUMN IF NOT EXISTS name_en varchar(200),
        ADD COLUMN IF NOT EXISTS unified_number varchar(10),
        ADD COLUMN IF NOT EXISTS freelance_doc_number varchar(30)""")
    op.execute(f"ALTER TABLE tenants ADD CONSTRAINT ck_tenant_entity_type CHECK (entity_type IN ({types}))")
    op.execute("ALTER TABLE tenants ADD CONSTRAINT ck_tenant_unified_number "
               "CHECK (unified_number IS NULL OR unified_number ~ '^7[0-9]{9}$')")

    op.execute("""ALTER TABLE tenant_settings
        ADD COLUMN IF NOT EXISTS short_address varchar(8),
        ADD COLUMN IF NOT EXISTS street_name_en varchar(150),
        ADD COLUMN IF NOT EXISTS district_en varchar(100),
        ADD COLUMN IF NOT EXISTS city_en varchar(100),
        ADD COLUMN IF NOT EXISTS country_en varchar(100),
        ADD COLUMN IF NOT EXISTS address_proof_number varchar(30),
        ADD COLUMN IF NOT EXISTS address_proof_expiry date,
        ADD COLUMN IF NOT EXISTS show_en_address boolean NOT NULL DEFAULT false,
        ADD COLUMN IF NOT EXISTS receipt_thanks varchar(200)""")

    # identity -> tenants (authoritative). What the tenant typed for invoices wins.
    op.execute("""UPDATE tenants t SET
            name = COALESCE(NULLIF(trim(s.seller_name), ''), t.name),
            vat_number = COALESCE(NULLIF(trim(s.vat_number), ''), t.vat_number)
        FROM tenant_settings s WHERE s.tenant_id = t.id""")
    # country in both languages (old rows hold 'SA' or nothing)
    op.execute("""UPDATE tenant_settings SET country = 'المملكة العربية السعودية'
        WHERE country IS NULL OR trim(country) = '' OR upper(trim(country)) IN ('SA', 'KSA', 'السعودية')""")
    op.execute("""UPDATE tenant_settings SET country_en = 'Kingdom of Saudi Arabia'
        WHERE country_en IS NULL AND country = 'المملكة العربية السعودية'""")

    for t in forced:
        op.execute(f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    bind = op.get_bind()
    forced = _forced(bind, ("tenant_settings",))
    for t in forced:
        op.execute(f"ALTER TABLE {t} NO FORCE ROW LEVEL SECURITY")
    op.execute("""ALTER TABLE tenant_settings
        DROP COLUMN IF EXISTS short_address, DROP COLUMN IF EXISTS street_name_en,
        DROP COLUMN IF EXISTS district_en, DROP COLUMN IF EXISTS city_en,
        DROP COLUMN IF EXISTS country_en, DROP COLUMN IF EXISTS address_proof_number,
        DROP COLUMN IF EXISTS address_proof_expiry, DROP COLUMN IF EXISTS show_en_address,
        DROP COLUMN IF EXISTS receipt_thanks""")
    op.execute("ALTER TABLE tenants DROP CONSTRAINT IF EXISTS ck_tenant_unified_number")
    op.execute("ALTER TABLE tenants DROP CONSTRAINT IF EXISTS ck_tenant_entity_type")
    op.execute("""ALTER TABLE tenants DROP COLUMN IF EXISTS entity_type, DROP COLUMN IF EXISTS name_en,
        DROP COLUMN IF EXISTS unified_number, DROP COLUMN IF EXISTS freelance_doc_number""")
    for t in forced:
        op.execute(f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY")
