import os
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker
BASE_DIR = Path(__file__).resolve().parent
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'restaurant_finder.db'}")


def ensure_mysql_database(database_url: str) -> None:
    url = make_url(database_url)
    if not url.drivername.startswith("mysql") or not url.database:
        return

    server_url = URL.create(
        drivername=url.drivername,
        username=url.username,
        password=url.password,
        host=url.host,
        port=url.port,
        query=url.query,
    )
    database_name = url.database.replace("`", "``")
    server_engine = create_engine(server_url, pool_pre_ping=True)
    with server_engine.connect() as connection:
        connection.execute(
            text(
                f"CREATE DATABASE IF NOT EXISTS `{database_name}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        )
        connection.commit()
    server_engine.dispose()


ensure_mysql_database(DATABASE_URL)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
      yield db
    finally:
      db.close()
