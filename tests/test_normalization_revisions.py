"""Normalization keeps the latest revision of each source record, and never merges different records (regression).

source_record_id is the first identifier a row carries, so every lot of one product shares it; grouping revisions on
it once collapsed 18 golden lots into 3 and 13 investigations into 2.
"""

from sqlalchemy import text

from backend.app.db.session import engine
from ingestion.normalization.service import REVISION_KEY_SQL, REVISION_KEYS

ROWS = """
WITH staged(id, source_system, record_type, source_record_id, raw_payload, ingestion_timestamp) AS (VALUES
  ('00000000-0000-0000-0000-000000000001'::uuid, 'MES', 'lot', 'PROD-1', '{"lot_id": "L1", "product_id": "PROD-1", "rev": 1}'::jsonb, '2026-01-01'::timestamptz),
  ('00000000-0000-0000-0000-000000000002'::uuid, 'MES', 'lot', 'PROD-1', '{"lot_id": "L1", "product_id": "PROD-1", "rev": 2}'::jsonb, '2026-02-01'::timestamptz),
  ('00000000-0000-0000-0000-000000000003'::uuid, 'MES', 'lot', 'PROD-1', '{"lot_id": "L2", "product_id": "PROD-1", "rev": 1}'::jsonb, '2026-01-01'::timestamptz),
  ('00000000-0000-0000-0000-000000000004'::uuid, 'QMS', 'investigation', 'PROD-1', '{"investigation_id": "INV-1", "product_id": "PROD-1"}'::jsonb, '2026-01-01'::timestamptz),
  ('00000000-0000-0000-0000-000000000005'::uuid, 'QMS', 'investigation', 'PROD-1', '{"investigation_id": "INV-2", "product_id": "PROD-1"}'::jsonb, '2026-01-01'::timestamptz),
  ('00000000-0000-0000-0000-000000000006'::uuid, 'X', 'unknown_type', 'SAME', '{"a": 1}'::jsonb, '2026-01-01'::timestamptz),
  ('00000000-0000-0000-0000-000000000007'::uuid, 'X', 'unknown_type', 'SAME', '{"a": 2}'::jsonb, '2026-01-01'::timestamptz)
)
SELECT raw_payload, row_number() OVER (
  PARTITION BY source_system, record_type, {key} ORDER BY ingestion_timestamp DESC, id DESC
) AS rank FROM staged
"""


def _latest() -> list[dict]:
    with engine.connect() as connection:
        rows = connection.execute(text(ROWS.replace("{key}", REVISION_KEY_SQL))).mappings().all()
    return [row["raw_payload"] for row in rows if row["rank"] == 1]


def test_each_record_keeps_only_its_latest_revision():
    lots = sorted((row["lot_id"], row["rev"]) for row in _latest() if "lot_id" in row)
    assert lots == [("L1", 2), ("L2", 1)]


def test_records_that_share_a_parent_id_are_never_merged():
    assert sorted(row["investigation_id"] for row in _latest() if "investigation_id" in row) == ["INV-1", "INV-2"]


def test_an_unknown_record_type_is_not_merged_at_all():
    assert sorted(row["a"] for row in _latest() if "a" in row) == [1, 2]


def test_every_record_type_the_normalizer_orders_has_its_own_identity():
    for record_type in (
        "product product_version supplier manufacturing_site component lot requirement change risk failure_mode "
        "control investigation complaint evidence_metadata evidence_file"
    ).split():
        assert record_type in REVISION_KEYS
