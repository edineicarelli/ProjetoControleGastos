import os
import re
import logging
from typing import Dict, Any, Optional
import httpx
from app.config import settings

logger = logging.getLogger(__name__)

ENV_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

def mask_secret(secret: str, show_start: int = 6, show_end: int = 4) -> str:
    if not secret or secret in ("SEU_TELEGRAM_BOT_TOKEN_AQUI", "SUA_GEMINI_API_KEY_AQUI"):
        return ""
    if len(secret) <= (show_start + show_end):
        return secret[:2] + "****" + secret[-2:]
    return secret[:show_start] + "•" * 8 + secret[-show_end:]

def update_env_file(key_values: Dict[str, str]) -> bool:
    """Atualiza variáveis no arquivo .env mantendo os demais campos"""
    env_path = ENV_PATH
    lines = []
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    
    updated_keys = set()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            k, _ = stripped.split("=", 1)
            k = k.strip()
            if k in key_values:
                val = str(key_values[k]).replace('"', '\\"')
                new_lines.append(f'{k}="{val}"\n')
                updated_keys.add(k)
                continue
        new_lines.append(line)
        
    for k, v in key_values.items():
        if k not in updated_keys:
            val = str(v).replace('"', '\\"')
            new_lines.append(f'{k}="{val}"\n')
            
    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)
        
    return True

class ConfigService:

    @staticmethod
    async def test_telegram_token(token: str) -> Dict[str, Any]:
        """Testa se o token do Telegram é válido consultando getMe"""
        clean_token = token.strip() if token else ""
        if not clean_token or clean_token == "SEU_TELEGRAM_BOT_TOKEN_AQUI":
            return {"success": False, "message": "Token do Telegram não informado ou padrão."}
        
        url = f"https://api.telegram.org/bot{clean_token}/getMe"
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.get(url)
                data = resp.json()
                if data.get("ok"):
                    result = data.get("result", {})
                    return {
                        "success": True,
                        "bot_name": result.get("first_name", ""),
                        "bot_username": result.get("username", ""),
                        "can_join_groups": result.get("can_join_groups", True),
                        "message": f"Conectado com sucesso! Bot: @{result.get('username')} ({result.get('first_name')})"
                    }
                else:
                    return {
                        "success": False,
                        "message": f"Telegram retornou erro: {data.get('description', 'Token inválido')}"
                    }
            except Exception as e:
                return {"success": False, "message": f"Falha na conexão com o Telegram: {str(e)}"}

    @staticmethod
    async def test_gemini_key(api_key: str) -> Dict[str, Any]:
        """Testa se a API Key do Google Gemini é válida consultando a lista de modelos"""
        clean_key = api_key.strip() if api_key else ""
        if not clean_key or clean_key == "SUA_GEMINI_API_KEY_AQUI":
            return {"success": False, "message": "Chave do Google Gemini não informada ou padrão."}
        
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={clean_key}"
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    models = [
                        m.get("name", "").replace("models/", "")
                        for m in data.get("models", [])
                        if "generateContent" in m.get("supportedGenerationMethods", [])
                    ]
                    return {
                        "success": True,
                        "models_count": len(models),
                        "sample_models": models[:4],
                        "message": f"Chave Gemini válida! {len(models)} modelos de IA disponíveis."
                    }
                else:
                    err_json = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                    err_msg = err_json.get("error", {}).get("message", f"HTTP {resp.status_code}")
                    return {
                        "success": False,
                        "message": f"Google Gemini retornou erro: {err_msg}"
                    }
            except Exception as e:
                return {"success": False, "message": f"Falha na conexão com Google Gemini: {str(e)}"}

    @staticmethod
    def get_settings_status() -> Dict[str, Any]:
        """Retorna os valores atuais dos tokens e o status de configuração"""
        has_telegram = bool(settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_BOT_TOKEN != "SEU_TELEGRAM_BOT_TOKEN_AQUI")
        has_gemini = bool(settings.GEMINI_API_KEY and settings.GEMINI_API_KEY != "SUA_GEMINI_API_KEY_AQUI")
        
        return {
            "telegram_token_raw": settings.TELEGRAM_BOT_TOKEN if settings.TELEGRAM_BOT_TOKEN != "SEU_TELEGRAM_BOT_TOKEN_AQUI" else "",
            "telegram_token_masked": mask_secret(settings.TELEGRAM_BOT_TOKEN, 8, 4),
            "has_telegram": has_telegram,
            "gemini_key_raw": settings.GEMINI_API_KEY if settings.GEMINI_API_KEY != "SUA_GEMINI_API_KEY_AQUI" else "",
            "gemini_key_masked": mask_secret(settings.GEMINI_API_KEY, 6, 4),
            "has_gemini": has_gemini
        }

    @staticmethod
    async def save_tokens(telegram_token: Optional[str], gemini_key: Optional[str]) -> Dict[str, Any]:
        """Atualiza os tokens no .env, nas configurações em memória e reinicia os serviços necessários"""
        updates = {}
        if telegram_token is not None:
            clean_tg = telegram_token.strip()
            updates["TELEGRAM_BOT_TOKEN"] = clean_tg
            settings.TELEGRAM_BOT_TOKEN = clean_tg
            
        if gemini_key is not None:
            clean_gm = gemini_key.strip()
            updates["GEMINI_API_KEY"] = clean_gm
            settings.GEMINI_API_KEY = clean_gm
            
        # Grava no arquivo .env
        update_env_file(updates)
        
        # Reinicia o Bot do Telegram se aplicável
        bot_restart_msg = ""
        try:
            from app.main import restart_telegram_bot
            restarted, msg = await restart_telegram_bot()
            bot_restart_msg = msg
        except Exception as e:
            logger.warning(f"Aviso ao reiniciar bot: {e}")
            bot_restart_msg = f"Configurações gravadas com sucesso. (Reinício: {e})"
            
        return {
            "success": True,
            "message": "Configurações de tokens salvas com sucesso!",
            "bot_status": bot_restart_msg,
            "status": ConfigService.get_settings_status()
        }
