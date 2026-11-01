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
from backend.app.db.models.pilot_support import *
from backend.app.db.models.stage2 import *
from backend.app.db.models.stage3 import *
from backend.app.db.models.reporting import *
from backend.app.db.models.regulatory import *
from backend.app.db.models.master import *
from backend.app.db.models.workflow import *
from backend.app.db.models.signals import *
from backend.app.db.models.case_scope import *
from backend.app.db.models.intelligence import *
from backend.app.db.models.reviews import *
from backend.app.db.models.decision_outcomes import *
from backend.app.db.models.complaint_review import *
from backend.app.db.models.reportability import *
from backend.app.db.models.capa_effectiveness import *
from backend.app.db.models.market_assessment import *
from backend.app.db.models.complaint_disposition import *
from backend.app.db.models.intake import *
from backend.app.db.models.authority_reports import *
from backend.app.db.models.case_ai import *
