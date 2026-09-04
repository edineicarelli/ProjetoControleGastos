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
