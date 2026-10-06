"""The human-readable business identifier every business object carries (migration md26; CUST000001, CMP000001).

The database assigns it when the row is inserted (a trigger, so connector syncs and imports get one too) and refuses
any change to it, so models declare it as server-generated and read-only: the application never sets it, and SQLAlchemy
reads it back after the insert. The UUID ``id`` stays the technical key; ``business_id`` is what people see.
"""

from sqlalchemy import FetchedValue, String
from sqlalchemy.orm import Mapped, mapped_column


def business_id_column() -> Mapped[str]:
    return mapped_column(String(20), server_default=FetchedValue(), nullable=False)
