import os
import subprocess
from typing import Dict, Any

__version__ = "1.5.1"
__release_date__ = "24/09/2026"
__app_name__ = "Controle Financeiro Inteligente"

def get_git_commit() -> str:
    """Obtém o hash curto do commit Git atual com fallback seguro"""
    env_commit = os.getenv("APP_COMMIT") or os.getenv("GIT_COMMIT")
    if env_commit:
        return env_commit[:7]
    try:
        git_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        commit = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=git_dir,
            stderr=subprocess.DEVNULL
        ).decode("utf-8").strip()
        if commit:
            return commit
    except Exception:
        pass
    return "2c0707d"

def get_version_info() -> Dict[str, Any]:
    """Retorna dicionário estruturado com as informações de versão do sistema"""
    commit = get_git_commit()
    return {
        "version": __version__,
        "version_tag": f"v{__version__}",
        "commit": commit,
        "release_date": __release_date__,
        "app_name": __app_name__,
        "full_label": f"v{__version__} ({commit})",
        "port": 8085,
        "environment": "production" if not os.getenv("DEBUG") else "development"
    }
