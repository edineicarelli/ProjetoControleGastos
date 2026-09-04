import os
import datetime
import pandas as pd
from typing import Optional
from sqlalchemy.orm import Session
from app.models import Transaction, Workspace
from app.config import settings

class ExportService:
    @staticmethod
    def export_to_excel(db: Session, workspace_id: int) -> str:
        """Exporta todas as transações do workspace para um arquivo Excel .xlsx"""
        ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
        txs = db.query(Transaction).filter(Transaction.workspace_id == workspace_id).order_by(Transaction.transaction_date.desc()).all()

        data = []
        for t in txs:
            data.append({
                "ID": t.id,
                "Data": t.transaction_date.strftime("%d/%m/%Y %H:%M"),
                "Tipo": "Receita" if t.type == "income" else "Despesa",
                "Descrição": t.description,
                "Categoria": t.category.name if t.category else "Outros",
                "Valor (R$)": t.amount if t.type == "income" else -t.amount,
                "Forma de Pagamento": t.payment_method,
                "Status": t.status,
                "Usuário": t.user.name if t.user else "Sistema"
            })

        df = pd.DataFrame(data)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"extrato_{ws.name.replace(' ', '_')}_{timestamp}.xlsx"
        filepath = os.path.join(settings.UPLOAD_DIR, "exports", filename)

        with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Lançamentos")

        return filepath

    @staticmethod
    def export_to_pdf(db: Session, workspace_id: int) -> str:
        """Gera um relatório financeiro resumido em PDF usando ReportLab"""
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib import colors

        ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
        txs = db.query(Transaction).filter(Transaction.workspace_id == workspace_id).order_by(Transaction.transaction_date.desc()).limit(50).all()

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"relatorio_{ws.name.replace(' ', '_')}_{timestamp}.pdf"
        filepath = os.path.join(settings.UPLOAD_DIR, "exports", filename)

        doc = SimpleDocTemplate(filepath, pagesize=letter)
        elements = []
        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            'TitleStyle',
            parent=styles['Heading1'],
            fontSize=18,
            leading=22,
            textColor=colors.HexColor("#1e293b")
        )

        elements.append(Paragraph(f"<b>Relatório Financeiro: {ws.name}</b>", title_style))
        elements.append(Paragraph(f"Gerado em: {datetime.datetime.now().strftime('%d/%m/%Y às %H:%M')}", styles['Normal']))
        elements.append(Spacer(1, 15))

        from app.utils import format_currency_br
        # Tabela de lançamentos
        table_data = [["Data", "Tipo", "Descrição", "Categoria", "Valor", "Pagamento"]]
        for t in txs:
            tipo_label = "+ Ent." if t.type == "income" else "- Saída"
            cat_name = t.category.name if t.category else "Outros"
            val_str = format_currency_br(t.amount)
            table_data.append([
                t.transaction_date.strftime("%d/%m/%Y"),
                tipo_label,
                t.description[:25],
                cat_name[:15],
                val_str,
                t.payment_method[:15]
            ])

        table = Table(table_data, colWidths=[65, 50, 150, 95, 75, 85])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#4f46e5")),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")])
        ]))

        elements.append(table)
        doc.build(elements)
        return filepath
