from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

BASE_DIR = Path(__file__).resolve().parent.parent.parent

PORTAL_SQLITE_PATH = BASE_DIR / "runtime_data" / "portal" / "portal.db"
PORTAL_SQLALCHEMY_DATABASE_URL = f"sqlite:///{PORTAL_SQLITE_PATH}"

PORTAL_SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)

portal_engine = create_engine(
    PORTAL_SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
)

PortalSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=portal_engine)

PortalBase = declarative_base()


def get_portal_db():
    db = PortalSessionLocal()
    try:
        yield db
    finally:
        db.close()
