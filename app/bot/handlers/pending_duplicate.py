import time
import uuid
from typing import Dict, Any, Optional

# Armazena transações pendentes de confirmação de duplicidade
# Estrutura: {token: {"data": dict, "timestamp": float}}
_PENDING_DUPLICATES: Dict[str, Dict[str, Any]] = {}
TTL_SECONDS = 86400  # 24 horas

def _cleanup_expired():
    """Remove registros pendentes expirados"""
    now = time.time()
    expired_keys = [k for k, v in _PENDING_DUPLICATES.items() if now - v.get("timestamp", 0) > TTL_SECONDS]
    for k in expired_keys:
        _PENDING_DUPLICATES.pop(k, None)

def save_pending_duplicate(data: Dict[str, Any]) -> str:
    """Salva os dados de uma transação pendente e retorna um token único"""
    _cleanup_expired()
    token = uuid.uuid4().hex[:12]
    _PENDING_DUPLICATES[token] = {
        "data": data,
        "timestamp": time.time()
    }
    return token

def get_pending_duplicate(token: str) -> Optional[Dict[str, Any]]:
    """Recupera os dados de uma transação pendente pelo token"""
    _cleanup_expired()
    entry = _PENDING_DUPLICATES.get(token)
    if entry:
        return entry.get("data")
    return None

def pop_pending_duplicate(token: str) -> Optional[Dict[str, Any]]:
    """Recupera e remove os dados de uma transação pendente pelo token"""
    _cleanup_expired()
    entry = _PENDING_DUPLICATES.pop(token, None)
    if entry:
        return entry.get("data")
    return None

def delete_pending_duplicate(token: str):
    """Descarta uma transação pendente"""
    _PENDING_DUPLICATES.pop(token, None)
