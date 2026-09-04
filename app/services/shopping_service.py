from typing import List, Optional
from sqlalchemy.orm import Session
from app.models import ShoppingList, ShoppingItem
from app.services.finance_service import FinanceService

class ShoppingService:
    @staticmethod
    def get_or_create_active_list(db: Session, workspace_id: int, title: str = "Lista de Mercado") -> ShoppingList:
        s_list = db.query(ShoppingList).filter(
            ShoppingList.workspace_id == workspace_id,
            ShoppingList.is_completed == False
        ).order_by(ShoppingList.created_at.desc()).first()

        if not s_list:
            s_list = ShoppingList(workspace_id=workspace_id, title=title)
            db.add(s_list)
            db.commit()
            db.refresh(s_list)
        return s_list

    @staticmethod
    def add_item(
        db: Session,
        list_id: int,
        name: str,
        quantity: float = 1.0,
        unit: str = "un",
        estimated_price: float = 0.0,
        category: str = "Geral"
    ) -> ShoppingItem:
        item = ShoppingItem(
            shopping_list_id=list_id,
            name=name.strip(),
            quantity=quantity,
            unit=unit,
            estimated_price=estimated_price,
            category=category
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        return item

    @staticmethod
    def toggle_item(db: Session, item_id: int) -> Optional[ShoppingItem]:
        item = db.query(ShoppingItem).filter(ShoppingItem.id == item_id).first()
        if not item:
            return None
        item.is_checked = not item.is_checked
        db.commit()
        db.refresh(item)
        return item

    @staticmethod
    def checkout_list(db: Session, list_id: int, user_id: int, actual_amount: Optional[float] = None) -> ShoppingList:
        """Conclui a lista de mercado e gera a transação de despesa no fluxo de caixa"""
        s_list = db.query(ShoppingList).filter(ShoppingList.id == list_id).first()
        if not s_list:
            return None

        total = actual_amount if actual_amount is not None else s_list.total_bought
        s_list.is_completed = True
        s_list.total_spent = total

        if total > 0:
            FinanceService.add_transaction(
                db=db,
                workspace_id=s_list.workspace_id,
                user_id=user_id,
                type="expense",
                amount=total,
                description=f"Compras de Supermercado ({s_list.title})",
                category_name="Alimentação",
                payment_method="Cartão"
            )

        db.commit()
        db.refresh(s_list)
        return s_list
