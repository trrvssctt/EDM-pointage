from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from server.app.config import DATABASE_URL

_options = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=_options, pool_pre_ping=True)

if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(connexion, _):
        curseur = connexion.cursor()
        curseur.execute("PRAGMA foreign_keys=ON")
        curseur.execute("PRAGMA journal_mode=WAL")
        curseur.close()

SessionLocale = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocale()
    try:
        yield db
    finally:
        db.close()


def initialiser_base():
    from server.app import models  # noqa: F401  (enregistre les tables)
    Base.metadata.create_all(engine)
