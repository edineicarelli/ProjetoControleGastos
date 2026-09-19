import os
import json
import asyncio
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from fastapi import APIRouter, Request, Depends, Query, HTTPException, WebSocket, WebSocketDisconnect, UploadFile, File, Form, status
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, Workspace, WorkspaceMember, Goal, Reminder, ShoppingList, Category, Transaction, TransactionItem
from app.services.finance_service import FinanceService
from app.services.ai_service import AIService
from app.services.reminder_service import ReminderService
from app.services.vehicle_service import VehicleService
from app.services.shopping_service import ShoppingService
from app.services.account_service import AccountService
from app.services.user_service import UserService
from app.services.auth_service import (
    AuthService,
    get_current_user_optional,
    get_current_user_required,
    require_admin,
    require_editor,
    SESSION_COOKIE_NAME
)
from app.services.export_service import ExportService
from app.services.market_analytics_service import MarketAnalyticsService
from app.services.event_bus import event_bus

from app.utils import format_currency_br, format_number_br
from app.version import get_version_info

router = APIRouter()

templates_dir = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=templates_dir)
templates.env.filters["currency_br"] = format_currency_br
templates.env.filters["number_br"] = format_number_br
templates.env.globals["app_version"] = get_version_info()["version"]
templates.env.globals["app_commit"] = get_version_info()["commit"]
templates.env.globals["app_release_date"] = get_version_info()["release_date"]
templates.env.globals["version_info"] = get_version_info()

@router.get("/api/version")
async def api_get_version():
    """Retorna as informações de versão do sistema e commit atual"""
    return JSONResponse(content=get_version_info())

# =========================================================================
# ROTAS DE AUTENTICAÇÃO, LOGIN E RECUPERAÇÃO DE SENHA
# =========================================================================

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, db: Session = Depends(get_db)):
    """Página de Login com background animado e opções de recuperação"""
    user = get_current_user_optional(request, db)
    if user:
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse(request=request, name="login.html")

@router.get("/logout")
@router.post("/api/auth/logout")
async def api_logout():
    """Encerra a sessão e redireciona para a tela de login"""
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")
    return response

@router.post("/api/auth/login")
async def api_login(request: Request, db: Session = Depends(get_db)):
    """Valida credenciais (usuário do Telegram, ID ou telefone + senha) e cria sessão segura"""
    from datetime import datetime
    data = await request.json()
    username = data.get("username", "").strip()
    password = data.get("password", "")
    remember_me = bool(data.get("remember_me") or data.get("rememberPassword"))

    if not username or not password:
        raise HTTPException(status_code=400, detail="Informe o usuário do Telegram e a senha.")

    clean_user = username.lstrip("@").lower()
    user = db.query(User).filter(
        (User.username.ilike(clean_user)) | 
        (User.phone == username) | 
        (User.telegram_id == username)
    ).first()

    if not user:
        raise HTTPException(status_code=400, detail="Usuário não encontrado. Verifique seu login ou utilize o comando /senha no Telegram.")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Usuário inativo. Entre em contato com o administrador.")

    # Verifica senha normal ou senha temporária válida
    pwd_valid = False
    used_temp_pwd = False

    if user.password_hash and AuthService.verify_password(password, user.password_hash):
        pwd_valid = True
    elif user.temp_password and user.temp_password == password:
        if not user.temp_password_expires_at or user.temp_password_expires_at > datetime.utcnow():
            pwd_valid = True
            used_temp_pwd = True

    if not pwd_valid:
        raise HTTPException(status_code=400, detail="Senha incorreta. Caso tenha esquecido, clique em 'Esqueci a senha' para receber uma senha temporária no Telegram.")

    must_change = bool(user.must_change_password or used_temp_pwd)

    # Duração da sessão: 30 dias se salvar/lembrar, ou 30 minutos (1800s) por padrão
    cookie_max_age = (30 * 86400) if remember_me else (30 * 60)
    token = AuthService.generate_session_token(user, expiration_seconds=cookie_max_age)

    response = JSONResponse({
        "success": True,
        "user_id": user.id,
        "username": user.username or user.telegram_id,
        "name": user.name or user.username,
        "system_role": user.system_role or "visualizador",
        "must_change_password": must_change,
        "redirect_url": "/dashboard"
    })
    
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=cookie_max_age,
        samesite="lax",
        path="/"
    )
    return response

@router.post("/api/auth/forgot-password")
async def api_forgot_password(request: Request, db: Session = Depends(get_db)):
    """Gera senha temporária e envia diretamente no chat do Telegram do usuário"""
    from datetime import datetime, timedelta

    data = await request.json()
    username = (data.get("username") or data.get("identifier") or "").strip()
    phone = (data.get("phone") or "").strip()

    if not username and not phone:
        raise HTTPException(status_code=400, detail="Informe seu usuário do Telegram ou ID para recuperação.")

    clean_user = username.lstrip("@").lower() if username else ""
    user = db.query(User).filter(
        (User.username.ilike(clean_user) if clean_user else False) | 
        (User.telegram_id == username if username else False) |
        (User.phone == (phone or username))
    ).first()

    if not user:
        raise HTTPException(
            status_code=404, 
            detail="Usuário não encontrado. Caso ainda não tenha iniciado conversa com o bot no Telegram, envie uma mensagem /start para vincular sua conta."
        )

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Usuário inativo. Entre em contato com o administrador.")

    # Gera senha temporária de 8 caracteres
    temp_pwd = AuthService.generate_temp_password(8)
    user.temp_password = temp_pwd
    user.temp_password_expires_at = datetime.utcnow() + timedelta(minutes=15)
    user.password_hash = AuthService.hash_password(temp_pwd)
    user.must_change_password = True
    db.commit()

    success, msg = await AuthService.send_temp_password_telegram(user, temp_pwd, db=db)
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    
    return {
        "success": True,
        "message": f"Senha temporária enviada com sucesso no Telegram para @{user.username or user.telegram_id}! Utilize-a para acessar e definir sua nova senha."
    }

@router.post("/api/auth/change-password")
async def api_change_password(request: Request, db: Session = Depends(get_db)):
    """Altera a senha do usuário e conclui a exigência de primeiro acesso"""
    data = await request.json()
    user_id = data.get("user_id")
    new_password = data.get("new_password")
    
    if not user_id or not new_password:
        raise HTTPException(status_code=400, detail="Dados incompletos.")

    try:
        UserService.change_user_password(db, int(user_id), new_password)
        user = db.query(User).filter(User.id == int(user_id)).first()
        token = AuthService.generate_session_token(user)

        response = JSONResponse({"success": True, "message": "Senha atualizada com sucesso!"})
        response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=token,
            httponly=True,
            max_age=7 * 86400,
            samesite="lax",
            path="/"
        )
        return response
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/join/{invite_code}")
@router.get("/entrar/{invite_code}")
async def web_join_workspace(invite_code: str, db: Session = Depends(get_db)):
    """Rota direta para ingressar no workspace via link web"""
    ws = db.query(Workspace).filter(Workspace.invite_code == invite_code.strip().upper()).first()
    if not ws:
        raise HTTPException(status_code=404, detail="Código de convite não encontrado.")
    return RedirectResponse(url=f"https://t.me/carellifinanceiro_bot?start=convite_{ws.invite_code}")

# =========================================================================
# DASHBOARD PRINCIPAL (PROTEGIDA POR AUTENTICAÇÃO)
# =========================================================================

@router.get("/", response_class=HTMLResponse)
@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(
    request: Request,
    user_id: Optional[str] = Query(None),
    workspace_id: Optional[int] = Query(None),
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None),
    db: Session = Depends(get_db)
):
    """Página principal do Dashboard Financeiro com verificação de login e RBAC"""
    # 1. Identifica estritamente o usuário logado via sessão
    logged_user = get_current_user_optional(request, db)

    # Se não houver nenhum usuário autenticado, redireciona para a tela de login
    if not logged_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    user = logged_user
    
    # Determina workspace
    if workspace_id:
        current_workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    else:
        current_workspace = user.current_workspace

    if not current_workspace:
        current_workspace = db.query(Workspace).order_by(Workspace.id.desc()).first()

    # Se ainda não existir nenhum workspace, cria um padrão
    if not current_workspace:
        user, current_workspace = FinanceService.get_or_create_user(db, telegram_id=user.telegram_id or "admin_system", name=user.name or "Principal")

    # Lista todos os workspaces para fácil alternância no painel
    user_workspaces = db.query(Workspace).order_by(Workspace.id.desc()).all()

    clean_year = int(year) if (year is not None and str(year).isdigit()) else None
    clean_month = int(month) if (month is not None and str(month).isdigit()) else None

    accounts = AccountService.get_accounts(db, current_workspace.id)
    summary = FinanceService.get_monthly_summary(db, current_workspace.id, year=clean_year, month=clean_month)
    expenses_by_account = FinanceService.get_expenses_by_account_summary(db, current_workspace.id, year=clean_year, month=clean_month)
    monthly_transactions = summary["monthly_transactions"]
    workspace_members = UserService.get_workspace_members(db, current_workspace.id)
    all_system_users = UserService.get_all_users(db)

    goals = db.query(Goal).filter(Goal.workspace_id == current_workspace.id).all()
    reminders = ReminderService.get_upcoming_reminders(db, current_workspace.id)
    vehicle = VehicleService.get_or_create_vehicle(db, current_workspace.id)
    vehicle_summary = VehicleService.get_vehicle_summary(db, vehicle.id)
    shopping_list = ShoppingService.get_or_create_active_list(db, current_workspace.id)

    bot_username = "carellifinanceiro_bot"
    invite_link = f"https://t.me/{bot_username}?start=convite_{current_workspace.invite_code}"

    categories = db.query(Category).filter(Category.workspace_id == current_workspace.id).order_by(Category.name.asc()).all()

    # Informações de RBAC
    user_role = (user.system_role or "visualizador").lower()
    is_admin = (user_role == "administrador")
    is_moderator = (user_role == "moderador")
    is_viewer = (user_role == "visualizador")

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "user": user,
            "logged_user": user,
            "user_role": user_role,
            "is_admin": is_admin,
            "is_moderator": is_moderator,
            "is_viewer": is_viewer,
            "current_workspace": current_workspace,
            "user_workspaces": user_workspaces,
            "workspace_members": workspace_members,
            "all_system_users": all_system_users,
            "accounts": accounts,
            "categories": categories,
            "summary": summary,
            "expenses_by_account": expenses_by_account,
            "all_transactions": monthly_transactions,
            "transactions": monthly_transactions,
            "selected_year": summary["year"],
            "selected_month": summary["month"],
            "goals": goals,
            "reminders": reminders,
            "vehicle": vehicle,
            "vehicle_summary": vehicle_summary,
            "shopping_list": shopping_list,
            "bot_username": bot_username,
            "invite_link": invite_link
        }
    )


@router.get("/export/excel")
async def export_excel_route(
    workspace_id: int,
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    account_id: Optional[int] = Query(None),
    tx_type: Optional[str] = Query("all"),
    category_id: Optional[int] = Query(None),
    top_expenses_limit: int = Query(5),
    include_comparison: bool = Query(False),
    include_metrics: bool = Query(True),
    db: Session = Depends(get_db)
):
    filepath = ExportService.export_to_excel(
        db=db,
        workspace_id=workspace_id,
        start_date=start_date,
        end_date=end_date,
        account_id=account_id,
        tx_type=tx_type,
        category_id=category_id,
        top_expenses_limit=top_expenses_limit,
        include_comparison=include_comparison,
        include_metrics=include_metrics
    )
    return FileResponse(filepath, filename=os.path.basename(filepath), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@router.get("/export/pdf")
async def export_pdf_route(
    workspace_id: int,
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    account_id: Optional[int] = Query(None),
    tx_type: Optional[str] = Query("all"),
    category_id: Optional[int] = Query(None),
    top_expenses_limit: int = Query(5),
    include_comparison: bool = Query(False),
    include_metrics: bool = Query(True),
    db: Session = Depends(get_db)
):
    filepath = ExportService.export_to_pdf(
        db=db,
        workspace_id=workspace_id,
        start_date=start_date,
        end_date=end_date,
        account_id=account_id,
        tx_type=tx_type,
        category_id=category_id,
        top_expenses_limit=top_expenses_limit,
        include_comparison=include_comparison,
        include_metrics=include_metrics
    )
    return FileResponse(filepath, filename=os.path.basename(filepath), media_type="application/pdf")

from pydantic import BaseModel
from typing import List, Optional

class WorkspaceCreateRequest(BaseModel):
    name: str
    type: str = "personal"
    user_id: Optional[int] = None

class WorkspaceUpdateRequest(BaseModel):
    name: str
    type: Optional[str] = None

class AccountCreateRequest(BaseModel):
    workspace_id: Optional[int] = None
    name: str
    type: str = "checking"
    initial_balance: float = 0.0
    icon: str = "🏦"
    color: str = "#6366f1"

class AccountUpdateRequest(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    initial_balance: Optional[float] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    is_active: Optional[bool] = None

class AccountTransferRequest(BaseModel):
    workspace_id: int
    from_account_id: int
    to_account_id: int
    amount: float
    description: Optional[str] = None
    date: Optional[str] = None
    user_id: Optional[int] = None

class UserAddRequest(BaseModel):
    workspace_id: int
    name: str
    telegram_id: Optional[str] = None
    username: Optional[str] = None
    role: str = "member"
    is_active: bool = True

class UserUpdateRequest(BaseModel):
    name: Optional[str] = None
    telegram_id: Optional[str] = None
    username: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None

class TransactionItemPayload(BaseModel):
    name: str
    quantity: float = 1.0
    unit: str = "un"
    unit_price: float = 0.0
    total_price: float = 0.0
    category: Optional[str] = "Geral"

class TransactionCreateRequest(BaseModel):
    workspace_id: int
    user_id: Optional[int] = None
    type: str = "expense"
    amount: float
    description: str
    category_name: Optional[str] = "Outros"
    payment_method: Optional[str] = "Outro"
    account_id: Optional[int] = None
    date: Optional[str] = None
    receipt_url: Optional[str] = None
    include_items: bool = True
    items: Optional[List[TransactionItemPayload]] = None

class TransactionUpdateRequest(BaseModel):
    transaction_date: Optional[str] = None  # YYYY-MM-DD
    description: Optional[str] = None
    amount: Optional[float] = None
    type: Optional[str] = None
    category_name: Optional[str] = None
    account_id: Optional[int] = None
    payment_method: Optional[str] = None
    notes: Optional[str] = None

class ReminderCreateRequest(BaseModel):
    workspace_id: int
    title: str
    amount: float = 0.0
    due_date: str  # YYYY-MM-DD
    type: str = "to_pay"  # 'to_pay' ou 'to_receive'
    recurrence: str = "none"  # 'none', 'monthly', 'weekly', 'yearly'
    reminder_hours_before: int = 24

class ReminderUpdateRequest(BaseModel):
    title: Optional[str] = None
    amount: Optional[float] = None
    due_date: Optional[str] = None  # YYYY-MM-DD
    type: Optional[str] = None
    recurrence: Optional[str] = None
    reminder_hours_before: Optional[int] = None
    status: Optional[str] = None

class BatchDeleteTransactionsRequest(BaseModel):
    transaction_ids: List[int]

class UpdateTransactionItemsRequest(BaseModel):
    items: List[TransactionItemPayload]

class AddShoppingItemRequest(BaseModel):
    workspace_id: int
    name: str
    quantity: Optional[float] = 1.0
    unit: Optional[str] = "un"
    estimated_price: Optional[float] = 0.0
    category: Optional[str] = "Geral"



# APIs para Perfis / Workspaces
@router.post("/api/workspaces")
async def api_create_workspace(payload: WorkspaceCreateRequest, db: Session = Depends(get_db)):
    from app.services.workspace_service import WorkspaceService
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="Nome do perfil/conta é obrigatório")
    
    user = None
    if payload.user_id:
        user = db.query(User).filter(User.id == payload.user_id).first()
    if not user:
        user = db.query(User).order_by(User.id.desc()).first()
    if not user:
        user, _ = FinanceService.get_or_create_user(db, telegram_id="demo_user", name="Demonstração")

    ws = WorkspaceService.create_workspace(
        db=db,
        user_id=user.id,
        name=payload.name,
        ws_type=payload.type or "personal"
    )
    return {"success": True, "workspace_id": ws.id, "name": ws.name}

@router.put("/api/workspaces/{workspace_id}")
async def api_update_workspace(workspace_id: int, payload: WorkspaceUpdateRequest, db: Session = Depends(get_db)):
    from app.services.workspace_service import WorkspaceService
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="Nome do perfil/conta é obrigatório")
    ws = WorkspaceService.update_workspace(
        db=db,
        workspace_id=workspace_id,
        name=payload.name,
        ws_type=payload.type
    )
    if not ws:
        raise HTTPException(status_code=404, detail="Perfil não encontrado")
    return {"success": True, "workspace_id": ws.id, "name": ws.name}

@router.delete("/api/workspaces/{workspace_id}")
async def api_delete_workspace(workspace_id: int, db: Session = Depends(get_db)):
    from app.services.workspace_service import WorkspaceService
    try:
        success = WorkspaceService.delete_workspace(db, workspace_id)
        if not success:
            raise HTTPException(status_code=404, detail="Perfil não encontrado")
        return {"success": True}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

class SystemUserCreateRequest(BaseModel):
    name: str
    username: str
    phone: str
    system_role: str = "visualizador"
    initial_password: Optional[str] = None
    telegram_id: Optional[str] = None
    workspace_id: Optional[int] = None

class SystemUserUpdateRequest(BaseModel):
    name: Optional[str] = None
    username: Optional[str] = None
    phone: Optional[str] = None
    system_role: Optional[str] = None
    telegram_id: Optional[str] = None
    is_active: Optional[bool] = None
    new_password: Optional[str] = None

# =========================================================================
# APIs de Administração de Usuários do Sistema (Exclusivo Administrador)
# =========================================================================

@router.get("/api/admin/users")
async def api_admin_get_users(
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    """Lista todos os usuários do sistema com suas permissões (somente admin)"""
    return UserService.get_all_users(db)

@router.post("/api/admin/users")
async def api_admin_create_user(
    payload: SystemUserCreateRequest,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    """Cria um novo usuário no sistema com role e telefone obrigatório (somente admin)"""
    try:
        res = UserService.create_system_user(
            db=db,
            name=payload.name,
            username=payload.username,
            phone=payload.phone,
            system_role=payload.system_role,
            initial_password=payload.initial_password,
            telegram_id=payload.telegram_id,
            workspace_id=payload.workspace_id
        )
        return res
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.put("/api/admin/users/{user_id}")
async def api_admin_update_user(
    user_id: int,
    payload: SystemUserUpdateRequest,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    """Atualiza dados, permissões e status de um usuário (somente admin)"""
    try:
        res = UserService.update_system_user(
            db=db,
            user_id=user_id,
            name=payload.name,
            username=payload.username,
            phone=payload.phone,
            system_role=payload.system_role,
            telegram_id=payload.telegram_id,
            is_active=payload.is_active,
            new_password=payload.new_password
        )
        return res
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/api/admin/users/{user_id}/toggle-status")
async def api_admin_toggle_user_status(
    user_id: int,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    """Inativa ou ativa um usuário com proteção para o admin padrão (somente admin)"""
    try:
        res = UserService.toggle_user_status(db, user_id)
        return res
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

# APIs para Gestão de Usuários & Membros do Workspace
@router.post("/api/users")
async def api_add_user(payload: UserAddRequest, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    from app.services.user_service import UserService
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="Nome do usuário é obrigatório")
    
    res = UserService.add_user_to_workspace(
        db=db,
        workspace_id=payload.workspace_id,
        name=payload.name,
        telegram_id=payload.telegram_id,
        username=payload.username,
        role=payload.role or "member",
        is_active=payload.is_active
    )
    return res

@router.put("/api/users/{user_id}")
async def api_update_user(
    user_id: int,
    payload: UserUpdateRequest,
    workspace_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    from app.services.user_service import UserService
    ws_id = workspace_id or current_user.current_workspace_id or 1
    res = UserService.update_user_member(
        db=db,
        workspace_id=ws_id,
        user_id=user_id,
        name=payload.name,
        username=payload.username,
        telegram_id=payload.telegram_id,
        role=payload.role,
        is_active=payload.is_active
    )
    if not res:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    return res

@router.post("/api/users/{user_id}/toggle-active")
async def api_toggle_user_active(
    user_id: int,
    workspace_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    try:
        res = UserService.toggle_user_status(db, user_id)
        if workspace_id:
            try:
                from app.services.event_bus import event_bus
                event_bus.notify_workspace_update(workspace_id)
            except Exception:
                pass
        return res
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/api/workspaces/{workspace_id}/members/{user_id}")
async def api_remove_workspace_member(workspace_id: int, user_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    from app.services.user_service import UserService
    try:
        success = UserService.remove_user_from_workspace(db, workspace_id, user_id)
        if not success:
            raise HTTPException(status_code=404, detail="Membro não encontrado neste perfil")
        return {"success": True}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

# =========================================================================
# ROTAS DE GESTÃO DE BACKUP E SEGURANÇA (EXCLUSIVO ADMINISTRADOR)
# =========================================================================

@router.get("/api/backup/config")
async def api_get_backup_config(
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    """Retorna as configurações atuais de backup e agendamento"""
    from app.services.backup_service import BackupService
    config = BackupService.get_or_create_config(db)
    try:
        dest_list = json.loads(config.storage_destinations or '["local"]')
    except Exception:
        dest_list = ["local"]

    return {
        "success": True,
        "is_scheduled": bool(config.is_scheduled),
        "frequency_type": config.frequency_type or "daily",
        "interval_hours": config.interval_hours or 24,
        "daily_time": config.daily_time or "03:00",
        "weekly_day": config.weekly_day if config.weekly_day is not None else 6,
        "storage_destinations": dest_list,
        "local_path": config.local_path or "",
        "network_path": config.network_path or "",
        "network_username": config.network_username or "",
        "network_password": config.network_password or "",
        "network_domain": config.network_domain or "",
        "cloud_provider": config.cloud_provider or "gdrive",
        "cloud_config": config.cloud_config or "",
        "retention_days": config.retention_days or 30,
        "include_uploads": bool(config.include_uploads),
        "last_backup_at": config.last_backup_at.strftime("%d/%m/%Y %H:%M:%S") if config.last_backup_at else None,
        "last_status": config.last_status or "ready",
        "last_error": config.last_error
    }

@router.post("/api/backup/config")
async def api_update_backup_config(
    request: Request,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    """Salva novas configurações de backup e reconfigura o agendador APScheduler"""
    from app.services.backup_service import BackupService
    from app.main import scheduler
    data = await request.json()
    config = BackupService.update_config(db, data)
    
    try:
        BackupService.setup_scheduled_job(scheduler)
    except Exception as e:
        logger.warning(f"Erro ao atualizar agendador: {e}")

    return {"success": True, "message": "Configurações de backup salvas com sucesso!"}

@router.post("/api/backup/test-network")
async def api_test_backup_network(
    request: Request,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    """Testa a conectividade, permissão de gravação e integridade com o destino de rede"""
    from app.services.backup_service import BackupService
    data = await request.json()
    network_path = data.get("network_path")
    username = data.get("network_username")
    password = data.get("network_password")
    domain = data.get("network_domain")

    result = BackupService.test_network_storage(
        network_path=network_path,
        username=username,
        password=password,
        domain=domain
    )
    return result

@router.get("/api/backup/list")
async def api_list_backups(
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    """Lista todos os backups existentes no sistema"""
    from app.services.backup_service import BackupService
    backups = BackupService.list_backups(db)
    return {"success": True, "backups": backups}

@router.post("/api/backup/create")
async def api_create_backup_now(
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    """Executa imediatamente a rotina de criação de backup manual"""
    from app.services.backup_service import BackupService
    result = BackupService.create_backup(db, backup_type="manual", user_id=admin_user.id)
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("message", "Falha ao criar backup."))
    return result

@router.get("/api/backup/download/{backup_id}")
async def api_download_backup(
    backup_id: int,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    """Faz o download seguro do arquivo de backup (.zip)"""
    from app.models import BackupRecord
    record = db.query(BackupRecord).filter(BackupRecord.id == backup_id).first()
    if not record or not record.file_path or not os.path.exists(record.file_path):
        raise HTTPException(status_code=404, detail="Arquivo de backup não encontrado no servidor.")

    return FileResponse(
        path=record.file_path,
        filename=record.filename,
        media_type="application/zip"
    )

@router.delete("/api/backup/{backup_id}")
async def api_delete_backup(
    backup_id: int,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    """Exclui o arquivo de backup e seu registro"""
    from app.services.backup_service import BackupService
    success = BackupService.delete_backup(db, backup_id)
    if not success:
        raise HTTPException(status_code=404, detail="Backup não encontrado.")
    return {"success": True, "message": "Backup excluído com sucesso."}

@router.post("/api/backup/restore/{backup_id}")
async def api_restore_backup_by_id(
    backup_id: int,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    """Restaura o sistema a partir de um backup registrado"""
    from app.services.backup_service import BackupService
    try:
        res = BackupService.restore_backup(db, backup_id=backup_id)
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/backup/upload-restore")
async def api_upload_restore_backup(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    """Recebe um arquivo de backup (.zip ou .db) e restaura no sistema"""
    from app.services.backup_service import BackupService
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Arquivo vazio.")
    try:
        res = BackupService.restore_backup(db, uploaded_bytes=content, filename=file.filename)
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# APIs para interação direta do frontend
@router.post("/api/accounts")
async def api_create_account(payload: AccountCreateRequest, db: Session = Depends(get_db)):
    from app.services.account_service import AccountService
    if not payload.name or not payload.name.strip():
        raise HTTPException(status_code=400, detail="Nome da conta é obrigatório")
    
    ws_id = payload.workspace_id
    if not ws_id:
        ws = db.query(Workspace).order_by(Workspace.id.desc()).first()
        if ws:
            ws_id = ws.id
        else:
            raise HTTPException(status_code=400, detail="Nenhum perfil/workspace ativo encontrado.")
            
    acc = AccountService.create_account(
        db=db,
        workspace_id=ws_id,
        name=payload.name.strip(),
        type=payload.type or "checking",
        initial_balance=float(payload.initial_balance or 0.0),
        icon=payload.icon or "🏦",
        color=payload.color or "#6366f1"
    )
    return {"success": True, "account_id": acc.id, "name": acc.name}

@router.put("/api/accounts/{account_id}")
async def api_update_account(account_id: int, payload: AccountUpdateRequest, db: Session = Depends(get_db)):
    from app.services.account_service import AccountService
    acc = AccountService.update_account(
        db=db,
        account_id=account_id,
        name=payload.name,
        type=payload.type,
        initial_balance=payload.initial_balance,
        icon=payload.icon,
        color=payload.color,
        is_active=payload.is_active
    )
    if not acc:
        raise HTTPException(status_code=404, detail="Conta não encontrada")
    return {"success": True, "account_id": acc.id}

@router.post("/api/accounts/{account_id}/toggle-active")
async def api_toggle_account_active(account_id: int, db: Session = Depends(get_db)):
    from app.services.account_service import AccountService
    acc = AccountService.toggle_account_active(db, account_id)
    if not acc:
        raise HTTPException(status_code=404, detail="Conta não encontrada")
    return {"success": True, "is_active": acc.is_active}

@router.delete("/api/accounts/{account_id}")
async def api_delete_account(account_id: int, db: Session = Depends(get_db)):
    from app.services.account_service import AccountService
    success = AccountService.delete_account(db, account_id)
    if not success:
        raise HTTPException(status_code=404, detail="Conta não encontrada")
    return {"success": True}

@router.post("/api/accounts/{account_id}/zero")
async def api_zero_account(
    account_id: int,
    workspace_id: int = Query(...),
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None),
    db: Session = Depends(get_db)
):
    """Zera o saldo e movimentações da conta no mês especificado"""
    from app.services.account_service import AccountService
    res = AccountService.zero_account(db, workspace_id, account_id, year=year, month=month)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("message", "Erro ao zerar conta"))
    return res

@router.post("/api/workspaces/{workspace_id}/zero-month")
async def api_zero_workspace_month(
    workspace_id: int,
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None),
    db: Session = Depends(get_db)
):
    """Zera todos os lançamentos do mês especificado no workspace"""
    from app.services.account_service import AccountService
    res = AccountService.zero_monthly_transactions(db, workspace_id, year=year, month=month)
    return res

@router.post("/api/accounts/transfer")
async def api_transfer_accounts(payload: AccountTransferRequest, db: Session = Depends(get_db)):
    from app.services.account_service import AccountService
    from datetime import datetime
    
    tx_date = None
    if payload.date:
        try:
            tx_date = datetime.strptime(payload.date, "%Y-%m-%d")
        except Exception:
            tx_date = None

    try:
        res = AccountService.transfer_between_accounts(
            db=db,
            workspace_id=payload.workspace_id,
            user_id=payload.user_id or 1,
            from_account_id=payload.from_account_id,
            to_account_id=payload.to_account_id,
            amount=payload.amount,
            description=payload.description,
            transaction_date=tx_date
        )
        return {"success": True, "amount": payload.amount}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar transferência: {str(e)}")


@router.post("/api/receipts/analyze")
async def api_analyze_receipt(
    file: UploadFile = File(...),
    workspace_id: int = Form(...),
    user_id: Optional[int] = Form(None),
    db: Session = Depends(get_db)
):
    """
    Recebe upload de imagem ou documento (PDF, JPG, PNG, WebP) de nota fiscal, cupom ou comprovante,
    processa via Gemini OCR Multimodal e retorna todos os dados financeiros estruturados,
    incluindo nome do estabelecimento, valor total, categoria, forma de pagamento e detalhamento item a item dos produtos.
    """
    from app.config import settings
    import uuid
    from datetime import datetime

    ai_service = AIService()
    filename = file.filename or "receipt.jpg"
    ext = os.path.splitext(filename)[1].lower()
    if not ext:
        ext = ".jpg"

    unique_id = uuid.uuid4().hex[:8]
    save_folder = "receipts" if ext in [".jpg", ".jpeg", ".png", ".webp"] else "documents"
    dir_path = os.path.join(settings.UPLOAD_DIR, save_folder)
    os.makedirs(dir_path, exist_ok=True)
    saved_path = os.path.join(dir_path, f"upload_{unique_id}_{filename}")

    # Salva arquivo enviado no disco
    content = await file.read()
    with open(saved_path, "wb") as f:
        f.write(content)

    ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    user = None
    if user_id:
        user = db.query(User).filter(User.id == user_id).first()
    if not user:
        user = db.query(User).first()

    user_context = {
        "user_name": user.name if user else "Usuário",
        "workspace_name": ws.name if ws else "Geral",
        "workspace_type": ws.type if ws else "personal"
    }

    try:
        if ext in [".jpg", ".jpeg", ".png", ".webp"] or (file.content_type and file.content_type.startswith("image/")):
            parsed = await ai_service.parse_receipt_image(saved_path, user_context=user_context)
        else:
            mime = file.content_type or "application/pdf"
            parsed = await ai_service.parse_document(saved_path, mime_type=mime, user_context=user_context)

        # Extrai transações e itens
        first_tx = parsed.transactions[0] if parsed.transactions else None
        extracted_items = []
        if first_tx and first_tx.items:
            for it in first_tx.items:
                extracted_items.append({
                    "name": it.name,
                    "quantity": it.quantity,
                    "unit": it.unit,
                    "unit_price": it.unit_price,
                    "total_price": it.total_price,
                    "category": it.category or "Geral"
                })

        if first_tx:
            tx_amount = first_tx.amount
            tx_desc = first_tx.description
            tx_type = first_tx.type
            tx_cat = first_tx.category_name
            tx_payment = first_tx.payment_method
        elif parsed.reminder:
            tx_amount = parsed.reminder.amount
            tx_desc = parsed.reminder.title
            tx_type = "expense" if parsed.reminder.type == "to_pay" else "income"
            tx_cat = "Contas & Serviços"
            tx_payment = "Boleto/Pix"
        else:
            tx_amount = 0.0
            tx_desc = os.path.splitext(filename)[0].replace("_", " ").title()
            tx_type = "expense"
            tx_cat = "Outros"
            tx_payment = "Cartão de Crédito"

        # Formata data
        tx_date = datetime.now().strftime("%Y-%m-%d")

        return {
            "success": True,
            "receipt_url": saved_path,
            "filename": filename,
            "description": tx_desc,
            "amount": tx_amount,
            "type": tx_type,
            "category_name": tx_cat,
            "payment_method": tx_payment,
            "date": tx_date,
            "has_items": len(extracted_items) > 0,
            "items_count": len(extracted_items),
            "items": extracted_items,
            "friendly_response": parsed.friendly_response
        }

    except Exception as e:
        return {
            "success": False,
            "receipt_url": saved_path,
            "filename": filename,
            "error": str(e),
            "description": "Despesa",
            "amount": 0.0,
            "type": "expense",
            "category_name": "Outros",
            "payment_method": "Outro",
            "items": [],
            "friendly_response": "Não foi possível extrair dados automaticamente deste arquivo."
        }

@router.post("/api/transactions")
async def api_create_transaction(payload: TransactionCreateRequest, db: Session = Depends(get_db)):
    """
    Cria uma nova transação financeira com suporte a inclusão opcional de itens detalhados (item a item)
    ou gravação exclusiva de valor total consolidado.
    """
    from datetime import datetime
    tx_date = None
    if payload.date:
        try:
            tx_date = datetime.strptime(payload.date, "%Y-%m-%d")
        except Exception:
            tx_date = None

    user_id = payload.user_id
    if not user_id:
        user = db.query(User).first()
        user_id = user.id if user else 1

    items_to_save = payload.items if (payload.include_items and payload.items) else None

    tx = FinanceService.add_transaction(
        db=db,
        workspace_id=payload.workspace_id,
        user_id=user_id,
        type=payload.type,
        amount=payload.amount,
        description=payload.description,
        category_name=payload.category_name or "Outros",
        payment_method=payload.payment_method or "Outro",
        account_id=payload.account_id,
        transaction_date=tx_date,
        receipt_url=payload.receipt_url,
        items=items_to_save
    )

    return {
        "success": True,
        "transaction_id": tx.id,
        "amount": tx.amount,
        "items_count": tx.items_count
    }

@router.get("/api/transactions/{transaction_id}/items")
async def api_get_transaction_items(transaction_id: int, db: Session = Depends(get_db)):
    """Retorna os itens discriminados de uma transação específica"""
    tx = db.query(Transaction).filter(Transaction.id == transaction_id).first()
    if not tx:
        raise HTTPException(status_code=404, detail="Lançamento não encontrado")
    
    items = FinanceService.get_transaction_items(db, transaction_id)
    return {
        "transaction_id": tx.id,
        "description": tx.description,
        "amount": tx.amount,
        "type": tx.type,
        "date": tx.transaction_date.strftime("%d/%m/%Y"),
        "category": tx.category.name if tx.category else "Outros",
        "items": [
            {
                "id": it.id,
                "name": it.name,
                "quantity": it.quantity,
                "unit": it.unit,
                "unit_price": it.unit_price,
                "total_price": it.total_price,
                "category": it.category
            }
            for it in items
        ]
    }

@router.delete("/api/transactions/{transaction_id}/items")
async def api_delete_transaction_items(transaction_id: int, db: Session = Depends(get_db)):
    """Remove a discriminação de itens de uma transação, mantendo o lançamento com o valor total"""
    success = FinanceService.delete_transaction_items(db, transaction_id)
    if not success:
        raise HTTPException(status_code=404, detail="Lançamento não encontrado")
    return {"success": True}

@router.put("/api/transactions/{transaction_id}/items")
async def api_update_transaction_items(
    transaction_id: int,
    payload: UpdateTransactionItemsRequest,
    db: Session = Depends(get_db)
):
    """Atualiza/salva a lista de itens discriminados de uma transação existente"""
    tx = db.query(Transaction).filter(Transaction.id == transaction_id).first()
    if not tx:
        raise HTTPException(status_code=404, detail="Lançamento não encontrado")
    
    items_data = [item.model_dump() for item in payload.items]
    saved = FinanceService.save_transaction_items(db, transaction_id, items_data)
    return {
        "success": True,
        "transaction_id": transaction_id,
        "items_count": len(saved)
    }


@router.get("/api/analytics/items")
async def api_get_items_analytics(
    workspace_id: int = Query(...),
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None),
    db: Session = Depends(get_db)
):
    """Retorna a análise e estatísticas completas de itens e produtos comprados no período"""
    data = FinanceService.get_items_analytics(db, workspace_id, year=year, month=month)
    return data

@router.get("/api/market/ranking")
async def api_get_market_ranking(
    workspace_id: int = Query(...),
    sort_by: str = Query("spent"),
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None),
    db: Session = Depends(get_db)
):
    """Retorna o ranking de itens mais consumidos e ranking de supermercados/gastos"""
    top_items = MarketAnalyticsService.get_top_consumed_items(
        db, workspace_id, limit=20, sort_by=sort_by, year=year, month=month
    )
    top_stores = MarketAnalyticsService.get_supermarket_ranking(
        db, workspace_id, limit=10, year=year, month=month
    )
    return {
        "top_items": top_items,
        "top_stores": top_stores
    }

@router.get("/api/market/compare-prices")
async def api_compare_market_prices(
    workspace_id: int = Query(...),
    query: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Compara preços unitários do mesmo produto entre diferentes supermercados"""
    comparisons = MarketAnalyticsService.get_cross_store_price_comparison(
        db, workspace_id, search_term=query
    )
    return {
        "comparisons": comparisons
    }

@router.get("/api/market/last-price")
async def api_get_last_item_price(
    workspace_id: int = Query(...),
    item_name: str = Query(...),
    db: Session = Depends(get_db)
):
    """Busca o preço unitário da última compra do item para pré-cadastro na lista de mercado"""
    price_info = MarketAnalyticsService.get_last_item_purchase_price(
        db, workspace_id, item_name=item_name
    )
    return price_info

@router.post("/api/shopping/items")
async def api_add_shopping_item(
    payload: AddShoppingItemRequest,
    db: Session = Depends(get_db)
):
    """Adiciona produto na lista ativa de compras com estimativa de preço automática"""
    s_list = ShoppingService.get_or_create_active_list(db, payload.workspace_id)
    item = ShoppingService.add_item(
        db=db,
        list_id=s_list.id,
        name=payload.name,
        quantity=payload.quantity or 1.0,
        unit=payload.unit or "un",
        estimated_price=payload.estimated_price or 0.0,
        category=payload.category or "Geral"
    )
    return {
        "success": True,
        "item": {
            "id": item.id,
            "name": item.name,
            "quantity": item.quantity,
            "unit": item.unit,
            "estimated_price": item.estimated_price,
            "total_estimated": item.estimated_price * item.quantity,
            "category": item.category,
            "is_checked": item.is_checked
        },
        "list_total_estimated": s_list.total_estimated
    }

@router.delete("/api/shopping/items/{item_id}")
async def api_delete_shopping_item(item_id: int, db: Session = Depends(get_db)):
    from app.models import ShoppingItem
    item = db.query(ShoppingItem).filter(ShoppingItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item não encontrado")
    db.delete(item)
    db.commit()
    return {"success": True}

@router.put("/api/transactions/{transaction_id}")
async def api_update_transaction(transaction_id: int, payload: TransactionUpdateRequest, db: Session = Depends(get_db)):
    """Atualiza a data do lançamento/vencimento e demais dados de uma transação existente"""
    from datetime import datetime
    parsed_date = None
    if payload.transaction_date:
        try:
            parsed_date = datetime.strptime(payload.transaction_date, "%Y-%m-%d")
        except Exception:
            pass

    tx = FinanceService.update_transaction(
        db=db,
        transaction_id=transaction_id,
        transaction_date=parsed_date,
        description=payload.description,
        amount=payload.amount,
        type=payload.type,
        category_name=payload.category_name,
        account_id=payload.account_id,
        payment_method=payload.payment_method,
        notes=payload.notes
    )
    if not tx:
        raise HTTPException(status_code=404, detail="Lançamento não encontrado")
    return {"success": True, "transaction_id": tx.id}

@router.delete("/api/transactions/{transaction_id}")
async def api_delete_transaction(transaction_id: int, db: Session = Depends(get_db)):
    success = FinanceService.delete_transaction(db, transaction_id)
    if not success:
        raise HTTPException(status_code=404, detail="Lançamento não encontrado")
    return {"success": True}

@router.post("/api/transactions/delete-batch")
async def api_delete_transactions_batch(payload: BatchDeleteTransactionsRequest, db: Session = Depends(get_db)):
    deleted_count = FinanceService.delete_transactions_batch(db, payload.transaction_ids)
    return {"success": True, "deleted_count": deleted_count}

@router.post("/api/shopping/toggle/{item_id}")
async def api_toggle_shopping_item(item_id: int, db: Session = Depends(get_db)):
    item = ShoppingService.toggle_item(db, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item não encontrado")
    return {"success": True, "is_checked": item.is_checked}

@router.post("/api/reminders")
async def api_create_reminder(payload: ReminderCreateRequest, db: Session = Depends(get_db)):
    """Cria uma nova conta a pagar ou a receber com data de vencimento"""
    from datetime import datetime, timedelta
    try:
        parsed_due = datetime.strptime(payload.due_date, "%Y-%m-%d")
    except Exception:
        parsed_due = datetime.utcnow() + timedelta(days=5)

    user = db.query(User).first()
    user_id = user.id if user else 1

    rem = ReminderService.create_reminder(
        db=db,
        workspace_id=payload.workspace_id,
        user_id=user_id,
        title=payload.title,
        amount=payload.amount,
        due_date=parsed_due,
        type=payload.type,
        recurrence=payload.recurrence,
        reminder_hours_before=payload.reminder_hours_before
    )
    return {"success": True, "reminder_id": rem.id}

@router.put("/api/reminders/{reminder_id}")
async def api_update_reminder(reminder_id: int, payload: ReminderUpdateRequest, db: Session = Depends(get_db)):
    """Atualiza a data de vencimento e demais informações de um lembrete/conta existente"""
    from datetime import datetime
    parsed_due = None
    if payload.due_date:
        try:
            parsed_due = datetime.strptime(payload.due_date, "%Y-%m-%d")
        except Exception:
            pass

    rem = ReminderService.update_reminder(
        db=db,
        reminder_id=reminder_id,
        due_date=parsed_due,
        title=payload.title,
        amount=payload.amount,
        type=payload.type,
        recurrence=payload.recurrence,
        reminder_hours_before=payload.reminder_hours_before,
        status=payload.status
    )
    if not rem:
        raise HTTPException(status_code=404, detail="Lembrete não encontrado")
    return {
        "success": True,
        "reminder": {
            "id": rem.id,
            "title": rem.title,
            "amount": rem.amount,
            "due_date": rem.due_date.strftime("%Y-%m-%d"),
            "type": rem.type,
            "recurrence": rem.recurrence,
            "reminder_hours_before": rem.reminder_hours_before
        }
    }

@router.post("/api/reminders/pay/{reminder_id}")
async def api_pay_reminder(reminder_id: int, db: Session = Depends(get_db)):
    rem = ReminderService.mark_as_paid(db, reminder_id)
    if not rem:
        raise HTTPException(status_code=404, detail="Lembrete não encontrado")
    
    # Registra despesa
    FinanceService.add_transaction(
        db=db,
        workspace_id=rem.workspace_id,
        user_id=rem.user_id or 1,
        type="expense" if rem.type == "to_pay" else "income",
        amount=rem.amount,
        description=f"Pagamento: {rem.title}",
        category_name="Contas & Serviços",
        payment_method="Boleto/Pix"
    )
    return {"success": True}

@router.delete("/api/reminders/{reminder_id}")
async def api_delete_reminder(reminder_id: int, db: Session = Depends(get_db)):
    rem = db.query(Reminder).filter(Reminder.id == reminder_id).first()
    if not rem:
        raise HTTPException(status_code=404, detail="Lembrete não encontrado")
    db.delete(rem)
    db.commit()
    return {"success": True}

@router.delete("/api/goals/{goal_id}")
async def api_delete_goal(goal_id: int, db: Session = Depends(get_db)):
    g = db.query(Goal).filter(Goal.id == goal_id).first()
    if not g:
        raise HTTPException(status_code=404, detail="Meta não encontrada")
    db.delete(g)
    db.commit()
    return {"success": True}

@router.delete("/api/vehicles/maintenance/{maintenance_id}")
async def api_delete_maintenance(maintenance_id: int, db: Session = Depends(get_db)):
    from app.models import VehicleMaintenance
    m = db.query(VehicleMaintenance).filter(VehicleMaintenance.id == maintenance_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Registro de manutenção não encontrado")
    db.delete(m)
    db.commit()
    return {"success": True}

@router.delete("/api/shopping/item/{item_id}")
async def api_delete_shopping_item(item_id: int, db: Session = Depends(get_db)):
    from app.models import ShoppingItem
    item = db.query(ShoppingItem).filter(ShoppingItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item de mercado não encontrado")
    db.delete(item)
    db.commit()
    return {"success": True}

# ========================================================
# REAL-TIME LIVE UPDATE STREAMS (SSE & WEBSOCKET)
# ========================================================
@router.get("/api/events/{workspace_id}")
async def sse_events(workspace_id: int):
    """Server-Sent Events (SSE) stream para atualizações em tempo real instantâneas no frontend"""
    queue = event_bus.subscribe_sse(workspace_id)

    async def event_generator():
        try:
            # Envia evento de conexão inicial
            yield f"data: {json.dumps({'event': 'connected', 'workspace_id': workspace_id, 'version': event_bus.get_workspace_version(workspace_id)})}\n\n"
            while True:
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"data: {json.dumps(data)}\n\n"
                except asyncio.TimeoutError:
                    yield f": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            event_bus.unsubscribe_sse(workspace_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

@router.websocket("/api/ws/{workspace_id}")
async def websocket_endpoint(websocket: WebSocket, workspace_id: int):
    """Canal WebSocket para atualizações em tempo real"""
    await event_bus.register_ws(workspace_id, websocket)
    try:
        while True:
            _ = await websocket.receive_text()
    except WebSocketDisconnect:
        event_bus.unregister_ws(workspace_id, websocket)
    except Exception:
        event_bus.unregister_ws(workspace_id, websocket)

@router.get("/api/sync/version")
async def api_sync_version(workspace_id: int, db: Session = Depends(get_db)):
    from sqlalchemy import func
    from app.models import Transaction, Account, Reminder, ShoppingItem, VehicleMaintenance

    tx_stat = db.query(func.count(Transaction.id), func.max(Transaction.id)).filter(Transaction.workspace_id == workspace_id).first()
    acc_stat = db.query(func.count(Account.id), func.sum(Account.current_balance)).filter(Account.workspace_id == workspace_id).first()
    rem_stat = db.query(func.count(Reminder.id)).filter(Reminder.workspace_id == workspace_id).first()
    shop_stat = db.query(func.count(ShoppingItem.id)).first()
    veh_stat = db.query(func.count(VehicleMaintenance.id)).first()

    fingerprint = f"{tx_stat[0]}_{tx_stat[1]}_{acc_stat[0]}_{acc_stat[1]}_{rem_stat[0]}_{shop_stat[0]}_{veh_stat[0]}"

    return {
        "workspace_id": workspace_id,
        "version": event_bus.get_workspace_version(workspace_id),
        "fingerprint": fingerprint
    }

# ========================================================
# APIS PARA CONFIGURAÇÃO DE TOKENS (TELEGRAM E IA)
# ========================================================
class SystemTokensUpdateRequest(BaseModel):
    telegram_bot_token: Optional[str] = None
    gemini_api_key: Optional[str] = None

class TestTelegramRequest(BaseModel):
    token: str

class TestGeminiRequest(BaseModel):
    api_key: str

@router.get("/api/system/tokens")
async def api_get_system_tokens():
    """Retorna o status atual das configurações de tokens"""
    from app.services.config_service import ConfigService
    return ConfigService.get_settings_status()

@router.post("/api/system/tokens")
async def api_update_system_tokens(payload: SystemTokensUpdateRequest):
    """Salva os novos tokens no .env, memória e atualiza serviços"""
    from app.services.config_service import ConfigService
    res = await ConfigService.save_tokens(
        telegram_token=payload.telegram_bot_token,
        gemini_key=payload.gemini_api_key
    )
    return res

@router.post("/api/system/test-telegram")
async def api_test_telegram(payload: TestTelegramRequest):
    """Testa a validade do token do Telegram"""
    from app.services.config_service import ConfigService
    return await ConfigService.test_telegram_token(payload.token)

@router.post("/api/system/test-gemini")
async def api_test_gemini(payload: TestGeminiRequest):
    """Testa a validade da API Key do Google Gemini"""
    from app.services.config_service import ConfigService
    return await ConfigService.test_gemini_key(payload.api_key)
