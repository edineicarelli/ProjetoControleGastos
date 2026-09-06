import os
import datetime
from typing import Optional, List, Dict, Any
import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import extract, and_
from app.models import Transaction, Workspace, Account, Category
from app.config import settings
from app.utils import format_currency_br, format_number_br

class ExportService:
    @staticmethod
    def _get_filtered_data(
        db: Session,
        workspace_id: int,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        account_id: Optional[int] = None,
        tx_type: Optional[str] = "all",
        category_id: Optional[int] = None,
        top_expenses_limit: int = 5,
        include_comparison: bool = False
    ) -> Dict[str, Any]:
        """Filtra transações e calcula métricas, agrupamentos por categoria e rankings para exportação"""
        ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
        query = db.query(Transaction).filter(Transaction.workspace_id == workspace_id)

        # Filtro de datas
        dt_start = None
        dt_end = None
        if start_date:
            try:
                dt_start = datetime.datetime.strptime(start_date.strip(), "%Y-%m-%d")
                query = query.filter(Transaction.transaction_date >= dt_start)
            except Exception:
                pass

        if end_date:
            try:
                dt_end = datetime.datetime.strptime(end_date.strip(), "%Y-%m-%d")
                # Fim do dia selecionado (23:59:59)
                dt_end_full = dt_end.replace(hour=23, minute=59, second=59)
                query = query.filter(Transaction.transaction_date <= dt_end_full)
            except Exception:
                pass

        # Filtro de Conta
        selected_account = None
        if account_id and account_id > 0:
            query = query.filter(Transaction.account_id == account_id)
            selected_account = db.query(Account).filter(Account.id == account_id).first()

        # Filtro de Tipo (income / expense / all)
        if tx_type and tx_type in ["income", "expense"]:
            query = query.filter(Transaction.type == tx_type)

        # Filtro de Categoria
        selected_category = None
        if category_id and category_id > 0:
            query = query.filter(Transaction.category_id == category_id)
            selected_category = db.query(Category).filter(Category.id == category_id).first()

        txs = query.order_by(Transaction.transaction_date.desc(), Transaction.id.desc()).all()

        total_income = sum(t.amount for t in txs if t.type == "income")
        total_expense = sum(t.amount for t in txs if t.type == "expense")
        net_balance = total_income - total_expense

        # Taxa de Poupança e Saúde
        if total_income > 0:
            savings_rate = (net_balance / total_income) * 100
            if savings_rate >= 30:
                health_score = min(100, int(90 + (savings_rate - 30) * (10 / 70)))
                health_status = "Excelente 🌟"
            elif savings_rate >= 15:
                health_score = int(75 + (savings_rate - 15) * (14 / 15))
                health_status = "Boa 👍"
            elif savings_rate >= 0:
                health_score = int(55 + (savings_rate / 15) * 19)
                health_status = "Equilibrada ⚖️"
            elif savings_rate >= -30:
                health_score = max(30, int(50 + (savings_rate / 30) * 20))
                health_status = "Atenção (Déficit) ⚠️"
            else:
                health_score = max(10, int(30 + max(-20, (savings_rate + 30) * 0.2)))
                health_status = "Crítico (Alto Déficit) 🚨"
        else:
            if total_expense > 0:
                savings_rate = -100.0
                health_score = 30
                health_status = "Sem Receitas Registradas ⚠️"
            else:
                savings_rate = 0.0
                health_score = 100
                health_status = "Sem Movimentações ⚪"

        # Agrupamento por Categoria
        cat_totals: Dict[str, Dict[str, Any]] = {}
        for t in txs:
            if t.type == "expense":
                cname = t.category.name if t.category else "Sem Categoria"
                cicon = t.category.icon if t.category else "🏷️"
                if cname not in cat_totals:
                    cat_totals[cname] = {"name": cname, "icon": cicon, "total": 0.0, "count": 0}
                cat_totals[cname]["total"] += t.amount
                cat_totals[cname]["count"] += 1

        sorted_cats = sorted(list(cat_totals.values()), key=lambda x: x["total"], reverse=True)
        for c in sorted_cats:
            c["percentage"] = (c["total"] / total_expense * 100) if total_expense > 0 else 0.0

        # Top Maiores Despesas
        expenses_only = [t for t in txs if t.type == "expense"]
        top_expenses = sorted(expenses_only, key=lambda x: x.amount, reverse=True)[:top_expenses_limit]

        # Comparativo com período anterior (se solicitado)
        comparison = None
        if include_comparison and dt_start and dt_end:
            period_days = (dt_end - dt_start).days + 1
            prev_end = dt_start - datetime.timedelta(days=1)
            prev_start = prev_end - datetime.timedelta(days=period_days - 1)

            prev_query = db.query(Transaction).filter(
                Transaction.workspace_id == workspace_id,
                Transaction.transaction_date >= prev_start,
                Transaction.transaction_date <= prev_end.replace(hour=23, minute=59, second=59)
            )
            if account_id and account_id > 0:
                prev_query = prev_query.filter(Transaction.account_id == account_id)
            if tx_type and tx_type in ["income", "expense"]:
                prev_query = prev_query.filter(Transaction.type == tx_type)
            if category_id and category_id > 0:
                prev_query = prev_query.filter(Transaction.category_id == category_id)

            prev_txs = prev_query.all()
            prev_income = sum(t.amount for t in prev_txs if t.type == "income")
            prev_expense = sum(t.amount for t in prev_txs if t.type == "expense")
            prev_net = prev_income - prev_expense

            diff_income_pct = ((total_income - prev_income) / prev_income * 100) if prev_income > 0 else (100.0 if total_income > 0 else 0.0)
            diff_expense_pct = ((total_expense - prev_expense) / prev_expense * 100) if prev_expense > 0 else (100.0 if total_expense > 0 else 0.0)

            comparison = {
                "prev_period_label": f"{prev_start.strftime('%d/%m/%Y')} a {prev_end.strftime('%d/%m/%Y')}",
                "prev_income": prev_income,
                "prev_expense": prev_expense,
                "prev_net": prev_net,
                "diff_income_pct": round(diff_income_pct, 1),
                "diff_expense_pct": round(diff_expense_pct, 1)
            }

        # Label do Período
        if dt_start and dt_end:
            period_label = f"{dt_start.strftime('%d/%m/%Y')} até {dt_end.strftime('%d/%m/%Y')}"
        elif dt_start:
            period_label = f"A partir de {dt_start.strftime('%d/%m/%Y')}"
        elif dt_end:
            period_label = f"Até {dt_end.strftime('%d/%m/%Y')}"
        else:
            period_label = "Todo o Histórico"

        return {
            "workspace": ws,
            "transactions": txs,
            "total_income": total_income,
            "total_expense": total_expense,
            "net_balance": net_balance,
            "savings_rate": round(savings_rate, 1),
            "health_score": health_score,
            "health_status": health_status,
            "categories": sorted_cats,
            "top_expenses": top_expenses,
            "comparison": comparison,
            "period_label": period_label,
            "selected_account": selected_account,
            "selected_category": selected_category,
            "tx_type": tx_type
        }

    @staticmethod
    def export_to_excel(
        db: Session,
        workspace_id: int,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        account_id: Optional[int] = None,
        tx_type: Optional[str] = "all",
        category_id: Optional[int] = None,
        top_expenses_limit: int = 5,
        include_comparison: bool = False,
        include_metrics: bool = True
    ) -> str:
        """Exporta relatório customizado para Excel (.xlsx) com múltiplas abas formatadas"""
        data = ExportService._get_filtered_data(
            db=db,
            workspace_id=workspace_id,
            start_date=start_date,
            end_date=end_date,
            account_id=account_id,
            tx_type=tx_type,
            category_id=category_id,
            top_expenses_limit=top_expenses_limit,
            include_comparison=include_comparison
        )

        ws = data["workspace"]
        txs = data["transactions"]

        # 1. Tabela Principal de Lançamentos
        tx_rows = []
        for t in txs:
            acc_name = t.account.name if t.account else t.payment_method
            tx_rows.append({
                "ID": t.id,
                "Data": t.transaction_date.strftime("%d/%m/%Y %H:%M"),
                "Tipo": "Receita (Entrada)" if t.type == "income" else "Despesa (Saída)",
                "Descrição": t.description,
                "Categoria": t.category.name if t.category else "Outros",
                "Valor (R$)": t.amount if t.type == "income" else -t.amount,
                "Conta / Pagamento": acc_name,
                "Status": "Concluído" if t.status == "completed" else "Pendente",
                "Usuário": t.user.name if t.user else "Sistema"
            })

        df_tx = pd.DataFrame(tx_rows)

        # 2. Resumo por Categoria
        cat_rows = []
        for c in data["categories"]:
            cat_rows.append({
                "Categoria": c["name"],
                "Total Gasto (R$)": c["total"],
                "Qtd Lançamentos": c["count"],
                "Participação (%)": round(c["percentage"], 1)
            })
        df_cat = pd.DataFrame(cat_rows)

        # 3. Top Maiores Gastos
        top_rows = []
        for rank, t in enumerate(data["top_expenses"], 1):
            top_rows.append({
                "Posição": f"#{rank}",
                "Descrição": t.description,
                "Categoria": t.category.name if t.category else "Outros",
                "Data": t.transaction_date.strftime("%d/%m/%Y"),
                "Valor (R$)": t.amount,
                "Conta": t.account.name if t.account else t.payment_method
            })
        df_top = pd.DataFrame(top_rows)

        # 4. Resumo Executivo / KPIs
        kpi_rows = [
            {"Indicador": "Perfil / Workspace", "Valor": ws.name},
            {"Indicador": "Período Analisado", "Valor": data["period_label"]},
            {"Indicador": "Conta Filtrada", "Valor": data["selected_account"].name if data["selected_account"] else "Todas as Contas"},
            {"Indicador": "Tipo de Movimentação", "Valor": "Todas" if data["tx_type"] == "all" else ("Apenas Receitas" if data["tx_type"] == "income" else "Apenas Despesas")},
            {"Indicador": "Total de Entradas (Receitas)", "Valor": format_currency_br(data["total_income"])},
            {"Indicador": "Total de Saídas (Despesas)", "Valor": format_currency_br(data["total_expense"])},
            {"Indicador": "Saldo Líquido do Período", "Valor": format_currency_br(data["net_balance"])},
            {"Indicador": "Taxa de Poupança", "Valor": f"{data['savings_rate']}%"},
            {"Indicador": "Índice de Saúde Financeira", "Valor": f"{data['health_score']}/100 - {data['health_status']}"},
            {"Indicador": "Total de Lançamentos", "Valor": len(txs)}
        ]

        if data["comparison"]:
            comp = data["comparison"]
            kpi_rows.extend([
                {"Indicador": "--- COMPARATIVO COM PERÍODO ANTERIOR ---", "Valor": comp["prev_period_label"]},
                {"Indicador": "Receitas Anteriores", "Valor": format_currency_br(comp["prev_income"])},
                {"Indicador": "Variação de Receitas", "Valor": f"{comp['diff_income_pct']}%"},
                {"Indicador": "Despesas Anteriores", "Valor": format_currency_br(comp["prev_expense"])},
                {"Indicador": "Variação de Despesas", "Valor": f"{comp['diff_expense_pct']}%"},
                {"Indicador": "Saldo Líquido Anterior", "Valor": format_currency_br(comp["prev_net"])}
            ])

        df_kpi = pd.DataFrame(kpi_rows)

        # Salva o arquivo Excel
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"relatorio_{ws.name.replace(' ', '_')}_{timestamp}.xlsx"
        filepath = os.path.join(settings.UPLOAD_DIR, "exports", filename)

        with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
            df_kpi.to_excel(writer, index=False, sheet_name="Resumo Executivo")
            if not df_tx.empty:
                df_tx.to_excel(writer, index=False, sheet_name="Lançamentos Detalhados")
            if not df_cat.empty:
                df_cat.to_excel(writer, index=False, sheet_name="Gastos por Categoria")
            if not df_top.empty:
                df_top.to_excel(writer, index=False, sheet_name="Top Maiores Gastos")

        return filepath

    @staticmethod
    def export_to_pdf(
        db: Session,
        workspace_id: int,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        account_id: Optional[int] = None,
        tx_type: Optional[str] = "all",
        category_id: Optional[int] = None,
        top_expenses_limit: int = 5,
        include_comparison: bool = False,
        include_metrics: bool = True
    ) -> str:
        """Gera relatório financeiro executivo em PDF com tabelas, KPIs e ranking"""
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib import colors

        data = ExportService._get_filtered_data(
            db=db,
            workspace_id=workspace_id,
            start_date=start_date,
            end_date=end_date,
            account_id=account_id,
            tx_type=tx_type,
            category_id=category_id,
            top_expenses_limit=top_expenses_limit,
            include_comparison=include_comparison
        )

        ws = data["workspace"]
        txs = data["transactions"]

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"relatorio_{ws.name.replace(' ', '_')}_{timestamp}.pdf"
        filepath = os.path.join(settings.UPLOAD_DIR, "exports", filename)

        doc = SimpleDocTemplate(filepath, pagesize=letter, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
        elements = []
        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            'TitleStyle',
            parent=styles['Heading1'],
            fontSize=16,
            leading=20,
            textColor=colors.HexColor("#0f172a"),
            fontName="Helvetica-Bold"
        )

        sub_style = ParagraphStyle(
            'SubStyle',
            parent=styles['Normal'],
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#64748b")
        )

        section_title_style = ParagraphStyle(
            'SectionTitleStyle',
            parent=styles['Heading2'],
            fontSize=11,
            leading=14,
            textColor=colors.HexColor("#1e293b"),
            fontName="Helvetica-Bold",
            spaceAfter=6
        )

        # Cabeçalho do Relatório
        elements.append(Paragraph(f"<b>💎 Relatório Financeiro: {ws.name}</b>", title_style))
        elements.append(Paragraph(f"Período: <b>{data['period_label']}</b> • Gerado em: {datetime.datetime.now().strftime('%d/%m/%Y às %H:%M')}", sub_style))
        if data["selected_account"]:
            elements.append(Paragraph(f"Filtro de Conta: <b>{data['selected_account'].name}</b>", sub_style))
        elements.append(Spacer(1, 10))
        elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e2e8f0"), spaceAfter=12))

        # 1. Tabela de Indicadores / KPIs
        kpi_data = [
            ["🟢 Total Entradas", "🔴 Total Saídas", "⚖️ Saldo Líquido", "🩺 Saúde Financeira"],
            [
                format_currency_br(data["total_income"]),
                format_currency_br(data["total_expense"]),
                format_currency_br(data["net_balance"]),
                f"{data['health_score']}/100"
            ]
        ]
        kpi_table = Table(kpi_data, colWidths=[135, 135, 135, 135])
        kpi_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor("#475569")),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor("#f8fafc")),
            ('TEXTCOLOR', (0, 1), (0, 1), colors.HexColor("#10b981")),
            ('TEXTCOLOR', (1, 1), (1, 1), colors.HexColor("#f43f5e")),
            ('TEXTCOLOR', (2, 1), (2, 1), colors.HexColor("#4f46e5")),
            ('FONTNAME', (0, 1), (-1, 1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 1), (-1, 1), 11),
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor("#cbd5e1")),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(kpi_table)
        elements.append(Spacer(1, 15))

        # 2. Tabela de Comparativo (se ativo)
        if data["comparison"]:
            comp = data["comparison"]
            elements.append(Paragraph("<b>📊 Comparativo com Período Anterior</b>", section_title_style))
            comp_data = [
                ["Métrica", "Período Anterior", "Período Atual", "Variação (%)"],
                ["Receitas", format_currency_br(comp["prev_income"]), format_currency_br(data["total_income"]), f"{comp['diff_income_pct']}%"],
                ["Despesas", format_currency_br(comp["prev_expense"]), format_currency_br(data["total_expense"]), f"{comp['diff_expense_pct']}%"],
                ["Saldo Líquido", format_currency_br(comp["prev_net"]), format_currency_br(data["net_balance"]), "-"]
            ]
            comp_table = Table(comp_data, colWidths=[140, 130, 130, 140])
            comp_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#e0e7ff")),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor("#3730a3")),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 8.5),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('ALIGN', (0, 1), (0, -1), 'LEFT'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#c7d2fe")),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ]))
            elements.append(comp_table)
            elements.append(Spacer(1, 15))

        # 3. Top Maiores Gastos
        if data["top_expenses"]:
            elements.append(Paragraph(f"<b>🏆 Top {len(data['top_expenses'])} Maiores Despesas do Período</b>", section_title_style))
            top_data = [["Rank", "Descrição", "Categoria", "Data", "Conta", "Valor"]]
            for rank, t in enumerate(data["top_expenses"], 1):
                acc_name = t.account.name if t.account else t.payment_method
                cat_name = t.category.name if t.category else "Outros"
                top_data.append([
                    f"#{rank}",
                    t.description[:25],
                    cat_name[:15],
                    t.transaction_date.strftime("%d/%m/%Y"),
                    acc_name[:12],
                    format_currency_br(t.amount)
                ])
            top_table = Table(top_data, colWidths=[40, 160, 95, 75, 85, 85])
            top_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#fee2e2")),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor("#991b1b")),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('ALIGN', (-1, 0), (-1, -1), 'RIGHT'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#fecaca")),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ]))
            elements.append(top_table)
            elements.append(Spacer(1, 15))

        # 4. Lançamentos Detalhados
        elements.append(Paragraph(f"<b>📑 Lançamentos ({len(txs)} registros)</b>", section_title_style))
        table_data = [["Data", "Tipo", "Descrição", "Categoria", "Conta / Método", "Valor"]]
        for t in txs[:100]:  # Limita a 100 no PDF para fluidez
            tipo_label = "+ Entrada" if t.type == "income" else "- Saída"
            cat_name = t.category.name if t.category else "Outros"
            acc_name = t.account.name if t.account else t.payment_method
            val_str = format_currency_br(t.amount)
            table_data.append([
                t.transaction_date.strftime("%d/%m/%Y"),
                tipo_label,
                t.description[:25],
                cat_name[:15],
                acc_name[:15],
                val_str
            ])

        table = Table(table_data, colWidths=[65, 55, 160, 95, 85, 80])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#4f46e5")),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('ALIGN', (-1, 0), (-1, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8.5),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 5),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ('FONTSIZE', (0, 1), (-1, -1), 7.5),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")])
        ]))

        elements.append(table)
        doc.build(elements)
        return filepath
