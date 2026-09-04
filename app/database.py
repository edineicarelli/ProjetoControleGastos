from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from app.config import settings
import logging

logger = logging.getLogger(__name__)

# Handle SQLite vs PostgreSQL
connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    """Dependency for FastAPI endpoints"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """Initialize database tables"""
    # Import all models to ensure they are registered with Base.metadata
    import app.models # noqa
    Base.metadata.create_all(bind=engine)
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            result = conn.execute(text("PRAGMA table_info(accounts)"))
            columns = [row[1] for row in result.fetchall()]
            if columns and "is_active" not in columns:
                conn.execute(text("ALTER TABLE accounts ADD COLUMN is_active BOOLEAN DEFAULT 1"))
                conn.commit()
    except Exception as e:
        logger.debug(f"DB column check info: {e}")
    logger.info("Banco de dados inicializado com sucesso.")
