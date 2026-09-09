import datetime
import re
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, extract
from app.models import Transaction, TransactionItem, Category

class MarketAnalyticsService:
    @staticmethod
    def _normalize_item_name(name: str) -> str:
        """Normaliza nome de produto para agrupamento inteligente"""
        if not name:
            return ""
        clean = name.strip()
        # Remove códigos numéricos no início ou final
        clean = re.sub(r"^\d+\s*[-–]\s*", "", clean)
        clean = re.sub(r"\s+\d+$", "", clean)
        return clean.title()

    @staticmethod
    def _extract_store_name(description: str) -> str:
        """Extrai nome amigável do supermercado/loja da descrição da transação"""
        if not description:
            return "Supermercado Geral"
        clean = description.strip()
        # Remove prefixos comuns como 'Compra no', 'Compras no', 'Mercado', 'Supermercado'
        clean = re.sub(r"^(?:compra(?:s)?\s+(?:no|na|em|de)?|pagamento\s+(?:no|na|em|de)?)\s*", "", clean, flags=re.IGNORECASE).strip()
        return clean.title() if clean else "Supermercado"

    @staticmethod
    def get_top_consumed_items(
        db: Session,
        workspace_id: int,
        limit: int = 15,
        sort_by: str = "spent",  # 'spent' ou 'quantity'
        year: Optional[int] = None,
        month: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Retorna ranking dos produtos mais consumidos / comprados no workspace.
        Permite ordenar por valor total gasto (R$) ou volume/quantidade total.
        """
        query = db.query(
            TransactionItem, Transaction
        ).join(
            Transaction, TransactionItem.transaction_id == Transaction.id
        ).filter(
            Transaction.workspace_id == workspace_id
        )

        if year:
            query = query.filter(extract('year', Transaction.transaction_date) == int(year))
        if month:
            query = query.filter(extract('month', Transaction.transaction_date) == int(month))

        results = query.order_by(Transaction.transaction_date.desc()).all()

        # Agrupamento inteligente em memória por nome normalizado
        grouped = {}
        for item, tx in results:
            norm_name = MarketAnalyticsService._normalize_item_name(item.name)
            store_name = MarketAnalyticsService._extract_store_name(tx.description)

            if norm_name not in grouped:
                grouped[norm_name] = {
                    "name": norm_name,
                    "category": item.category or "Geral",
                    "total_quantity": 0.0,
                    "unit": item.unit or "un",
                    "total_spent": 0.0,
                    "purchase_count": 0,
                    "prices": [],
                    "stores": set(),
                    "last_purchase_date": tx.transaction_date.strftime("%d/%m/%Y") if tx.transaction_date else "",
                    "last_unit_price": item.unit_price,
                    "last_store": store_name
                }

            item_total = item.total_price if item.total_price > 0 else (item.quantity * item.unit_price)
            grouped[norm_name]["total_quantity"] += (item.quantity or 1.0)
            grouped[norm_name]["total_spent"] += item_total
            grouped[norm_name]["purchase_count"] += 1
            if item.unit_price > 0:
                grouped[norm_name]["prices"].append(item.unit_price)
            grouped[norm_name]["stores"].add(store_name)

        items_list = []
        for name, data in grouped.items():
            avg_price = (data["total_spent"] / data["total_quantity"]) if data["total_quantity"] > 0 else (sum(data["prices"]) / len(data["prices"]) if data["prices"] else 0.0)
            items_list.append({
                "name": data["name"],
                "category": data["category"],
                "total_quantity": round(data["total_quantity"], 3),
                "unit": data["unit"],
                "total_spent": round(data["total_spent"], 2),
                "avg_unit_price": round(avg_price, 2),
                "purchase_count": data["purchase_count"],
                "stores_count": len(data["stores"]),
                "stores_list": list(data["stores"]),
                "last_purchase_date": data["last_purchase_date"],
                "last_unit_price": data["last_unit_price"],
                "last_store": data["last_store"]
            })

        if sort_by == "quantity":
            items_list.sort(key=lambda x: x["total_quantity"], reverse=True)
        else:
            items_list.sort(key=lambda x: x["total_spent"], reverse=True)

        return items_list[:limit]

    @staticmethod
    def get_supermarket_ranking(
        db: Session,
        workspace_id: int,
        limit: int = 10,
        year: Optional[int] = None,
        month: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Retorna ranking dos supermercados/estabelecimentos onde o usuário mais gasta.
        """
        query = db.query(Transaction).filter(
            Transaction.workspace_id == workspace_id,
            Transaction.type == "expense"
        )

        if year:
            query = query.filter(extract('year', Transaction.transaction_date) == int(year))
        if month:
            query = query.filter(extract('month', Transaction.transaction_date) == int(month))

        txs = query.order_by(Transaction.transaction_date.desc()).all()

        stores = {}
        for tx in txs:
            is_market = False
            cat_name = tx.category.name.lower() if tx.category else ""
            if any(k in cat_name for k in ["mercado", "supermercado", "alimenta", "feira", "açougue", "padaria", "horti"]):
                is_market = True
            elif tx.items_count > 0:
                is_market = True
            elif any(k in tx.description.lower() for k in ["mercado", "super", "hiper", "atacad", "bistek", "angeloni", "zornitta", "condor", "muffato", "carrefour", "pão de açúcar"]):
                is_market = True

            if not is_market:
                continue

            store_name = MarketAnalyticsService._extract_store_name(tx.description)
            if store_name not in stores:
                stores[store_name] = {
                    "store_name": store_name,
                    "total_spent": 0.0,
                    "transaction_count": 0,
                    "total_items_count": 0,
                    "last_visit": tx.transaction_date.strftime("%d/%m/%Y") if tx.transaction_date else "",
                    "items": {}
                }

            stores[store_name]["total_spent"] += tx.amount
            stores[store_name]["transaction_count"] += 1
            stores[store_name]["total_items_count"] += tx.items_count

            # Agrupa itens do mercado
            for item in tx.items:
                i_name = item.name.strip().title()
                if i_name not in stores[store_name]["items"]:
                    stores[store_name]["items"][i_name] = {
                        "name": i_name,
                        "quantity": 0.0,
                        "unit": item.unit or "un",
                        "total_spent": 0.0
                    }
                stores[store_name]["items"][i_name]["quantity"] += (item.quantity or 1.0)
                tot = item.total_price if item.total_price > 0 else ((item.quantity or 1.0) * (item.unit_price or 0.0))
                stores[store_name]["items"][i_name]["total_spent"] += tot

        ranking = []
        for s in stores.values():
            ticket_medio = s["total_spent"] / s["transaction_count"] if s["transaction_count"] > 0 else 0.0
            items_arr = sorted(s["items"].values(), key=lambda x: x["total_spent"], reverse=True)
            for it in items_arr:
                it["total_spent"] = round(it["total_spent"], 2)
                it["quantity"] = round(it["quantity"], 2)

            ranking.append({
                "store_name": s["store_name"],
                "total_spent": round(s["total_spent"], 2),
                "transaction_count": s["transaction_count"],
                "avg_ticket": round(ticket_medio, 2),
                "total_items_count": s["total_items_count"],
                "last_visit": s["last_visit"],
                "items_list": items_arr
            })

        ranking.sort(key=lambda x: x["total_spent"], reverse=True)
        return ranking[:limit]

    @staticmethod
    def get_cross_store_price_comparison(
        db: Session,
        workspace_id: int,
        search_term: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Compara o preço do mesmo item entre diferentes supermercados/estabelecimentos.
        Identifica onde foi comprado mais barato, onde foi mais caro e a variação %.
        """
        query = db.query(
            TransactionItem, Transaction
        ).join(
            Transaction, TransactionItem.transaction_id == Transaction.id
        ).filter(
            Transaction.workspace_id == workspace_id
        )

        if search_term and search_term.strip():
            query = query.filter(TransactionItem.name.ilike(f"%{search_term.strip()}%"))

        results = query.order_by(Transaction.transaction_date.desc()).all()

        products = {}
        for item, tx in results:
            norm_name = MarketAnalyticsService._normalize_item_name(item.name)
            store_name = MarketAnalyticsService._extract_store_name(tx.description)

            if norm_name not in products:
                products[norm_name] = {
                    "product_name": norm_name,
                    "category": item.category or "Geral",
                    "unit": item.unit or "un",
                    "stores_data": {}
                }

            if item.unit_price <= 0:
                continue

            if store_name not in products[norm_name]["stores_data"]:
                products[norm_name]["stores_data"][store_name] = {
                    "store_name": store_name,
                    "latest_price": item.unit_price,
                    "min_price": item.unit_price,
                    "max_price": item.unit_price,
                    "unit": item.unit or "un",
                    "last_date": tx.transaction_date.strftime("%d/%m/%Y") if tx.transaction_date else "",
                    "count": 1
                }
            else:
                st = products[norm_name]["stores_data"][store_name]
                st["min_price"] = min(st["min_price"], item.unit_price)
                st["max_price"] = max(st["max_price"], item.unit_price)
                st["count"] += 1

        comparison_list = []
        for prod_name, data in products.items():
            stores_list = list(data["stores_data"].values())
            if not stores_list:
                continue

            stores_list.sort(key=lambda x: x["latest_price"])

            cheapest = stores_list[0]
            most_expensive = stores_list[-1]

            has_comparison = len(stores_list) > 1
            price_diff = round(most_expensive["latest_price"] - cheapest["latest_price"], 2)
            diff_pct = round((price_diff / cheapest["latest_price"] * 100), 1) if (cheapest["latest_price"] > 0 and has_comparison) else 0.0

            comparison_list.append({
                "product_name": prod_name,
                "category": data["category"],
                "unit": data["unit"],
                "stores_count": len(stores_list),
                "has_multi_store_comparison": has_comparison,
                "cheapest_store": {
                    "store_name": cheapest["store_name"],
                    "price": cheapest["latest_price"],
                    "unit": cheapest["unit"],
                    "date": cheapest["last_date"]
                },
                "most_expensive_store": {
                    "store_name": most_expensive["store_name"],
                    "price": most_expensive["latest_price"],
                    "unit": most_expensive["unit"],
                    "date": most_expensive["last_date"]
                } if has_comparison else None,
                "price_diff": price_diff if has_comparison else 0.0,
                "diff_pct": diff_pct if has_comparison else 0.0,
                "all_stores": stores_list
            })

        comparison_list.sort(key=lambda x: (not x["has_multi_store_comparison"], -x["diff_pct"], x["product_name"]))
        return comparison_list

    @staticmethod
    def detect_default_unit_and_category(product_name: str) -> tuple[str, str, Optional[str]]:
        """
        Detecta a unidade comercial padrão brasileira (kg, l, pct, cx, un) e categoria
        com base no nome do produto (ex: Pão Francês -> KG, Tomate -> KG, Leite -> L/UN).
        Retorna (unidade, categoria, dica_ao_usuario).
        """
        if not product_name:
            return "un", "Geral", None

        p = product_name.lower().strip()

        # Itens comercializados por KG / Peso (Padaria a peso, Açougue, Frios, Hortifruti)
        kg_keywords = [
            "pao frances", "pão francês", "pao de sal", "pão de sal", "pao d'agua", "pão d'água",
            "cacetinho", "pao de queijo", "pão de queijo", "chipa",
            "queijo", "mussarela", "muçarela", "prato", "provolone", "parmesao", "parmesão",
            "presunto", "mortadela", "peito de peru", "salame", "bacon",
            "picanha", "alcatra", "maminha", "contrafile", "contrafilé", "patinho", "acem", "acém",
            "carne moida", "carne moída", "costela", "frango", "peito de frango", "filé", "file",
            "coxa", "sobrecoxa", "linguica", "linguiça", "toscana", "lombo", "pernil", "bisteca",
            "peixe", "salmao", "salmão", "tilapia", "tilápia", "camarao", "camarão",
            "tomate", "banana", "batata", "cebola", "alho", "maca", "maçã", "laranja", "cenoura",
            "melancia", "melao", "melão", "mamao", "mamão", "abobrinha", "berinjela", "chuchu",
            "beterraba", "pimentao", "pimentão", "uva", "manga", "limao", "limão", "tangerina",
            "mexerica", "bergamota", "pera", "morango", "pepino", "mandioca", "aipim", "macaxeira"
        ]

        # Categorização e Detecção KG
        for k in kg_keywords:
            if k in p:
                cat = "Hortifruti"
                if any(b in p for b in ["pao", "pão", "queijo", "chipa", "bolo"]):
                    cat = "Padaria & Sobremesas" if "pao" in p or "bolo" in p else "Laticínios & Frios"
                elif any(b in p for b in ["queijo", "presunto", "mortadela", "salame", "peru"]):
                    cat = "Laticínios & Frios"
                elif any(b in p for b in ["picanha", "carne", "alcatra", "maminha", "contrafile", "patinho", "acem", "costela", "frango", "coxa", "linguica", "linguiça", "bacon", "lombo", "pernil", "bisteca", "peixe", "salmao", "tilapia", "camarao"]):
                    cat = "Açougue & Carnes"
                return "kg", cat, f"💡 *{product_name.title()}* é vendido por *KG* (peso na balança)."

        # Líquidos (L / Garrafa / Caixa)
        liquid_keywords = [
            "leite", "suco", "refrigerante", "coca", "guarana", "guaraná", "agua", "água",
            "cerveja", "vinho", "azeite", "oleo", "óleo", "detergente", "amaciante", "desinfetante", "vinagre"
        ]
        for lk in liquid_keywords:
            if lk in p:
                cat = "Bebidas" if any(b in p for b in ["leite", "suco", "refrigerante", "coca", "guarana", "agua", "cerveja", "vinho"]) else "Limpeza & Casa"
                return "un", cat, None

        # Pacotes / Caixas
        pct_keywords = [
            "arroz", "feijao", "feijão", "cafe", "café", "acucar", "açúcar", "farinha", "macarrao", "macarrão",
            "biscoito", "bolacha", "torrada", "granola", "aveia", "papel higienico", "sabao em po", "sabão em pó"
        ]
        for pk in pct_keywords:
            if pk in p:
                cat = "Limpeza & Casa" if "papel" in p or "sabao" in p else "Mercearia"
                unit = "cx" if "sabao em po" in p else "pct"
                return unit, cat, None

        return "un", "Geral", None

    @staticmethod
    def get_last_item_purchase_price(
        db: Session,
        workspace_id: int,
        item_name: str
    ) -> Dict[str, Any]:
        """
        Encontra a última compra de determinado produto no workspace para prever o custo
        estimado e unidade correta (ex: Pão Francês -> KG) ao montar Lista de Mercado ou Lançamento.
        """
        if not item_name or not item_name.strip():
            return {"found": False, "estimated_unit_price": 0.0, "unit": "un", "category": "Geral", "unit_tip": None}

        query_name = item_name.strip().lower()
        words = [w for w in query_name.split() if len(w) >= 2]
        default_unit, default_cat, default_tip = MarketAnalyticsService.detect_default_unit_and_category(item_name)

        items_query = db.query(
            TransactionItem, Transaction
        ).join(
            Transaction, TransactionItem.transaction_id == Transaction.id
        ).filter(
            Transaction.workspace_id == workspace_id,
            TransactionItem.unit_price > 0
        ).order_by(Transaction.transaction_date.desc(), TransactionItem.id.desc())

        all_items = items_query.limit(200).all()

        best_match = None
        for item, tx in all_items:
            item_n = item.name.lower()
            if all(w in item_n for w in words):
                best_match = (item, tx)
                break

        if not best_match and len(words) > 0:
            first_word = words[0]
            if len(first_word) >= 3:
                for item, tx in all_items:
                    if first_word in item.name.lower():
                        best_match = (item, tx)
                        break

        if best_match:
            item, tx = best_match
            store_name = MarketAnalyticsService._extract_store_name(tx.description)
            unit_to_use = item.unit if item.unit else default_unit
            return {
                "found": True,
                "matched_name": item.name,
                "estimated_unit_price": item.unit_price,
                "unit": unit_to_use,
                "category": item.category or default_cat,
                "last_store": store_name,
                "last_date": tx.transaction_date.strftime("%d/%m/%Y") if tx.transaction_date else "",
                "last_total_price": item.total_price,
                "unit_tip": default_tip or (f"💡 Vendido por {unit_to_use.upper()}" if unit_to_use != 'un' else None)
            }

        return {
            "found": False,
            "estimated_unit_price": 0.0,
            "unit": default_unit,
            "category": default_cat,
            "unit_tip": default_tip
        }
