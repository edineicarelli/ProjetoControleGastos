import hashlib
import hmac
import secrets
import string
import time
import json
import base64
import logging
from typing import Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
from fastapi import Request, HTTPException, Depends, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User

logger = logging.getLogger(__name__)

# Chave secreta para assinatura dos tokens de sessão
SECRET_KEY = "controle_gastos_secure_session_key_secret_2026"
SESSION_COOKIE_NAME = "cg_session"
SESSION_EXPIRATION_DAYS = 7

class AuthService:
    @staticmethod
    def hash_password(password: str) -> str:
        """Gera hash PBKDF2-HMAC-SHA256 com salt aleatório seguro"""
        salt = secrets.token_hex(16)
        pwd_hash = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            100000
        ).hex()
        return f"{salt}${pwd_hash}"

    @staticmethod
    def verify_password(password: str, stored_hash: Optional[str]) -> bool:
        """Verifica se a senha fornecida corresponde ao hash armazenado"""
        if not stored_hash or "$" not in stored_hash:
            return False
        try:
            salt, hash_val = stored_hash.split("$", 1)
            new_hash = hashlib.pbkdf2_hmac(
                'sha256',
                password.encode('utf-8'),
                salt.encode('utf-8'),
                100000
            ).hex()
            return hmac.compare_digest(hash_val, new_hash)
        except Exception as e:
            logger.error(f"Erro ao verificar senha: {e}")
            return False

    @staticmethod
    def generate_session_token(user: User) -> str:
        """Gera um token de sessão assinado e seguro"""
        payload = {
            "uid": user.id,
            "usr": user.username or user.telegram_id,
            "role": user.system_role or "visualizador",
            "mcp": user.must_change_password,
            "exp": int(time.time()) + (SESSION_EXPIRATION_DAYS * 86400)
        }
        payload_bytes = json.dumps(payload, separators=(',', ':')).encode('utf-8')
        payload_b64 = base64.urlsafe_b64encode(payload_bytes).decode('utf-8').rstrip('=')
        
        signature = hmac.new(
            SECRET_KEY.encode('utf-8'),
            payload_b64.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        return f"{payload_b64}.{signature}"

    @staticmethod
    def decode_session_token(token: Optional[str]) -> Optional[Dict[str, Any]]:
        """Valida a assinatura do token e retorna os dados se válido"""
        if not token or "." not in token:
            return None
        try:
            payload_b64, signature = token.split(".", 1)
            expected_sig = hmac.new(
                SECRET_KEY.encode('utf-8'),
                payload_b64.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            if not hmac.compare_digest(signature, expected_sig):
                return None
            
            # Adiciona padding de base64 se necessário
            rem = len(payload_b64) % 4
            if rem > 0:
                payload_b64 += "=" * (4 - rem)
                
            payload_bytes = base64.urlsafe_b64decode(payload_b64.encode('utf-8'))
            payload = json.loads(payload_bytes.decode('utf-8'))
            
            # Checa expiração
            if payload.get("exp", 0) < int(time.time()):
                return None
                
            return payload
        except Exception as e:
            logger.debug(f"Falha ao decodificar token de sessão: {e}")
            return None

    @staticmethod
    def generate_temp_password(length: int = 8) -> str:
        """Gera uma senha temporária alfanumérica segura e legível"""
        chars = string.ascii_uppercase + string.digits + "!@#$"
        return "".join(secrets.choice(chars) for _ in range(length))

    @staticmethod
    async def send_temp_password_telegram(user: User, temp_password: str, db: Optional[Session] = None) -> Tuple[bool, str]:
        """Envia a senha temporária diretamente ao Telegram do usuário via HTTP API"""
        import httpx
        from app.config import settings

        token = settings.TELEGRAM_BOT_TOKEN
        if not token or token == "SEU_TELEGRAM_BOT_TOKEN_AQUI":
            logger.warning("TELEGRAM_BOT_TOKEN não configurado para envio de senha temporária.")
            return (False, "O Token do Bot do Telegram não foi configurado nas variáveis de ambiente.")

        chat_id = None
        # 1. Verifica se telegram_id do próprio usuário é numérico
        if user.telegram_id and user.telegram_id.isdigit():
            chat_id = int(user.telegram_id)

        # 2. Se não for numérico, tenta resolver a partir do banco de dados
        if not chat_id and db:
            import re
            user_phone_digits = re.sub(r'\D', '', user.phone or '')
            if len(user_phone_digits) in [12, 13] and user_phone_digits.startswith("55"):
                user_phone_digits = user_phone_digits[2:]

            # A: Busca por outro registro com o mesmo telefone e chat_id numérico
            if user_phone_digits:
                for other in db.query(User).filter(User.telegram_id.isnot(None)).all():
                    if other.telegram_id and other.telegram_id.isdigit():
                        other_phone = re.sub(r'\D', '', other.phone or '')
                        if len(other_phone) in [12, 13] and other_phone.startswith("55"):
                            other_phone = other_phone[2:]
                        if other_phone and other_phone == user_phone_digits:
                            chat_id = int(other.telegram_id)
                            break

            # B: Busca por username correspondente com chat_id numérico
            if not chat_id and user.username:
                for other in db.query(User).filter(User.telegram_id.isnot(None)).all():
                    if other.telegram_id and other.telegram_id.isdigit():
                        if other.username and other.username.lower() == user.username.lower():
                            chat_id = int(other.telegram_id)
                            break

            # C: Se for o admin do sistema, vincula ao primeiro administrador com chat_id numérico
            if not chat_id and (user.is_admin_default or user.system_role == "administrador" or user.username == "admin"):
                for other in db.query(User).filter(User.telegram_id.isnot(None)).all():
                    if other.telegram_id and other.telegram_id.isdigit() and other.system_role == "administrador":
                        chat_id = int(other.telegram_id)
                        break

        if not chat_id:
            logger.warning(f"Usuário {user.username} (ID {user.id}) não possui chat_id numérico no Telegram.")
            return (
                False, 
                f"O usuário '{user.name or user.username}' não possui um Chat ID do Telegram vinculado. Abra o Telegram e envie uma mensagem /start para o bot para vincular sua conta."
            )

        msg = (
            f"🔐 *RECUPERAÇÃO DE SENHA*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Olá, *{user.name or user.username}*!\n\n"
            f"Recebemos uma solicitação de redefinição de senha para o seu acesso ao *Sistema de Controle Financeiro*.\n\n"
            f"🔑 *Sua Senha Temporária:* `{temp_password}`\n\n"
            f"⚠️ *Importante:* Esta senha expira em 15 minutos e você deverá cadastrar uma nova senha logo após o login."
        )

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                url = f"https://api.telegram.org/bot{token}/sendMessage"
                payload = {
                    "chat_id": chat_id,
                    "text": msg,
                    "parse_mode": "Markdown"
                }
                res = await client.post(url, json=payload)
                res_data = res.json()

                if res.status_code == 200 and res_data.get("ok"):
                    logger.info(f"Senha temporária enviada com sucesso no Telegram para chat_id {chat_id}")
                    return (True, f"Senha temporária enviada no Telegram para {user.name} com sucesso!")
                else:
                    err_desc = res_data.get("description", "Erro desconhecido do Telegram")
                    logger.error(f"Erro na API do Telegram ao enviar senha temporária: {err_desc}")
                    return (False, f"Erro ao enviar no Telegram: {err_desc}. Inicie uma conversa com o bot no Telegram.")

        except Exception as e:
            logger.error(f"Exceção ao enviar mensagem no Telegram: {e}")
            return (False, f"Falha de comunicação com o Telegram: {str(e)}")

    @staticmethod
    def verify_telegram_auth(db: Session, telegram_id: str) -> Tuple[bool, Optional[User], str]:
        """
        Verifica o estado de autenticação de um usuário do Telegram.
        Retorna (is_authenticated, user, status_code_string)
        status_code_string pode ser:
          - 'ok': autenticado e ativo
          - 'unauthenticated': cadastrado mas precisa autenticar com senha
          - 'inactive': usuário inativado pelo administrador
          - 'unregistered': nenhum usuário vinculado a este telegram_id
        """
        user = db.query(User).filter(User.telegram_id == str(telegram_id)).first()
        if not user:
            return (False, None, "unregistered")
        
        if not user.is_active:
            return (False, user, "inactive")
        
        if not getattr(user, "is_telegram_authenticated", False):
            return (False, user, "unauthenticated")
            
        return (True, user, "ok")

    @staticmethod
    def authenticate_telegram_user(
        db: Session,
        telegram_id: str,
        password: str,
        username: Optional[str] = None,
        name: Optional[str] = None
    ) -> Tuple[bool, str, Optional[User]]:
        """
        Autentica o usuário no Telegram com a senha do sistema Web.
        """
        user = None
        clean_pwd = (password or "").strip()

        if not clean_pwd:
            return (False, "Informe a senha para autenticar.", None)

        if username:
            clean_user = username.strip().lstrip("@")
            user = db.query(User).filter(
                (User.username.ilike(clean_user)) | (User.phone == clean_user)
            ).first()
        else:
            user = db.query(User).filter(User.telegram_id == str(telegram_id)).first()
            if not user:
                # Se ainda não estiver vinculado e não passou username, busca usuário admin padrão ou único
                admins = db.query(User).filter(
                    (User.is_admin_default == True) | (User.username == "admin")
                ).all()
                if len(admins) == 1:
                    user = admins[0]

        if not user:
            return (False, "Usuário não encontrado. Envie `/login seu_usuario sua_senha` para vincular sua conta.", None)

        if not user.is_active:
            return (False, "⛔ Esta conta de usuário está inativa no sistema. Entre em contato com o administrador.", None)

        # Verifica senha
        pwd_match = False
        if user.password_hash and AuthService.verify_password(clean_pwd, user.password_hash):
            pwd_match = True
        elif user.temp_password and user.temp_password == clean_pwd:
            if not user.temp_password_expires_at or user.temp_password_expires_at > datetime.datetime.utcnow():
                pwd_match = True

        if not pwd_match:
            return (False, "❌ Senha incorreta. Digite a mesma senha utilizada no sistema Web.", None)

        # Atualiza vínculo com telegram_id
        if str(user.telegram_id) != str(telegram_id):
            # Se havia outro registro placeholder com esse telegram_id, ajusta
            other = db.query(User).filter(User.telegram_id == str(telegram_id)).first()
            if other and other.id != user.id:
                other.telegram_id = f"detached_{other.id}_{secrets.token_hex(4)}"
                other.is_telegram_authenticated = False
                db.flush()
            user.telegram_id = str(telegram_id)

        if name and (not user.name or user.name in ["Usuário", "Novo Usuário"]):
            user.name = name

        user.is_telegram_authenticated = True
        db.commit()
        db.refresh(user)

        # Inicializa workspaces se necessário
        from app.services.finance_service import FinanceService
        FinanceService.get_or_create_user(db, str(telegram_id), name=user.name, username=user.username)

        return (True, f"✅ Autenticação realizada com sucesso! Bem-vindo(a), *{user.name or user.username}*!", user)

    @staticmethod
    def logout_telegram_user(db: Session, telegram_id: str) -> bool:
        """Encerra a sessão do usuário no Telegram"""
        user = db.query(User).filter(User.telegram_id == str(telegram_id)).first()
        if user:
            user.is_telegram_authenticated = False
            db.commit()
            return True
        return False


def get_current_user_optional(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    """Obtém o usuário logado atual através do cookie de sessão, parâmetro de consulta ou fallback seguro"""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        payload = AuthService.decode_session_token(token)
        if payload:
            user_id = payload.get("uid")
            if user_id:
                user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
                if user:
                    return user
    
    # Suporte para parâmetro user_id (Telegram Mini App ou navegação direta)
    user_id_param = request.query_params.get("user_id")
    if user_id_param:
        user = db.query(User).filter(
            ((User.telegram_id == str(user_id_param)) | (User.id == int(user_id_param) if str(user_id_param).isdigit() else False)),
            User.is_active == True
        ).first()
        if user:
            return user

    return None



def get_current_user_required(request: Request, db: Session = Depends(get_db)) -> User:
    """Obriga que o usuário esteja autenticado. Se for rota web redireciona para /login, se API retorna 401"""
    user = get_current_user_optional(request, db)
    if not user:
        if request.url.path.startswith("/api/"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Sessão expirada ou não autenticado. Faça login novamente."
            )
        # Para rotas de páginas HTML
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            headers={"Location": f"/login?next={request.url.path}"}
        )
    return user


def require_role(allowed_roles: list):
    """Dependência para verificar permissão baseada em roles (RBAC)"""
    def role_checker(current_user: User = Depends(get_current_user_required)) -> User:
        user_role = (current_user.system_role or "visualizador").lower()
        if user_role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Acesso negado. Esta operação exige perfil ({', '.join(allowed_roles)}). Seu perfil atual é: {user_role}."
            )
        return current_user
    return role_checker


# Helpers de dependências prontas
require_admin = require_role(["administrador"])
require_editor = require_role(["administrador", "moderador"])
