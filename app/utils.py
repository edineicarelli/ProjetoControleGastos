from typing import Any, List, Optional, Dict

def format_currency_br(value: float | int | None, with_symbol: bool = True) -> str:
    """
    Formata valores numéricos para o padrão de moeda brasileiro (BRL / Real).
    Exemplos:
      1250.5  -> 'R$ 1.250,50' (com símbolo) ou '1.250,50' (sem símbolo)
      -45.0   -> 'R$ -45,00'
      0       -> 'R$ 0,00'
    """
    if value is None:
        value = 0.0
    try:
        val = float(value)
    except (ValueError, TypeError):
        return f"R$ {value}" if with_symbol else str(value)
    
    formatted = f"{val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    
    if with_symbol:
        if formatted.startswith("-"):
            return f"R$ -{formatted[1:]}"
        return f"R$ {formatted}"
    return formatted


def format_number_br(value: float | int | None, decimals: int = 0) -> str:
    """
    Formata números com separadores pt-BR (ex: 50.000 ou 1.234,56).
    """
    if value is None:
        value = 0
    try:
        val = float(value)
    except (ValueError, TypeError):
        return str(value)
    
    if decimals == 0:
        return f"{int(round(val)):,}".replace(",", ".")
    else:
        return f"{val:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def format_items_list_text(items: list, max_items: int = 25) -> str:
    """
    Formata lista de itens de uma transação / cupom fiscal para apresentação clara e elegante no Telegram.
    """
    if not items:
        return ""

    lines = [f"\n🧾 *Itens do Cupom Fiscal ({len(items)} produtos):*"]
    for idx, it in enumerate(items[:max_items], 1):
        name = getattr(it, "name", None) or (it.get("name") if isinstance(it, dict) else str(it))
        quantity = getattr(it, "quantity", None) if getattr(it, "quantity", None) is not None else (it.get("quantity", 1.0) if isinstance(it, dict) else 1.0)
        unit = getattr(it, "unit", None) or (it.get("unit", "un") if isinstance(it, dict) else "un")
        unit_price = getattr(it, "unit_price", None) if getattr(it, "unit_price", None) is not None else (it.get("unit_price", 0.0) if isinstance(it, dict) else 0.0)
        total_price = getattr(it, "total_price", None) if getattr(it, "total_price", None) is not None else (it.get("total_price", 0.0) if isinstance(it, dict) else 0.0)

        try:
            qty_num = float(quantity) if quantity is not None else 1.0
        except (ValueError, TypeError):
            qty_num = 1.0

        try:
            up_num = float(unit_price) if unit_price is not None else 0.0
        except (ValueError, TypeError):
            up_num = 0.0

        try:
            tot_num = float(total_price) if total_price is not None else 0.0
        except (ValueError, TypeError):
            tot_num = 0.0

        if tot_num <= 0 and up_num > 0:
            tot_num = qty_num * up_num

        if up_num > 0 and (qty_num != 1 or unit != "un"):
            unit_str = f" ({qty_num:g} {unit} x {format_currency_br(up_num)})"
        elif qty_num != 1 or unit != "un":
            unit_str = f" ({qty_num:g} {unit})"
        else:
            unit_str = ""

        tot_str = f" → *{format_currency_br(tot_num)}*" if tot_num > 0 else ""
        clean_name = str(name).replace("_", " ").replace("*", "").replace("[", "(").replace("]", ")").replace("`", "")
        lines.append(f"  *{idx}.* {clean_name}{unit_str}{tot_str}")

    if len(items) > max_items:
        lines.append(f"  _... e mais {len(items) - max_items} itens na lista completa._")

    return "\n" + "\n".join(lines)

def format_full_receipt_text(tx: Any, items: list, max_items: int = 35) -> str:
    """
    Formata os detalhes completos de um cupom fiscal / transação com itens para exibição no Telegram.
    """
    cat_name = tx.category.name if getattr(tx, "category", None) else "Mercado"
    acc_name = tx.account.name if getattr(tx, "account", None) else (getattr(tx, "payment_method", "Outro") or "Outro")
    date_str = tx.transaction_date.strftime("%d/%m/%Y") if getattr(tx, "transaction_date", None) else ""
    clean_desc = str(tx.description).replace("_", " ").replace("*", "")

    lines = [
        f"🧾 *Cupom Fiscal - {clean_desc}*",
        f"💰 *Valor Total:* {format_currency_br(tx.amount)} | 📅 *Data:* {date_str}",
        f"💳 *Conta/Pagamento:* {acc_name} | 🏷️ *Categoria:* {cat_name}",
        "───────────────────"
    ]

    if not items:
        lines.append("ℹ️ _Nenhum item individual discriminado para este lançamento._")
        return "\n".join(lines)

    for idx, it in enumerate(items[:max_items], 1):
        name = getattr(it, "name", None) or (it.get("name") if isinstance(it, dict) else str(it))
        quantity = getattr(it, "quantity", None) if getattr(it, "quantity", None) is not None else (it.get("quantity", 1.0) if isinstance(it, dict) else 1.0)
        unit = getattr(it, "unit", None) or (it.get("unit", "un") if isinstance(it, dict) else "un")
        unit_price = getattr(it, "unit_price", None) if getattr(it, "unit_price", None) is not None else (it.get("unit_price", 0.0) if isinstance(it, dict) else 0.0)
        total_price = getattr(it, "total_price", None) if getattr(it, "total_price", None) is not None else (it.get("total_price", 0.0) if isinstance(it, dict) else 0.0)
        cat = getattr(it, "category", None) or (it.get("category", "") if isinstance(it, dict) else "")

        try:
            qty_num = float(quantity) if quantity is not None else 1.0
        except (ValueError, TypeError):
            qty_num = 1.0

        try:
            up_num = float(unit_price) if unit_price is not None else 0.0
        except (ValueError, TypeError):
            up_num = 0.0

        try:
            tot_num = float(total_price) if total_price is not None else 0.0
        except (ValueError, TypeError):
            tot_num = 0.0

        if tot_num <= 0 and up_num > 0:
            tot_num = qty_num * up_num

        if up_num > 0 and (qty_num != 1 or unit != "un"):
            unit_str = f" ({qty_num:g} {unit} x {format_currency_br(up_num)})"
        elif qty_num != 1 or unit != "un":
            unit_str = f" ({qty_num:g} {unit})"
        else:
            unit_str = ""

        tot_str = f" → *{format_currency_br(tot_num)}*" if tot_num > 0 else ""
        cat_str = f" `[{cat}]`" if cat and cat not in ["Geral", "Outros", ""] else ""
        clean_name = str(name).replace("_", " ").replace("*", "").replace("[", "(").replace("]", ")").replace("`", "")
        lines.append(f"*{idx}.* {clean_name}{unit_str}{tot_str}{cat_str}")

    if len(items) > max_items:
        lines.append(f"\n_... e mais {len(items) - max_items} itens na lista completa._")

    lines.append("───────────────────")
    lines.append(f"📊 *Total de Produtos:* {len(items)} itens discriminados")
    return "\n".join(lines)


