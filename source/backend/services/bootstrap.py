import os

from sqlalchemy.orm import Session

from source.backend.database import Base, engine
from models.admin_data import Admin, Setting
from services.auth import hash_password


def init_database() -> None:
    Base.metadata.create_all(bind=engine)


def seed_defaults(db: Session) -> None:
    if not db.query(Setting).first():
        db.add(Setting(id=1, daily_search_limit=3, special_event_limit=5, event_enabled=False))

    admin_username = os.getenv("ADMIN_USERNAME", "admin")
    admin_password = os.getenv("ADMIN_PASSWORD", "Admin@123")
    existing_admin = db.query(Admin).filter(Admin.username == admin_username).first()
    if not existing_admin:
        db.add(Admin(username=admin_username, password_hash=hash_password(admin_password)))

    db.commit()
