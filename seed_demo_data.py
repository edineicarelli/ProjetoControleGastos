import datetime
from app.database import init_db, SessionLocal
from app.services.finance_service import FinanceService
from app.services.reminder_service import ReminderService
from app.services.goal_service import GoalService
from app.services.vehicle_service import VehicleService
from app.services.shopping_service import ShoppingService

def seed():
    print("Inicializando banco de dados...")
    init_db()
    db = SessionLocal()

    try:
        # Cria usuário demo
        user, ws_pf = FinanceService.get_or_create_user(
            db=db,
            telegram_id="123456789",
            name="Eduardo Carelli",
            username="ecarelli"
        )
        print(f"Usuário criado: {user.name} | Workspace PF: {ws_pf.name}")

        # Adiciona transações de exemplo no PF
        now = datetime.datetime.utcnow()
        FinanceService.add_transaction(db, ws_pf.id, user.id, "income", 5500.0, "Salário Mensal", "Salário", "Pix", now - datetime.timedelta(days=2))
        FinanceService.add_transaction(db, ws_pf.id, user.id, "income", 1200.0, "Freela de Desenvolvimento", "Freelas & Extras", "Pix", now - datetime.timedelta(days=1))

        FinanceService.add_transaction(db, ws_pf.id, user.id, "expense", 450.0, "Supermercado Mensal", "Alimentação", "Cartão de Crédito", now - datetime.timedelta(days=2))
        FinanceService.add_transaction(db, ws_pf.id, user.id, "expense", 85.50, "Jantar Restaurante", "Alimentação", "Cartão de Débito", now - datetime.timedelta(days=1))
        FinanceService.add_transaction(db, ws_pf.id, user.id, "expense", 180.0, "Combustível Posto Shell", "Transporte", "Cartão de Débito", now - datetime.timedelta(days=3))
        FinanceService.add_transaction(db, ws_pf.id, user.id, "expense", 120.0, "Internet Fibra", "Moradia", "Boleto", now - datetime.timedelta(days=4))
        FinanceService.add_transaction(db, ws_pf.id, user.id, "expense", 65.0, "Farmácia", "Saúde", "Pix", now - datetime.timedelta(days=5))

        # Adiciona Lembretes
        ReminderService.create_reminder(db, ws_pf.id, user.id, "Condomínio Edifício", 480.0, now + datetime.timedelta(days=4), recurrence="monthly")
        ReminderService.create_reminder(db, ws_pf.id, user.id, "Fatura Cartão Black", 1450.0, now + datetime.timedelta(days=9), recurrence="monthly")

        # Adiciona Metas
        GoalService.create_goal(db, ws_pf.id, "Reserva de Emergência", 20000.0, 8500.0, icon="🛡️")
        GoalService.create_goal(db, ws_pf.id, "Viagem Fim de Ano", 5000.0, 3200.0, icon="✈️")

        # Adiciona Veículo & Manutenções
        vehicle = VehicleService.get_or_create_vehicle(db, ws_pf.id, name="Civic Touring 1.5T", plate="BRA-2E19")
        VehicleService.add_maintenance(db, vehicle.id, "oil_change", "Troca de Óleo Sintético 0W20 + Filtros", 380.0, km=45000.0, next_due_km=55000.0)
        VehicleService.add_maintenance(db, vehicle.id, "fuel", "Abastecimento Gasolina Podium", 250.0, km=45300.0)

        # Adiciona Lista de Mercado
        s_list = ShoppingService.get_or_create_active_list(db, ws_pf.id, "Compras da Semana")
        ShoppingService.add_item(db, s_list.id, "Arroz Integral 5kg", 1, "pct", 28.90)
        ShoppingService.add_item(db, s_list.id, "Azeite Extra Virgem", 1, "un", 42.00)
        ShoppingService.add_item(db, s_list.id, "Peito de Frango", 2, "kg", 38.00)
        ShoppingService.add_item(db, s_list.id, "Café em Grãos", 1, "pct", 35.00)

        # Workspace PJ (Empresa)
        ws_pj = FinanceService.switch_workspace(db, user, "business")
        FinanceService.add_transaction(db, ws_pj.id, user.id, "income", 18500.0, "Faturamento Projeto Consultoria", "Vendas", "Pix", now - datetime.timedelta(days=3))
        FinanceService.add_transaction(db, ws_pj.id, user.id, "expense", 2200.0, "Servidores AWS & Cloud", "Contas & Serviços", "Cartão de Crédito", now - datetime.timedelta(days=2))
        FinanceService.add_transaction(db, ws_pj.id, user.id, "expense", 1100.0, "Contabilidade Mensal", "Contas & Serviços", "Pix", now - datetime.timedelta(days=4))

        # Retorna para PF
        FinanceService.switch_workspace(db, user, "personal")

        print("✅ Dados de demonstração semeados com sucesso!")
    finally:
        db.close()

if __name__ == "__main__":
    seed()
