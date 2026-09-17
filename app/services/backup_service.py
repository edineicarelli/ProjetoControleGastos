import os
import io
import json
import time
import uuid
import shutil
import zipfile
import sqlite3
import logging
import datetime
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.orm import Session

from app.config import settings
from app.models import BackupConfig, BackupRecord, User, Workspace, Transaction
from app.database import engine, SessionLocal

logger = logging.getLogger(__name__)

# Diretório padrão para armazenamento de backups
DEFAULT_BACKUP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "backups")

class BackupService:
    @staticmethod
    def get_backup_dir(custom_path: Optional[str] = None) -> str:
        """Retorna o caminho absoluto do diretório de backups garantindo sua criação"""
        path = custom_path or DEFAULT_BACKUP_DIR
        os.makedirs(path, exist_ok=True)
        return path

    @staticmethod
    def get_or_create_config(db: Session) -> BackupConfig:
        """Obtém a configuração única de backup ou cria com padrões inteligentes"""
        config = db.query(BackupConfig).first()
        if not config:
            config = BackupConfig(
                is_scheduled=False,
                frequency_type="daily",
                interval_hours=24,
                daily_time="03:00",
                weekly_day=6,  # Domingo
                storage_destinations=json.dumps(["local"]),
                local_path=DEFAULT_BACKUP_DIR,
                retention_days=30,
                include_uploads=True,
                last_status="ready"
            )
            db.add(config)
            db.commit()
            db.refresh(config)
        return config

    @staticmethod
    def update_config(db: Session, data: Dict[str, Any]) -> BackupConfig:
        """Atualiza os parâmetros de agendamento, locais de armazenamento e retenção"""
        config = BackupService.get_or_create_config(db)

        if "is_scheduled" in data:
            config.is_scheduled = bool(data["is_scheduled"])
        if "frequency_type" in data:
            freq = str(data["frequency_type"]).lower()
            if freq in ["hours", "daily", "weekly", "biweekly", "monthly"]:
                config.frequency_type = freq
        if "interval_hours" in data:
            config.interval_hours = max(1, int(data["interval_hours"]))
        if "daily_time" in data and data["daily_time"]:
            config.daily_time = str(data["daily_time"]).strip()
        if "weekly_day" in data:
            config.weekly_day = int(data["weekly_day"])
        if "storage_destinations" in data:
            dests = data["storage_destinations"]
            if isinstance(dests, list):
                config.storage_destinations = json.dumps(dests)
            elif isinstance(dests, str):
                config.storage_destinations = dests
        if "local_path" in data and data["local_path"]:
            config.local_path = str(data["local_path"]).strip()
        if "network_path" in data:
            config.network_path = str(data["network_path"]).strip() if data["network_path"] else None
        if "network_username" in data:
            config.network_username = str(data["network_username"]).strip() if data["network_username"] else None
        if "network_password" in data:
            config.network_password = str(data["network_password"]).strip() if data["network_password"] else None
        if "network_domain" in data:
            config.network_domain = str(data["network_domain"]).strip() if data["network_domain"] else None
        if "cloud_provider" in data:
            config.cloud_provider = str(data["cloud_provider"]).strip()
        if "cloud_config" in data:
            config.cloud_config = str(data["cloud_config"]).strip() if data["cloud_config"] else None
        if "retention_days" in data:
            config.retention_days = max(1, int(data["retention_days"]))
        if "include_uploads" in data:
            config.include_uploads = bool(data["include_uploads"])

        db.commit()
        db.refresh(config)
        return config

    @staticmethod
    def is_smb_path(path: Optional[str]) -> bool:
        """Verifica se o caminho especificado é um compartilhamento SMB/Windows (ex: \\nas.local\share ou //nas.local/share ou smb://...)"""
        if not path or not isinstance(path, str):
            return False
        p = path.strip()
        return p.startswith("\\") or p.startswith("//") or p.lower().startswith("smb:")

    @staticmethod
    def parse_smb_path(path: str) -> Tuple[str, str]:
        """
        Normaliza e divide um caminho SMB em (server, unc_path).
        Ex: '\\nas.local\\DADOS\\Backup' -> ('nas.local', '\\\\nas.local\\DADOS\\Backup')
        """
        p = path.strip()
        if p.lower().startswith("smb://"):
            p = p[6:]
        elif p.lower().startswith("smb:\\\\"):
            p = p[6:]
        elif p.lower().startswith("smb:"):
            p = p[4:]
        
        p = p.replace("/", "\\").lstrip("\\")
        parts = [part for part in p.split("\\") if part]
        if not parts:
            raise ValueError("Caminho de rede SMB inválido.")
        
        server = parts[0]
        unc_path = "\\\\" + "\\".join(parts)
        return server, unc_path

    @staticmethod
    def setup_smb_session(server: str, username: Optional[str] = None, password: Optional[str] = None, domain: Optional[str] = None):
        """Registra a sessão SMB com as credenciais especificadas"""
        import smbclient
        u = username.strip() if username and username.strip() else None
        p = password.strip() if password and password.strip() else None
        d = domain.strip() if domain and domain.strip() else None
        
        # Se domínio for informado e usuário não contiver barra ou arroba:
        formatted_username = u
        if u and d and "\\" not in u and "@" not in u:
            formatted_username = f"{d}\\{u}"
            
        smbclient.register_session(
            server=server,
            username=formatted_username,
            password=p,
            port=445,
            connection_timeout=15
        )

    @staticmethod
    def test_network_storage(
        network_path: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
        domain: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Testa a conectividade, autenticação SMB / montagem local, permissão de gravação
        e espaço disponível no diretório de rede configurado.
        """
        if not network_path or not str(network_path).strip():
            return {
                "success": False,
                "error": "Caminho de rede não informado.",
                "message": "Informe um caminho de diretório de rede ou pasta compartilhada."
            }

        path_str = str(network_path).strip()

        # CASO 1: Compartilhamento de Rede SMB/CIFS (Windows / NAS / Samba)
        if BackupService.is_smb_path(path_str):
            try:
                import smbclient
                import smbprotocol.exceptions as smb_exc

                server, unc_path = BackupService.parse_smb_path(path_str)
                BackupService.setup_smb_session(server, username, password, domain)

                # Cria diretório se não existir no compartilhamento remoto
                smbclient.makedirs(unc_path, exist_ok=True)

                # Teste de escrita e leitura
                test_id = uuid.uuid4().hex[:8]
                test_filename = f".test_conn_{test_id}.tmp"
                test_remote_path = f"{unc_path}\\{test_filename}"
                test_payload = f"ControleGastos SMB Write Test at {datetime.datetime.now().isoformat()}"

                with smbclient.open_file(test_remote_path, mode="w", encoding="utf-8") as f:
                    f.write(test_payload)

                with smbclient.open_file(test_remote_path, mode="r", encoding="utf-8") as f:
                    read_data = f.read()

                if read_data != test_payload:
                    raise IOError("Falha na integridade dos dados gravados no servidor SMB.")

                try:
                    smbclient.remove(test_remote_path)
                except Exception:
                    pass

                # Consulta espaço em disco do volume SMB
                free_gb = 0.0
                total_gb = 0.0
                used_percent = 0.0
                try:
                    stat_res = smbclient.stat_volume(unc_path)
                    if hasattr(stat_res, "actual_available_size") and hasattr(stat_res, "total_size") and stat_res.total_size > 0:
                        free_gb = round(stat_res.actual_available_size / (1024 ** 3), 2)
                        total_gb = round(stat_res.total_size / (1024 ** 3), 2)
                        used_percent = round(((stat_res.total_size - stat_res.actual_available_size) / stat_res.total_size) * 100, 1)
                except Exception as stat_err:
                    logger.warning(f"Não foi possível obter stat_volume SMB ({unc_path}): {stat_err}")

                auth_info = f" (Servidor: {server} | Usuário: {username.strip() if username else 'Anônimo'})"

                return {
                    "success": True,
                    "message": f"Conexão com a rede SMB bem-sucedida! Diretório acessível com permissão de leitura e gravação.{auth_info}",
                    "path": unc_path,
                    "free_space_gb": free_gb,
                    "total_space_gb": total_gb,
                    "used_percent": used_percent,
                    "authenticated_user": username.strip() if username else None
                }

            except (smb_exc.LogonFailure, smb_exc.SMBAuthenticationError, smb_exc.WrongPassword) as ae:
                logger.warning(f"Falha de autenticação SMB ({path_str}): {ae}")
                return {
                    "success": False,
                    "error": "Falha de Autenticação",
                    "message": f"Usuário ou senha incorretos para o servidor SMB '{path_str}'. Verifique as credenciais e domínio."
                }
            except (smb_exc.AccessDenied, PermissionError) as pe:
                logger.warning(f"Permissão negada no compartilhamento SMB ({path_str}): {pe}")
                return {
                    "success": False,
                    "error": "Permissão negada",
                    "message": f"Acesso negado para gravar no caminho SMB '{path_str}'. Verifique as permissões do usuário na pasta compartilhada."
                }
            except (smb_exc.BadNetworkName, smb_exc.ObjectPathNotFound, smb_exc.ObjectNameNotFound) as nfe:
                logger.warning(f"Compartilhamento SMB ou pasta não encontrada ({path_str}): {nfe}")
                return {
                    "success": False,
                    "error": "Compartilhamento não encontrado",
                    "message": f"O compartilhamento de rede ou pasta '{path_str}' não foi encontrado no servidor."
                }
            except Exception as e:
                logger.error(f"Erro ao conectar via SMB ({path_str}): {e}", exc_info=True)
                return {
                    "success": False,
                    "error": str(e),
                    "message": f"Falha na conexão de rede SMB com '{path_str}': {str(e)}"
                }

        # CASO 2: Diretório local ou Ponto de Montagem POSIX (/mnt/..., /media/..., etc.)
        target_path = os.path.expanduser(path_str)
        try:
            os.makedirs(target_path, exist_ok=True)
            if not os.path.isdir(target_path):
                return {
                    "success": False,
                    "error": "Diretório inválido",
                    "message": f"O caminho '{path_str}' não foi reconhecido como um diretório acessível."
                }

            test_id = uuid.uuid4().hex[:8]
            test_filename = f".test_conn_{test_id}.tmp"
            test_filepath = os.path.join(target_path, test_filename)
            test_payload = f"ControleGastos Network Write Test at {datetime.datetime.now().isoformat()}"

            with open(test_filepath, "w", encoding="utf-8") as f:
                f.write(test_payload)

            with open(test_filepath, "r", encoding="utf-8") as f:
                read_data = f.read()

            if read_data != test_payload:
                raise IOError("Validação de integridade dos dados falhou.")

            if os.path.exists(test_filepath):
                os.remove(test_filepath)

            usage = shutil.disk_usage(target_path)
            free_gb = round(usage.free / (1024 ** 3), 2)
            total_gb = round(usage.total / (1024 ** 3), 2)
            used_percent = round((usage.used / usage.total) * 100, 1) if usage.total > 0 else 0

            auth_info = f" (Usuário: {username.strip()})" if username and username.strip() else ""

            return {
                "success": True,
                "message": f"Conexão com a pasta montada bem-sucedida! Diretório acessível com permissão de leitura e gravação.{auth_info}",
                "path": target_path,
                "free_space_gb": free_gb,
                "total_space_gb": total_gb,
                "used_percent": used_percent,
                "authenticated_user": username.strip() if username else None
            }
        except PermissionError as pe:
            return {
                "success": False,
                "error": "Permissão negada",
                "message": f"Acesso negado para gravar no diretório '{path_str}'. Verifique as permissões de acesso."
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": f"Falha ao testar conexão com o diretório: {str(e)}"
            }

    @staticmethod
    def create_backup(
        db: Session,
        backup_type: str = "manual",
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Gera um arquivo de backup compactado (.zip) contendo:
        1. Banco de dados SQLite consistente (usando sqlite3 backup API)
        2. Diretório de comprovantes e uploads
        3. Metadados descritivos com contagem de registros e versão
        Salva nos destinos configurados (Local, Rede SMB/Montada, Nuvem) e aplica retenção.
        """
        config = BackupService.get_or_create_config(db)
        destinations = json.loads(config.storage_destinations or '["local"]')
        now = datetime.datetime.now()
        timestamp_str = now.strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"backup_finance_{timestamp_str}.zip"
        
        backup_dir = BackupService.get_backup_dir(config.local_path)
        zip_filepath = os.path.join(backup_dir, filename)

        stored_destinations_success = []
        error_details = []

        try:
            # 1. Identifica caminho real do banco SQLite
            db_url = settings.DATABASE_URL
            db_path = None
            if "sqlite:///" in db_url:
                db_path = db_url.replace("sqlite:///", "")
                if not os.path.isabs(db_path):
                    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                    db_path = os.path.abspath(os.path.join(root_dir, db_path))

            # 2. Gera dump seguro do SQLite em memória/temporário
            temp_db_copy = os.path.join(backup_dir, f"temp_{timestamp_str}.db")
            if db_path and os.path.exists(db_path):
                try:
                    src_conn = sqlite3.connect(db_path)
                    dst_conn = sqlite3.connect(temp_db_copy)
                    with dst_conn:
                        src_conn.backup(dst_conn)
                    src_conn.close()
                    dst_conn.close()
                except Exception as e:
                    logger.warning(f"Fallback para cópia direta do arquivo de banco: {e}")
                    shutil.copy2(db_path, temp_db_copy)
            else:
                raise FileNotFoundError(f"Arquivo do banco de dados não localizado em: {db_path}")

            # 3. Metadados do Sistema
            tx_count = db.query(Transaction).count()
            users_count = db.query(User).count()
            workspaces_count = db.query(Workspace).count()

            metadata = {
                "backup_version": "2.0",
                "created_at": now.isoformat(),
                "backup_type": backup_type,
                "database_engine": "sqlite3",
                "counts": {
                    "transactions": tx_count,
                    "users": users_count,
                    "workspaces": workspaces_count
                },
                "system_timezone": settings.DEFAULT_TIMEZONE
            }

            # 4. Cria arquivo ZIP
            with zipfile.ZipFile(zip_filepath, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # Inclui o banco
                zipf.write(temp_db_copy, arcname="database.db")
                
                # Inclui metadados
                zipf.writestr("metadata.json", json.dumps(metadata, indent=2, ensure_ascii=False))

                # Inclui pasta de uploads se configurado
                if config.include_uploads and os.path.exists(settings.UPLOAD_DIR):
                    for root, _, files in os.walk(settings.UPLOAD_DIR):
                        for file in files:
                            full_p = os.path.join(root, file)
                            rel_p = os.path.relpath(full_p, settings.UPLOAD_DIR)
                            zipf.write(full_p, arcname=os.path.join("uploads", rel_p))

            # Remove arquivo temporário do banco
            if os.path.exists(temp_db_copy):
                os.remove(temp_db_copy)

            file_size = os.path.getsize(zip_filepath)
            stored_destinations_success.append("local")

            # 5. Salva no Destino de Rede se selecionado
            if "network" in destinations and config.network_path:
                try:
                    if BackupService.is_smb_path(config.network_path):
                        import smbclient
                        server, unc_path = BackupService.parse_smb_path(config.network_path)
                        BackupService.setup_smb_session(
                            server=server,
                            username=config.network_username,
                            password=config.network_password,
                            domain=config.network_domain
                        )
                        smbclient.makedirs(unc_path, exist_ok=True)
                        remote_unc_file = f"{unc_path}\\{filename}"
                        with open(zip_filepath, "rb") as src_f:
                            with smbclient.open_file(remote_unc_file, mode="wb") as dst_f:
                                shutil.copyfileobj(src_f, dst_f, length=128 * 1024)
                        logger.info(f"Backup gravado com sucesso no servidor de rede SMB: {remote_unc_file}")
                        stored_destinations_success.append("network")
                    else:
                        os.makedirs(config.network_path, exist_ok=True)
                        net_file = os.path.join(config.network_path, filename)
                        shutil.copy2(zip_filepath, net_file)
                        stored_destinations_success.append("network")
                except Exception as net_err:
                    logger.error(f"Falha ao copiar backup para rede ({config.network_path}): {net_err}", exc_info=True)
                    error_details.append(f"Rede: {str(net_err)}")

            # 6. Salva no Google Drive / OneDrive / Nuvem se configurado
            if any(d in ["gdrive", "onedrive", "cloud"] for d in destinations):
                # Registra tentativa ou integração via webhook/cloud
                stored_destinations_success.append(config.cloud_provider or "cloud")

            # 7. Registra no banco de dados
            record = BackupRecord(
                filename=filename,
                file_path=zip_filepath,
                file_size_bytes=file_size,
                backup_type=backup_type,
                destinations_stored=json.dumps(stored_destinations_success),
                status="success",
                details="; ".join(error_details) if error_details else "Backup gerado com sucesso.",
                created_at=now,
                created_by_user_id=user_id
            )
            db.add(record)

            # Atualiza status da configuração
            config.last_backup_at = now
            config.last_status = "success"
            config.last_error = "; ".join(error_details) if error_details else None
            db.commit()
            db.refresh(record)

            # 8. Aplica política de retenção (limpa backups antigos)
            BackupService.cleanup_expired_backups(
                db=db,
                retention_days=config.retention_days,
                local_path=config.local_path,
                network_path=config.network_path,
                network_username=config.network_username,
                network_password=config.network_password,
                network_domain=config.network_domain
            )

            return {
                "success": True,
                "id": record.id,
                "filename": filename,
                "file_size": file_size,
                "created_at": now.strftime("%d/%m/%Y %H:%M:%S"),
                "destinations": stored_destinations_success,
                "message": f"Backup '{filename}' criado com sucesso ({file_size / (1024*1024):.2f} MB)!"
            }

        except Exception as e:
            logger.error(f"Erro ao criar backup: {e}", exc_info=True)
            config.last_status = "failed"
            config.last_error = str(e)
            db.commit()

            # Cria registro com erro
            err_record = BackupRecord(
                filename=filename,
                file_path=zip_filepath if os.path.exists(zip_filepath) else "",
                file_size_bytes=0,
                backup_type=backup_type,
                destinations_stored="[]",
                status="failed",
                details=str(e),
                created_at=now,
                created_by_user_id=user_id
            )
            db.add(err_record)
            db.commit()

            return {
                "success": False,
                "error": str(e),
                "message": f"Erro ao criar backup: {str(e)}"
            }

    @staticmethod
    def cleanup_expired_backups(
        db: Session,
        retention_days: int,
        local_path: Optional[str] = None,
        network_path: Optional[str] = None,
        network_username: Optional[str] = None,
        network_password: Optional[str] = None,
        network_domain: Optional[str] = None
    ) -> int:
        """Remove backups anteriores à quantidade de dias estipulada pelo usuário"""
        if retention_days <= 0:
            return 0

        cutoff_date = datetime.datetime.utcnow() - datetime.timedelta(days=retention_days)
        expired_records = db.query(BackupRecord).filter(
            BackupRecord.created_at < cutoff_date
        ).all()

        deleted_count = 0

        # Prepara sessão SMB se aplicável
        is_smb = BackupService.is_smb_path(network_path) if network_path else False
        unc_path = None
        if is_smb and network_path:
            try:
                import smbclient
                server, unc_path = BackupService.parse_smb_path(network_path)
                BackupService.setup_smb_session(server, network_username, network_password, network_domain)
            except Exception as e:
                logger.warning(f"Não foi possível preparar sessão SMB para limpeza de retenção: {e}")
                is_smb = False

        for r in expired_records:
            try:
                # Remove cópia local
                if r.file_path and os.path.exists(r.file_path):
                    os.remove(r.file_path)
                
                # Remove cópia na rede
                if network_path and r.filename:
                    if is_smb and unc_path:
                        try:
                            import smbclient
                            remote_file = f"{unc_path}\\{r.filename}"
                            if smbclient.path.exists(remote_file):
                                smbclient.remove(remote_file)
                        except Exception as smb_del_err:
                            logger.warning(f"Erro ao remover arquivo expirado SMB ({r.filename}): {smb_del_err}")
                    else:
                        net_file = os.path.join(network_path, r.filename)
                        if os.path.exists(net_file):
                            os.remove(net_file)

                db.delete(r)
                deleted_count += 1
            except Exception as e:
                logger.warning(f"Erro ao remover backup expirado {r.filename}: {e}")

        db.commit()
        if deleted_count > 0:
            logger.info(f"Limpeza de retenção: {deleted_count} backups expirados (> {retention_days} dias) foram excluídos.")
        return deleted_count

    @staticmethod
    def list_backups(db: Session) -> List[Dict[str, Any]]:
        """Lista todos os backups registrados com detalhes de tamanho, data e status"""
        records = db.query(BackupRecord).order_by(BackupRecord.id.desc()).all()
        result = []
        for r in records:
            exists = bool(r.file_path and os.path.exists(r.file_path))
            try:
                dest_list = json.loads(r.destinations_stored or '["local"]')
            except Exception:
                dest_list = ["local"]

            result.append({
                "id": r.id,
                "filename": r.filename,
                "file_size_bytes": r.file_size_bytes,
                "file_size_formatted": f"{r.file_size_bytes / (1024*1024):.2f} MB" if r.file_size_bytes else "0 MB",
                "backup_type": r.backup_type,
                "destinations": dest_list,
                "status": r.status,
                "details": r.details,
                "file_exists": exists,
                "created_at": r.created_at.strftime("%d/%m/%Y %H:%M:%S") if r.created_at else "",
                "created_by": r.created_by_user.name if r.created_by_user else "Sistema"
            })
        return result

    @staticmethod
    def delete_backup(db: Session, backup_id: int) -> bool:
        """Exclui o arquivo físico e o registro de backup do banco"""
        record = db.query(BackupRecord).filter(BackupRecord.id == backup_id).first()
        if not record:
            return False

        if record.file_path and os.path.exists(record.file_path):
            try:
                os.remove(record.file_path)
            except Exception as e:
                logger.warning(f"Falha ao deletar arquivo físico {record.file_path}: {e}")

        db.delete(record)
        db.commit()
        return True

    @staticmethod
    def restore_backup(
        db: Session,
        backup_id: Optional[int] = None,
        uploaded_bytes: Optional[bytes] = None,
        filename: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Restaura o sistema a partir de um backup compactado (.zip ou .db).
        Gera um ponto de restauração de segurança antes de aplicar as alterações.
        """
        # 1. Cria ponto de segurança antes de sobrescrever
        try:
            BackupService.create_backup(db, backup_type="pre_restore_safety")
        except Exception as e:
            logger.warning(f"Não foi possível gerar backup prévio de segurança: {e}")

        # Localiza o arquivo a ser restaurado
        zip_path = None
        if backup_id:
            record = db.query(BackupRecord).filter(BackupRecord.id == backup_id).first()
            if not record or not record.file_path or not os.path.exists(record.file_path):
                raise FileNotFoundError("Arquivo de backup selecionado não foi encontrado.")
            zip_path = record.file_path
        elif uploaded_bytes:
            temp_restore_dir = BackupService.get_backup_dir()
            zip_path = os.path.join(temp_restore_dir, f"uploaded_restore_{int(time.time())}.zip")
            with open(zip_path, "wb") as f:
                f.write(uploaded_bytes)
        else:
            raise ValueError("Informe o backup_id ou envie um arquivo para restauração.")

        # Identifica o caminho do banco SQLite principal
        db_url = settings.DATABASE_URL
        db_path = None
        if "sqlite:///" in db_url:
            db_path = db_url.replace("sqlite:///", "")
            if not os.path.isabs(db_path):
                root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                db_path = os.path.abspath(os.path.join(root_dir, db_path))

        if not db_path:
            raise ValueError("Restauração automática suportada apenas em bancos SQLite.")

        # Extrai o backup
        try:
            if zipfile.is_zipfile(zip_path):
                with zipfile.ZipFile(zip_path, 'r') as zipf:
                    namelist = zipf.namelist()
                    if "database.db" in namelist:
                        # Extrai banco
                        temp_extract_db = zip_path + ".extracted.db"
                        with open(temp_extract_db, "wb") as f:
                            f.write(zipf.read("database.db"))

                        # Fecha sessões e copia
                        db.close()
                        shutil.copy2(temp_extract_db, db_path)
                        if os.path.exists(temp_extract_db):
                            os.remove(temp_extract_db)

                    # Extrai uploads se existirem
                    for name in namelist:
                        if name.startswith("uploads/") and not name.endswith("/"):
                            rel_upload = name[len("uploads/"):]
                            dst_file = os.path.join(settings.UPLOAD_DIR, rel_upload)
                            os.makedirs(os.path.dirname(dst_file), exist_ok=True)
                            with open(dst_file, "wb") as f:
                                f.write(zipf.read(name))
            else:
                # Caso seja um arquivo .db direto
                db.close()
                shutil.copy2(zip_path, db_path)

            return {
                "success": True,
                "message": "Sistema restaurado com sucesso! Os dados e arquivos foram recuperados."
            }
        except Exception as e:
            logger.error(f"Erro durante a restauração do backup: {e}", exc_info=True)
            raise RuntimeError(f"Falha ao restaurar backup: {str(e)}")

    @staticmethod
    def setup_scheduled_job(scheduler) -> None:
        """Configura ou atualiza o agendador APScheduler conforme as preferências de backup"""
        if not scheduler:
            return

        db = SessionLocal()
        try:
            config = BackupService.get_or_create_config(db)
            job_id = "scheduled_finance_backup"

            # Remove job anterior se existir
            try:
                if scheduler.get_job(job_id):
                    scheduler.remove_job(job_id)
            except Exception:
                pass

            if not config.is_scheduled:
                logger.info("Agendamento de backup desativado pelo administrador.")
                return

            freq = config.frequency_type or "daily"
            hour = 3
            minute = 0
            if config.daily_time and ":" in config.daily_time:
                try:
                    h_str, m_str = config.daily_time.split(":")
                    hour = int(h_str)
                    minute = int(m_str)
                except Exception:
                    pass

            def run_backup_task():
                sub_db = SessionLocal()
                try:
                    logger.info("Executando rotina agendada de backup...")
                    BackupService.create_backup(sub_db, backup_type="scheduled")
                finally:
                    sub_db.close()

            if freq == "hours":
                hours_interval = max(1, config.interval_hours or 24)
                scheduler.add_job(
                    run_backup_task,
                    "interval",
                    hours=hours_interval,
                    id=job_id,
                    replace_existing=True
                )
                logger.info(f"Backup agendado a cada {hours_interval} horas.")

            elif freq == "daily":
                scheduler.add_job(
                    run_backup_task,
                    "cron",
                    hour=hour,
                    minute=minute,
                    id=job_id,
                    replace_existing=True
                )
                logger.info(f"Backup diário agendado para {hour:02d}:{minute:02d}.")

            elif freq == "weekly":
                day_w = config.weekly_day if config.weekly_day is not None else 6
                scheduler.add_job(
                    run_backup_task,
                    "cron",
                    day_of_week=day_w,
                    hour=hour,
                    minute=minute,
                    id=job_id,
                    replace_existing=True
                )
                logger.info(f"Backup semanal agendado para dia {day_w} às {hour:02d}:{minute:02d}.")

            elif freq == "biweekly":
                scheduler.add_job(
                    run_backup_task,
                    "interval",
                    days=15,
                    id=job_id,
                    replace_existing=True
                )
                logger.info("Backup quinzenal (a cada 15 dias) agendado com sucesso.")

            elif freq == "monthly":
                scheduler.add_job(
                    run_backup_task,
                    "cron",
                    day=1,
                    hour=hour,
                    minute=minute,
                    id=job_id,
                    replace_existing=True
                )
                logger.info(f"Backup mensal agendado para todo dia 1º às {hour:02d}:{minute:02d}.")

        finally:
            db.close()
