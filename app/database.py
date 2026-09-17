from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from app.config import settings
import logging

logger = logging.getLogger(__name__)

from sqlalchemy.pool import NullPool

# Handle SQLite vs PostgreSQL
connect_args = {}
pool_kwargs = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
    pool_kwargs = {"poolclass": NullPool}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    echo=False,
    **pool_kwargs
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
    """Initialize database tables, apply schema migrations, and seed default admin"""
    # Import all models to ensure they are registered with Base.metadata
    import app.models # noqa
    Base.metadata.create_all(bind=engine)
    
    # SQLite automatic migrations for new columns
    try:
        with engine.connect() as conn:
            # 1. Accounts is_active column
            res_acc = conn.execute(text("PRAGMA table_info(accounts)"))
            acc_cols = [row[1] for row in res_acc.fetchall()]
            if acc_cols and "is_active" not in acc_cols:
                conn.execute(text("ALTER TABLE accounts ADD COLUMN is_active BOOLEAN DEFAULT 1"))
                conn.commit()

            # 2. Users auth and RBAC columns
            res_usr = conn.execute(text("PRAGMA table_info(users)"))
            usr_cols = [row[1] for row in res_usr.fetchall()]
            
            if usr_cols:
                if "phone" not in usr_cols:
                    conn.execute(text("ALTER TABLE users ADD COLUMN phone VARCHAR"))
                if "password_hash" not in usr_cols:
                    conn.execute(text("ALTER TABLE users ADD COLUMN password_hash VARCHAR"))
                if "system_role" not in usr_cols:
                    conn.execute(text("ALTER TABLE users ADD COLUMN system_role VARCHAR DEFAULT 'visualizador'"))
                if "is_admin_default" not in usr_cols:
                    conn.execute(text("ALTER TABLE users ADD COLUMN is_admin_default BOOLEAN DEFAULT 0"))
                if "must_change_password" not in usr_cols:
                    conn.execute(text("ALTER TABLE users ADD COLUMN must_change_password BOOLEAN DEFAULT 0"))
                if "temp_password" not in usr_cols:
                    conn.execute(text("ALTER TABLE users ADD COLUMN temp_password VARCHAR"))
                if "temp_password_expires_at" not in usr_cols:
                    conn.execute(text("ALTER TABLE users ADD COLUMN temp_password_expires_at DATETIME"))
                if "is_telegram_authenticated" not in usr_cols:
                    conn.execute(text("ALTER TABLE users ADD COLUMN is_telegram_authenticated BOOLEAN DEFAULT 0"))
                conn.commit()

            # 3. BackupConfigs network credentials columns
            res_cfg = conn.execute(text("PRAGMA table_info(backup_configs)"))
            cfg_cols = [row[1] for row in res_cfg.fetchall()]
            if cfg_cols:
                if "network_username" not in cfg_cols:
                    conn.execute(text("ALTER TABLE backup_configs ADD COLUMN network_username VARCHAR"))
                if "network_password" not in cfg_cols:
                    conn.execute(text("ALTER TABLE backup_configs ADD COLUMN network_password VARCHAR"))
                if "network_domain" not in cfg_cols:
                    conn.execute(text("ALTER TABLE backup_configs ADD COLUMN network_domain VARCHAR"))
                conn.commit()
    except Exception as e:
        logger.debug(f"DB column check info: {e}")

    # Seed Default Administrator User & Default Workspace
    try:
        from app.models.user import User
        from app.models.workspace import Workspace, WorkspaceMember
        from app.services.auth_service import AuthService
        import uuid

        db = SessionLocal()
        try:
            # Procura por usuário admin existente
            admin_user = db.query(User).filter((User.username == "admin") | (User.is_admin_default == True)).first()
            
            # Garante que haja pelo menos um workspace padrão
            default_ws = db.query(Workspace).first()
            if not default_ws:
                default_ws = Workspace(
                    name="Pessoal (PF)",
                    type="personal",
                    invite_code=str(uuid.uuid4())[:8].upper()
                )
                db.add(default_ws)
                db.flush()

            if not admin_user:
                logger.info("Criando usuário administrador padrão do sistema ('admin')...")
                admin_user = User(
                    telegram_id="admin_system",
                    username="admin",
                    name="Administrador do Sistema",
                    phone="(11) 99999-9999",
                    password_hash=AuthService.hash_password("admin123"),
                    system_role="administrador",
                    is_admin_default=True,
                    must_change_password=True,  # Solicita alteração no primeiro login por segurança
                    is_active=True,
                    current_workspace_id=default_ws.id
                )
                db.add(admin_user)
                db.flush()

                # Vincula como owner do workspace
                member = WorkspaceMember(
                    workspace_id=default_ws.id,
                    user_id=admin_user.id,
                    role="owner"
                )
                db.add(member)
                db.commit()
                logger.info("Usuário 'admin' criado com sucesso. Senha padrão: admin123")
            else:
                # Garante que o admin tenha a role e flag corretas
                if not admin_user.is_admin_default or admin_user.system_role != "administrador":
                    admin_user.is_admin_default = True
                    admin_user.system_role = "administrador"
                    if not admin_user.password_hash:
                        admin_user.password_hash = AuthService.hash_password("admin123")
                        admin_user.must_change_password = True
                    db.commit()
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Erro ao semear usuário admin: {e}")

    logger.info("Banco de dados inicializado com sucesso.")
