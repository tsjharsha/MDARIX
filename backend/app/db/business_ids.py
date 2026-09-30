"""Central business-identifier allocation (Master Data Foundation §1.2).

Every readable business ID (APP00001, PROD00001, INV00001, ...) is issued by
``md_master.next_business_id(prefix)`` in the control-plane database. Tables in
the control plane use it as a column default; services that create records in a
tenant data plane call :func:`allocate_business_id` with a control-plane session
so IDs stay unique across the whole deployment.
"""

from sqlalchemy import text
from sqlalchemy.orm import Session


def allocate_business_id(control_db: Session, prefix: str) -> str:
    """Atomically reserve the next identifier for ``prefix`` (never MAX()+1, never recycled)."""
    return control_db.execute(text("select md_master.next_business_id(:prefix)"), {"prefix": prefix}).scalar_one()
