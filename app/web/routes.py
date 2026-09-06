import os
import json
import asyncio
from typing import Optional, List
from fastapi import APIRouter, Request, Depends, Query, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, Workspace, WorkspaceMember, Goal, Reminder, ShoppingList, Category
from app.services.finance_service import FinanceService
from app.services.reminder_service import ReminderService
from app.services.vehicle_service import VehicleService
from app.services.shopping_service import ShoppingService
from app.services.account_service import AccountService
from app.services.user_service import UserService
from app.services.export_service import ExportService
from app.services.event_bus import event_bus

from app.utils import format_currency_br, format_number_br

router = APIRouter()

templates_dir = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=templates_dir)
templates.env.filters["currency_br"] = format_currency_br
templates.env.filters["number_br"] = format_number_br

@router.get("/join/{invite_code}")
@router.get("/entrar/{invite_code}")
async def web_join_workspace(invite_code: str, db: Session = Depends(get_db)):
    """Rota direta para ingressar no workspace via link web"""
    ws = db.query(Workspace).filter(Workspace.invite_code == invite_code.strip().upper()).first()
    if not ws:
        raise HTTPException(status_code=404, detail="Código de convite não encontrado.")
    return RedirectResponse(url=f"https://t.me/carellifinanceiro_bot?start=convite_{ws.invite_code}")

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
    """Página principal do Dashboard Financeiro / Telegram Mini App com suporte a navegação mensal"""
    # Se passar user_id (telegram_id), busca o usuário, senão busca o usuário mais recente cadastrado
    user = None
    if user_id:
        user = db.query(User).filter(User.telegram_id == str(user_id)).first()
    
    if not user:
        # Prioriza o usuário real mais recente (não demo/teste)
        user = db.query(User).filter(User.telegram_id.notin_(['demo_user', 'test_unit'])).order_by(User.id.desc()).first()
        if not user:
            user = db.query(User).order_by(User.id.desc()).first()

    # Se ainda não existir nenhum usuário, cria um usuário padrão
    if not user:
        user, ws = FinanceService.get_or_create_user(db, telegram_id="demo_user", name="Demonstração")
    
    # Determina workspace
    if workspace_id:
        current_workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    else:
        current_workspace = user.current_workspace

    if not current_workspace:
        current_workspace = db.query(Workspace).order_by(Workspace.id.desc()).first()

    # Lista todos os workspaces para fácil alternância no painel
    user_workspaces = db.query(Workspace).order_by(Workspace.id.desc()).all()

    clean_year = int(year) if (year is not None and str(year).isdigit()) else None
    clean_month = int(month) if (month is not None and str(month).isdigit()) else None

    accounts = AccountService.get_accounts(db, current_workspace.id)
    summary = FinanceService.get_monthly_summary(db, current_workspace.id, year=clean_year, month=clean_month)
    monthly_transactions = summary["monthly_transactions"]
    workspace_members = UserService.get_workspace_members(db, current_workspace.id)

    goals = db.query(Goal).filter(Goal.workspace_id == current_workspace.id).all()
    reminders = ReminderService.get_upcoming_reminders(db, current_workspace.id)
    vehicle = VehicleService.get_or_create_vehicle(db, current_workspace.id)
    vehicle_summary = VehicleService.get_vehicle_summary(db, vehicle.id)
    shopping_list = ShoppingService.get_or_create_active_list(db, current_workspace.id)

    bot_username = "carellifinanceiro_bot"
    invite_link = f"https://t.me/{bot_username}?start=convite_{current_workspace.invite_code}"

    categories = db.query(Category).filter(Category.workspace_id == current_workspace.id).order_by(Category.name.asc()).all()

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "user": user,
            "current_workspace": current_workspace,
            "user_workspaces": user_workspaces,
            "workspace_members": workspace_members,
            "accounts": accounts,
            "categories": categories,
            "summary": summary,
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

class BatchDeleteTransactionsRequest(BaseModel):
    transaction_ids: List[int]

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

# APIs para Gestão de Usuários & Membros (Web & Telegram)
@router.post("/api/users")
async def api_add_user(payload: UserAddRequest, db: Session = Depends(get_db)):
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
async def api_update_user(user_id: int, workspace_id: int, payload: UserUpdateRequest, db: Session = Depends(get_db)):
    from app.services.user_service import UserService
    res = UserService.update_user_member(
        db=db,
        workspace_id=workspace_id,
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
async def api_toggle_user_active(user_id: int, workspace_id: int, db: Session = Depends(get_db)):
    from app.models import User
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    user.is_active = not (user.is_active if user.is_active is not None else True)
    db.commit()
    try:
        from app.services.event_bus import event_bus
        event_bus.notify_workspace_update(workspace_id)
    except Exception:
        pass
    return {"success": True, "is_active": user.is_active}

@router.delete("/api/workspaces/{workspace_id}/members/{user_id}")
async def api_remove_workspace_member(workspace_id: int, user_id: int, db: Session = Depends(get_db)):
    from app.services.user_service import UserService
    try:
        success = UserService.remove_user_from_workspace(db, workspace_id, user_id)
        if not success:
            raise HTTPException(status_code=404, detail="Membro não encontrado neste perfil")
        return {"success": True}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))



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
