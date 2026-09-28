from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


from backend.app.db.models.ask import *
from backend.app.db.models.customer_lifecycle import *
from backend.app.db.models.enterprise import *
from backend.app.db.models.foundation import *
from backend.app.db.models.ingestion import *
from backend.app.db.models.normalization import *
from backend.app.db.models.stage2 import *
from backend.app.db.models.stage3 import *
