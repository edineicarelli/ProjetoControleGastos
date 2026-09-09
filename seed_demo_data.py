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

        # Adiciona transação de supermercado com detalhamento item a item
        market_items = [
            {"name": "Arroz Nobre 5kg", "quantity": 1.0, "unit": "pct", "unit_price": 32.90, "total_price": 32.90, "category": "Mercearia"},
            {"name": "Feijão Carioca 1kg", "quantity": 2.0, "unit": "pct", "unit_price": 8.50, "total_price": 17.00, "category": "Mercearia"},
            {"name": "Azeite de Oliva Extra Virgem 500ml", "quantity": 1.0, "unit": "un", "unit_price": 48.90, "total_price": 48.90, "category": "Mercearia"},
            {"name": "Picanha Bovina Resfriada", "quantity": 1.4, "unit": "kg", "unit_price": 89.90, "total_price": 125.86, "category": "Carnes & Aves"},
            {"name": "Peito de Frango Filezinho", "quantity": 2.0, "unit": "kg", "unit_price": 22.90, "total_price": 45.80, "category": "Carnes & Aves"},
            {"name": "Leite Integral Piracanjuba 1L", "quantity": 6.0, "unit": "un", "unit_price": 5.49, "total_price": 32.94, "category": "Laticínios & Frios"},
            {"name": "Queijo Muçarela Fatiado", "quantity": 0.5, "unit": "kg", "unit_price": 46.00, "total_price": 23.00, "category": "Laticínios & Frios"},
            {"name": "Café Torrado e Moído 500g", "quantity": 2.0, "unit": "pct", "unit_price": 19.80, "total_price": 39.60, "category": "Mercearia"},
            {"name": "Detergente Líquido Ypê", "quantity": 4.0, "unit": "un", "unit_price": 2.99, "total_price": 11.96, "category": "Limpeza"},
            {"name": "Sabão em Pó Omo 1.6kg", "quantity": 1.0, "unit": "cx", "unit_price": 36.90, "total_price": 36.90, "category": "Limpeza"},
            {"name": "Maçã Gala Nacional", "quantity": 1.5, "unit": "kg", "unit_price": 9.90, "total_price": 14.85, "category": "Hortifruti"},
            {"name": "Banana Prata", "quantity": 1.2, "unit": "kg", "unit_price": 7.90, "total_price": 9.48, "category": "Hortifruti"},
            {"name": "Papel Higiênico Neve 12 rolos", "quantity": 1.0, "unit": "pct", "unit_price": 29.90, "total_price": 29.90, "category": "Higiene & Beleza"}
        ]
        market_total = round(sum(it["total_price"] for it in market_items), 2)

        FinanceService.add_transaction(
            db=db,
            workspace_id=ws_pf.id,
            user_id=user.id,
            type="expense",
            amount=market_total,
            description="Supermercado Pão de Açúcar",
            category_name="Supermercado",
            payment_method="Cartão de Crédito",
            transaction_date=now - datetime.timedelta(days=2),
            items=market_items
        )

        # Transação de farmácia com itens
        pharma_items = [
            {"name": "Vitamina C + Zinco Efervescente", "quantity": 2.0, "unit": "cx", "unit_price": 24.90, "total_price": 49.80, "category": "Farmácia"},
            {"name": "Protetor Solar FPS 50 200ml", "quantity": 1.0, "unit": "un", "unit_price": 59.90, "total_price": 59.90, "category": "Higiene & Beleza"},
            {"name": "Dipirona 500mg 20 comp", "quantity": 1.0, "unit": "cx", "unit_price": 9.50, "total_price": 9.50, "category": "Farmácia"}
        ]
        pharma_total = round(sum(it["total_price"] for it in pharma_items), 2)

        FinanceService.add_transaction(
            db=db,
            workspace_id=ws_pf.id,
            user_id=user.id,
            type="expense",
            amount=pharma_total,
            description="Drogaria São Paulo",
            category_name="Saúde & Farmácia",
            payment_method="Pix",
            transaction_date=now - datetime.timedelta(days=5),
            items=pharma_items
        )

        FinanceService.add_transaction(db, ws_pf.id, user.id, "expense", 85.50, "Jantar Restaurante", "Alimentação", "Cartão de Débito", now - datetime.timedelta(days=1))
        FinanceService.add_transaction(db, ws_pf.id, user.id, "expense", 180.0, "Combustível Posto Shell", "Transporte", "Cartão de Débito", now - datetime.timedelta(days=3))
        FinanceService.add_transaction(db, ws_pf.id, user.id, "expense", 120.0, "Internet Fibra", "Moradia", "Boleto", now - datetime.timedelta(days=4))


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
