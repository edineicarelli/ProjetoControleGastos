import datetime
import re
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, extract
from app.models import Transaction, TransactionItem, Category

MACRO_SEGMENTS = {
    "all": {
        "key": "all",
        "name": "Todos os Itens",
        "icon": "🌟",
        "color": "#6366f1",
        "store_label": "Estabelecimentos",
        "store_title": "🏪 Estabelecimentos Onde Mais Gasta",
        "products_title": "🏆 Produtos Mais Consumidos (Geral)",
        "comparison_title": "🔍 Comparador de Preços (Todos os Estabelecimentos)",
        "kpi_spent_label": "Total Geral em Itens",
        "kpi_stores_label": "Estabelecimentos Visitados"
    },
    "mercado": {
        "key": "mercado",
        "name": "Supermercado & Alimentação",
        "icon": "🛒",
        "color": "#10b981",
        "store_label": "Supermercados",
        "store_title": "🏪 Supermercados Onde Você Mais Gasta",
        "products_title": "🏆 Produtos de Mercado Mais Consumidos",
        "comparison_title": "🔍 Comparador de Preços entre Supermercados",
        "kpi_spent_label": "Total em Supermercado",
        "kpi_stores_label": "Supermercados Visitados"
    },
    "combustivel": {
        "key": "combustivel",
        "name": "Combustíveis & Postos",
        "icon": "⛽",
        "color": "#f59e0b",
        "store_label": "Postos de Combustível",
        "store_title": "⛽ Postos Onde Você Mais Abastece",
        "products_title": "⛽ Combustíveis & Produtos Mais Abastecidos",
        "comparison_title": "🔍 Comparador de Preços de Combustível entre Postos",
        "kpi_spent_label": "Total em Combustíveis",
        "kpi_stores_label": "Postos Visitados"
    },
    "tintas_reforma": {
        "key": "tintas_reforma",
        "name": "Tintas & Construção",
        "icon": "🎨",
        "color": "#8b5cf6",
        "store_label": "Lojas de Tintas & Construção",
        "store_title": "🎨 Lojas de Tintas & Materiais Onde Mais Compra",
        "products_title": "🎨 Tintas, Vernizes & Materiais Mais Comprados",
        "comparison_title": "🔍 Comparador de Preços (Tintas, Selantes & Construção)",
        "kpi_spent_label": "Total em Tintas & Reforma",
        "kpi_stores_label": "Lojas de Tintas & Obras"
    },
    "farmacia": {
        "key": "farmacia",
        "name": "Farmácia & Saúde",
        "icon": "💊",
        "color": "#06b6d4",
        "store_label": "Farmácias & Drogarias",
        "store_title": "💊 Farmácias Onde Você Mais Compra",
        "products_title": "💊 Medicamentos & Itens de Farmácia",
        "comparison_title": "🔍 Comparador de Preços entre Drogarias & Farmácias",
        "kpi_spent_label": "Total em Farmácia & Saúde",
        "kpi_stores_label": "Farmácias Visitadas"
    },
    "veicular": {
        "key": "veicular",
        "name": "Veicular & Autopeças",
        "icon": "🚗",
        "color": "#ec4899",
        "store_label": "Oficinas & Autopeças",
        "store_title": "🚗 Autopeças & Oficinas Onde Mais Gasta",
        "products_title": "🚗 Peças, Óleos & Serviços Veiculares",
        "comparison_title": "🔍 Comparador de Preços de Autopeças & Manutenção",
        "kpi_spent_label": "Total em Peças & Veicular",
        "kpi_stores_label": "Oficinas & Autopeças"
    },
    "outros": {
        "key": "outros",
        "name": "Outros Itens & Serviços",
        "icon": "📦",
        "color": "#64748b",
        "store_label": "Lojas Diversas",
        "store_title": "📦 Outros Estabelecimentos Onde Mais Gasta",
        "products_title": "📦 Outros Produtos Registrados",
        "comparison_title": "🔍 Comparador de Preços Diversos",
        "kpi_spent_label": "Total em Outros Itens",
        "kpi_stores_label": "Estabelecimentos Diversos"
    }
}

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
    def _extract_store_name(description: str, fallback_label: str = "Estabelecimento") -> str:
        """Extrai nome amigável do supermercado/posto/loja da descrição da transação"""
        if not description:
            return fallback_label
        clean = description.strip()
        # Remove prefixos comuns
        clean = re.sub(
            r"^(?:compra(?:s)?\s+(?:no|na|em|de)?|pagamento\s+(?:no|na|em|de)?|abastecimento\s+(?:no|na|em|de)?|combust[ií]vel\s+(?:no|na|em|de)?)\s*",
            "", clean, flags=re.IGNORECASE
        ).strip()
        return clean.title() if clean else fallback_label

    @staticmethod
    def resolve_item_segment(
        item_name: str,
        item_category: str = "",
        tx_desc: str = "",
        tx_category_name: str = ""
    ) -> tuple[str, str, str, str, str]:
        """
        Classifica o item e a transação em uma das macro categorias:
        Retorna (segment_key, segment_name, display_subcategory, badge_color, icon)
        """
        n = (item_name or "").lower()
        c = (item_category or "").lower()
        d = (tx_desc or "").lower()
        tc = (tx_category_name or "").lower()

        # 1. Combustível & Postos
        fuel_words = [
            "gasolina", "etanol", "diesel", "gnv", "combustivel", "combustível",
            "abastecimento", "arla 32", "aditivo combustivel", "v-power", "podium"
        ]
        fuel_stores = [
            "posto ", "shell", "ipiranga", "petrobras", "br distribuidora",
            "ale combustiveis", "ale postos", "auto posto"
        ]
        if (
            any(w in n for w in fuel_words)
            or any(w in d for w in fuel_stores)
            or "combustivel" in tc
            or "combustível" in tc
            or ("transporte" in tc and any(w in d for w in ["posto", "gasolina", "combustivel", "etanol", "diesel"]))
        ):
            if "etanol" in n:
                sub = "Etanol"
            elif "diesel" in n:
                sub = "Diesel S10/S500"
            elif any(w in n for w in ["aditiv", "podium", "v-power", "grid"]):
                sub = "Gasolina Aditivada"
            elif "gasolina" in n:
                sub = "Gasolina Comum"
            elif "gnv" in n:
                sub = "GNV"
            elif any(w in n for w in ["oleo", "óleo", "lubrificante"]):
                sub = "Lubrificantes & Pista"
            else:
                sub = "Combustíveis & Posto"
            meta = MACRO_SEGMENTS["combustivel"]
            return meta["key"], meta["name"], sub, meta["color"], meta["icon"]

        # 2. Tintas, Construção & Reforma
        paint_words = [
            "tinta", "tintas", "verniz", "esmalte", "massa corrida", "massa acrilica", "massa acrílica",
            "selante", "pu 40", "pu40", "silicone", "pincel", "trincha", "rolo de la", "rolo de lã",
            "rolo espuma", "rolo pintura", "thinner", "aguarras", "aguarrás", "solvente", "lixa ", "lixas",
            "cimento", "argamassa", "rejunte", "tijolo", "gesso", "drywall", "suvinil", "coral",
            "sherwin", "renner", "resina", "impermeabilizante", "primer", "fita crepe"
        ]
        paint_stores = [
            "tintas", "materiais e construcao", "materiais e construção", "cooperativa agropecuaria",
            "cooperativa agropecuária", "leroy merlin", "telhanorte", "c&c", "construcao", "construção",
            "reforma", "tintas mc", "darka", "madeireira", "ferragem"
        ]
        if (
            any(w in n for w in paint_words)
            or any(w in d for w in paint_stores)
            or "construcao" in tc
            or "construção" in tc
            or "reforma" in tc
            or "materiais" in tc
            or "tintas" in c
        ):
            if any(w in n for w in ["tinta", "suvinil", "coral", "sherwin", "acrilica", "acrílica", "latex"]):
                sub = "Tintas Imobiliárias"
            elif any(w in n for w in ["verniz", "esmalte"]):
                sub = "Vernizes & Esmaltes"
            elif any(w in n for w in ["massa", "selante", "pu 40", "pu40", "silicone", "rejunte"]):
                sub = "Massas & Selantes"
            elif any(w in n for w in ["pincel", "trincha", "rolo"]):
                sub = "Pincéis & Acessórios"
            elif any(w in n for w in ["thinner", "solvente", "aguarras"]):
                sub = "Solventes & Diluentes"
            elif any(w in n for w in ["lixa"]):
                sub = "Lixas & Abrasivos"
            elif any(w in n for w in ["cimento", "argamassa", "tijolo", "gesso"]):
                sub = "Alvenaria & Construção"
            else:
                sub = "Materiais & Tintas"
            meta = MACRO_SEGMENTS["tintas_reforma"]
            return meta["key"], meta["name"], sub, meta["color"], meta["icon"]

        # 3. Farmácia & Saúde
        pharma_words = [
            "vitamina", "dipirona", "paracetamol", "ibuprofeno", "remedio", "remédio", "medicamento",
            "protetor solar", "antialergico", "antialérgico", "antibiotico", "antibiótico", "analgesico",
            "analgésico", "anti-inflamatorio", "anti-inflamatório", "curativo", "band-aid", "soro",
            "xarope", "colirio", "colírio", "pomada", "fralda", "termometro", "termômetro"
        ]
        pharma_stores = [
            "farmacia", "farmácia", "drogaria", "drogasil", "panvel", "pague menos", "sao paulo",
            "são paulo", "raia", "droga raia", "drogaria sp"
        ]
        if (
            any(w in n for w in pharma_words)
            or any(w in d for w in pharma_stores)
            or "saúde" in tc
            or "saude" in tc
            or "farmácia" in tc
            or "farmacia" in tc
            or "farmacia" in c
            or "farmácia" in c
        ):
            if any(w in n for w in ["vitamina", "suplemento", "whey"]):
                sub = "Vitaminas & Suplementos"
            elif any(w in n for w in ["protetor solar", "shampoo", "sabonete", "creme", "desodorante"]):
                sub = "Higiene & Cuidados"
            elif any(w in n for w in ["fralda", "lenco", "lenço"]):
                sub = "Mamãe & Bebê"
            else:
                sub = "Medicamentos"
            meta = MACRO_SEGMENTS["farmacia"]
            return meta["key"], meta["name"], sub, meta["color"], meta["icon"]

        # 4. Veicular & Autopeças
        vehicle_words = [
            "oleo 5w", "oleo 0w", "oleo 10w", "oleo 15w", "oleo motor", "óleo motor",
            "filtro de oleo", "filtro de ar", "filtro de combustivel", "pastilha de freio",
            "disco de freio", "amortecedor", "pneu", "alinhamento", "balanceamento", "bateria veiculo"
        ]
        vehicle_stores = [
            "autopeças", "auto peças", "oficina", "mecanica", "mecânica", "auto center", "borracharia"
        ]
        if any(w in n for w in vehicle_words) or any(w in d for w in vehicle_stores) or "veicular" in tc or "veículo" in tc:
            if any(w in n for w in ["oleo", "óleo"]):
                sub = "Óleos & Lubrificantes"
            elif "filtro" in n:
                sub = "Filtros"
            elif "pneu" in n:
                sub = "Pneus & Rodas"
            elif "freio" in n or "pastilha" in n:
                sub = "Freios & Suspensão"
            else:
                sub = "Peças & Manutenção"
            meta = MACRO_SEGMENTS["veicular"]
            return meta["key"], meta["name"], sub, meta["color"], meta["icon"]

        # 5. Supermercado & Alimentação
        market_words = [
            "arroz", "feijao", "feijão", "leite", "cafe", "café", "picanha", "carne", "frango",
            "maca", "maçã", "banana", "tomate", "queijo", "sabao", "sabão", "detergente", "pao", "pão",
            "azeite", "acucar", "açúcar", "biscoito", "muffin", "refresco", "panettone", "mussarela",
            "presunto", "iogurte", "alface", "cebola", "alho", "batata", "refrigerante", "cerveja",
            "suco", "agua", "água", "macarrao", "macarrão", "farinha"
        ]
        market_stores = [
            "mercado", "supermercado", "atacad", "angeloni", "bistek", "condor", "pao de acucar",
            "pão de açúcar", "superviza", "zornitta", "fort atacadista", "muffato", "carrefour", "assai", "cooper"
        ]
        known_market_cats = [
            "mercearia", "hortifruti", "carnes & aves", "açougue", "laticínios & frios",
            "padaria", "padaria & sobremesas", "bebidas", "limpeza", "limpeza & casa", "higiene & beleza"
        ]
        if (
            any(w in n for w in market_words)
            or any(w in d for w in market_stores)
            or "supermercado" in tc
            or "alimentação" in tc
            or "alimentacao" in tc
            or c in known_market_cats
        ):
            if item_category and item_category != "Geral":
                sub = item_category
            elif any(w in n for w in ["carne", "picanha", "frango", "bisteca", "alcatra", "costela", "peixe"]):
                sub = "Carnes & Açougue"
            elif any(w in n for w in ["tomate", "banana", "maca", "maçã", "cebola", "batata", "alho", "laranja"]):
                sub = "Hortifruti"
            elif any(w in n for w in ["pao", "pão", "bolo", "muffin", "torta"]):
                sub = "Padaria & Confeitaria"
            elif any(w in n for w in ["queijo", "leite", "mussarela", "iogurte", "presunto"]):
                sub = "Laticínios & Frios"
            elif any(w in n for w in ["refrigerante", "suco", "cerveja", "vinho", "refresco", "agua", "água"]):
                sub = "Bebidas"
            elif any(w in n for w in ["detergente", "sabao", "sabão", "amaciante", "desinfetante", "limpeza"]):
                sub = "Limpeza & Casa"
            else:
                sub = "Mercearia"
            meta = MACRO_SEGMENTS["mercado"]
            return meta["key"], meta["name"], sub, meta["color"], meta["icon"]

        # 6. Fallback pelo nome da categoria da transação
        if "transporte" in tc:
            meta = MACRO_SEGMENTS["combustivel"]
            return meta["key"], meta["name"], "Combustíveis", meta["color"], meta["icon"]
        if "construcao" in tc or "materiais" in tc:
            meta = MACRO_SEGMENTS["tintas_reforma"]
            return meta["key"], meta["name"], "Materiais & Construção", meta["color"], meta["icon"]
        if "saude" in tc or "saúde" in tc:
            meta = MACRO_SEGMENTS["farmacia"]
            return meta["key"], meta["name"], "Farmácia & Saúde", meta["color"], meta["icon"]
        if "alimentacao" in tc or "alimentação" in tc:
            meta = MACRO_SEGMENTS["mercado"]
            return meta["key"], meta["name"], "Alimentação & Mercado", meta["color"], meta["icon"]

        # 7. Outros
        meta = MACRO_SEGMENTS["outros"]
        return meta["key"], meta["name"], item_category or "Diversos", meta["color"], meta["icon"]

    @staticmethod
    def get_top_consumed_items(
        db: Session,
        workspace_id: int,
        limit: int = 15,
        sort_by: str = "spent",  # 'spent' ou 'quantity'
        year: Optional[int] = None,
        month: Optional[int] = None,
        category_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Retorna ranking dos produtos mais consumidos / comprados no workspace.
        Permite filtrar por categoria (macro segmento) e ordenar por gasto ou quantidade.
        """
        query = db.query(
            TransactionItem, Transaction, Category
        ).join(
            Transaction, TransactionItem.transaction_id == Transaction.id
        ).outerjoin(
            Category, Transaction.category_id == Category.id
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
        for item, tx, cat in results:
            cat_name = cat.name if cat else ""
            seg_key, seg_name, subcat, color, icon = MarketAnalyticsService.resolve_item_segment(
                item.name, item.category or "", tx.description or "", cat_name
            )

            # Filtro por macro segmento se especificado
            if category_filter and category_filter != "all" and seg_key != category_filter:
                continue

            norm_name = MarketAnalyticsService._normalize_item_name(item.name)
            store_name = MarketAnalyticsService._extract_store_name(tx.description)

            if norm_name not in grouped:
                grouped[norm_name] = {
                    "name": norm_name,
                    "segment_key": seg_key,
                    "segment_name": seg_name,
                    "category": subcat,
                    "badge_color": color,
                    "icon": icon,
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
            avg_price = (data["total_spent"] / data["total_quantity"]) if data["total_quantity"] > 0 else (
                sum(data["prices"]) / len(data["prices"]) if data["prices"] else 0.0
            )
            items_list.append({
                "name": data["name"],
                "segment_key": data["segment_key"],
                "segment_name": data["segment_name"],
                "category": data["category"],
                "badge_color": data["badge_color"],
                "icon": data["icon"],
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
        month: Optional[int] = None,
        category_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Retorna ranking dos estabelecimentos (supermercados, postos, lojas de tintas, farmácias)
        onde o usuário mais gasta, refinado por categoria.
        """
        query = db.query(Transaction, Category).outerjoin(
            Category, Transaction.category_id == Category.id
        ).filter(
            Transaction.workspace_id == workspace_id,
            Transaction.type == "expense"
        )

        if year:
            query = query.filter(extract('year', Transaction.transaction_date) == int(year))
        if month:
            query = query.filter(extract('month', Transaction.transaction_date) == int(month))

        tx_list = query.order_by(Transaction.transaction_date.desc()).all()

        stores = {}
        for tx, cat in tx_list:
            cat_name = cat.name if cat else ""

            # Se a transação tem itens, avalia os itens
            if tx.items and len(tx.items) > 0:
                matching_items = []
                for it in tx.items:
                    seg_key, seg_name, subcat, color, icon = MarketAnalyticsService.resolve_item_segment(
                        it.name, it.category or "", tx.description or "", cat_name
                    )
                    if not category_filter or category_filter == "all" or seg_key == category_filter:
                        matching_items.append((it, seg_key, seg_name, subcat, color, icon))

                if not matching_items:
                    continue

                # Determina o segmento predominante
                primary_seg = matching_items[0][1]
                store_name = MarketAnalyticsService._extract_store_name(tx.description)

                if store_name not in stores:
                    meta = MACRO_SEGMENTS.get(primary_seg, MACRO_SEGMENTS["outros"])
                    stores[store_name] = {
                        "store_name": store_name,
                        "segment_key": primary_seg,
                        "segment_name": meta["name"],
                        "icon": meta["icon"],
                        "badge_color": meta["color"],
                        "total_spent": 0.0,
                        "transaction_count": 0,
                        "total_items_count": 0,
                        "last_visit": tx.transaction_date.strftime("%d/%m/%Y") if tx.transaction_date else "",
                        "items": {}
                    }

                items_sum = sum(
                    it.total_price if it.total_price > 0 else ((it.quantity or 1.0) * (it.unit_price or 0.0))
                    for it, *_ in matching_items
                )
                stores[store_name]["total_spent"] += items_sum
                stores[store_name]["transaction_count"] += 1
                stores[store_name]["total_items_count"] += len(matching_items)

                for it, _, _, sub, _, _ in matching_items:
                    i_name = it.name.strip().title()
                    if i_name not in stores[store_name]["items"]:
                        stores[store_name]["items"][i_name] = {
                            "name": i_name,
                            "quantity": 0.0,
                            "unit": it.unit or "un",
                            "total_spent": 0.0
                        }
                    stores[store_name]["items"][i_name]["quantity"] += (it.quantity or 1.0)
                    tot = it.total_price if it.total_price > 0 else ((it.quantity or 1.0) * (it.unit_price or 0.0))
                    stores[store_name]["items"][i_name]["total_spent"] += tot

            else:
                # Transação sem itens (ex: Combustível Posto Shell R$ 180)
                seg_key, seg_name, subcat, color, icon = MarketAnalyticsService.resolve_item_segment(
                    "", "", tx.description or "", cat_name
                )
                if category_filter and category_filter != "all" and seg_key != category_filter:
                    continue

                # Se o filtro for 'all', só inclui transações de segmentos típicos de compras/consumo
                if (not category_filter or category_filter == "all") and seg_key not in ["mercado", "combustivel", "tintas_reforma", "farmacia", "veicular"]:
                    continue

                store_name = MarketAnalyticsService._extract_store_name(tx.description)
                if store_name not in stores:
                    meta = MACRO_SEGMENTS.get(seg_key, MACRO_SEGMENTS["outros"])
                    stores[store_name] = {
                        "store_name": store_name,
                        "segment_key": seg_key,
                        "segment_name": meta["name"],
                        "icon": meta["icon"],
                        "badge_color": meta["color"],
                        "total_spent": 0.0,
                        "transaction_count": 0,
                        "total_items_count": 0,
                        "last_visit": tx.transaction_date.strftime("%d/%m/%Y") if tx.transaction_date else "",
                        "items": {}
                    }

                stores[store_name]["total_spent"] += tx.amount
                stores[store_name]["transaction_count"] += 1

        ranking = []
        for s in stores.values():
            ticket_medio = s["total_spent"] / s["transaction_count"] if s["transaction_count"] > 0 else 0.0
            items_arr = sorted(s["items"].values(), key=lambda x: x["total_spent"], reverse=True)
            for it in items_arr:
                it["total_spent"] = round(it["total_spent"], 2)
                it["quantity"] = round(it["quantity"], 2)

            ranking.append({
                "store_name": s["store_name"],
                "segment_key": s["segment_key"],
                "segment_name": s["segment_name"],
                "icon": s["icon"],
                "badge_color": s["badge_color"],
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
        search_term: Optional[str] = None,
        category_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Compara o preço do mesmo item entre diferentes estabelecimentos (mercados, postos, lojas de tintas).
        Identifica onde foi comprado mais barato, mais caro e variação %.
        """
        query = db.query(
            TransactionItem, Transaction, Category
        ).join(
            Transaction, TransactionItem.transaction_id == Transaction.id
        ).outerjoin(
            Category, Transaction.category_id == Category.id
        ).filter(
            Transaction.workspace_id == workspace_id
        )

        if search_term and search_term.strip():
            query = query.filter(TransactionItem.name.ilike(f"%{search_term.strip()}%"))

        results = query.order_by(Transaction.transaction_date.desc()).all()

        products = {}
        for item, tx, cat in results:
            cat_name = cat.name if cat else ""
            seg_key, seg_name, subcat, color, icon = MarketAnalyticsService.resolve_item_segment(
                item.name, item.category or "", tx.description or "", cat_name
            )

            # Filtro de macro categoria
            if category_filter and category_filter != "all" and seg_key != category_filter:
                continue

            norm_name = MarketAnalyticsService._normalize_item_name(item.name)
            store_name = MarketAnalyticsService._extract_store_name(tx.description)

            if norm_name not in products:
                products[norm_name] = {
                    "product_name": norm_name,
                    "segment_key": seg_key,
                    "segment_name": seg_name,
                    "category": subcat,
                    "badge_color": color,
                    "icon": icon,
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
                "segment_key": data["segment_key"],
                "segment_name": data["segment_name"],
                "category": data["category"],
                "badge_color": data["badge_color"],
                "icon": data["icon"],
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
        Detecta a unidade comercial padrão brasileira (kg, l, pct, cx, lata, tubo, un) e categoria
        com base no nome do produto (Supermercado, Combustível, Tintas & Reforma, Farmácia, Autopeças).
        Retorna (unidade, categoria, dica_ao_usuario).
        """
        if not product_name:
            return "un", "Geral", None

        p = product_name.lower().strip()

        # Combustíveis (L / Litros na Bomba)
        fuel_keywords = [
            "gasolina", "etanol", "diesel", "gnv", "combustivel", "combustível",
            "aditivo combustivel", "arla 32", "gasolina comum", "gasolina aditivada", "podium", "v-power"
        ]
        for fk in fuel_keywords:
            if fk in p:
                return "l", "Combustíveis", f"💡 *{product_name.title()}* é medido em *Litros (L)* na bomba."

        # Tintas, Construção & Reforma
        paint_keywords = [
            "tinta", "tintas", "verniz", "esmalte", "massa corrida", "massa acrilica", "selante",
            "pu 40", "pu40", "silicone", "thinner", "aguarras", "aguarrás", "solvente", "cimento",
            "argamassa", "rejunte", "suvinil", "coral", "sherwin", "latex", "resina"
        ]
        for pk in paint_keywords:
            if pk in p:
                unit = "lata" if any(w in p for w in ["tinta", "verniz", "esmalte"]) else (
                    "tubo" if any(w in p for w in ["selante", "pu", "silicone"]) else (
                        "cx" if "massa" in p else "un"
                    )
                )
                return unit, "Tintas & Construção", f"💡 *{product_name.title()}* classificado em *Tintas & Construção*."

        # Ferramentas de pintura
        paint_tools = ["pincel", "trincha", "rolo de la", "rolo de lã", "rolo espuma", "rolo pintura", "lixa", "espátula", "bandeja"]
        for pt in paint_tools:
            if pt in p:
                return "un", "Tintas & Construção", f"💡 Acessório de pintura classificado em *Tintas & Construção*."

        # Farmácia & Medicamentos
        pharma_keywords = [
            "dipirona", "paracetamol", "ibuprofeno", "vitamina", "remedio", "remédio", "medicamento",
            "antialergico", "antialérgico", "antibiotico", "antibiótico", "analgesico", "analgésico",
            "curativo", "pomada", "xarope", "fralda", "soro", "colirio", "colírio"
        ]
        for phk in pharma_keywords:
            if phk in p:
                return "cx", "Farmácia & Saúde", f"💡 Produto classificado em *Farmácia & Saúde*."

        # Veicular & Peças
        veh_keywords = ["oleo 5w", "oleo 0w", "oleo 10w", "filtro de oleo", "filtro de ar", "pastilha de freio", "pneu"]
        for vk in veh_keywords:
            if vk in p:
                unit = "l" if "oleo" in vk else "un"
                return unit, "Veicular & Autopeças", f"💡 Item veicular classificado em *Veicular & Autopeças*."

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
        estimado e unidade correta ao montar Lista de Mercado ou Lançamento.
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
