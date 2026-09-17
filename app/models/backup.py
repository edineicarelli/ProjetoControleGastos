import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base

class BackupConfig(Base):
    __tablename__ = "backup_configs"

    id = Column(Integer, primary_key=True, index=True)
    is_scheduled = Column(Boolean, default=False)
    frequency_type = Column(String, default="daily")  # "hours", "daily", "weekly", "biweekly", "monthly"
    interval_hours = Column(Integer, default=24)      # 1, 2, 3, 4, 6, 8, 12, 24
    daily_time = Column(String, default="03:00")      # "HH:MM"
    weekly_day = Column(Integer, default=6)           # 0=Segunda, ..., 6=Domingo
    storage_destinations = Column(Text, default='["local"]')  # JSON array: ["local", "network", "gdrive", "onedrive"]
    local_path = Column(String, default="/app/data/backups")
    network_path = Column(String, nullable=True)     # Ex: /mnt/backups_rede ou //servidor/pasta
    network_username = Column(String, nullable=True) # Usuário de acesso à rede/SMB
    network_password = Column(String, nullable=True) # Senha de acesso à rede/SMB
    network_domain = Column(String, nullable=True)   # Domínio / Workgroup de rede
    cloud_provider = Column(String, default="gdrive") # "gdrive", "onedrive", "webhook"
    cloud_config = Column(Text, nullable=True)       # JSON ou URL/Token de integração
    retention_days = Column(Integer, default=30)     # 1, 2, 3, 4, 5, 7, 10, 15, 20, 30, 60...
    include_uploads = Column(Boolean, default=True)
    last_backup_at = Column(DateTime, nullable=True)
    last_status = Column(String, nullable=True)      # "success", "failed"
    last_error = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

class BackupRecord(Base):
    __tablename__ = "backup_records"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False, index=True)
    file_path = Column(String, nullable=False)
    file_size_bytes = Column(Integer, default=0)
    backup_type = Column(String, default="manual")   # "manual", "scheduled"
    destinations_stored = Column(Text, default='["local"]')  # JSON array
    status = Column(String, default="success")       # "success", "failed"
    details = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    created_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    created_by_user = relationship("User")
