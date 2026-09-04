from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Literal

class ExtractedTransaction(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: Literal["expense", "income"] = Field(..., description="'expense' para gastos/despesas, 'income' para receitas/ganhos/entradas/salário")
    amount: float = Field(..., description="Valor numérico monetário em reais (ex: 45.90)")
    description: str = Field(..., description="Descrição resumida da despesa ou receita (ex: 'Almoço no restaurante', 'Salário mensal')")
    category_name: str = Field("Outros", description="Nome da categoria sugerida (ex: Alimentação, Transporte, Saúde, Moradia, Salário, Lazer, etc.)")
    payment_method: str = Field("Cartão de Crédito", description="Forma de pagamento inferida ou informada: Pix, Cartão de Crédito, Cartão de Débito, Dinheiro, Boleto, etc.")
    date_offset_days: int = Field(0, description="Diferença de dias em relação a hoje: 0 para hoje, -1 para ontem, -2 para anteontem, etc.")

class ExtractedReminder(BaseModel):
    model_config = ConfigDict(extra="ignore")
    title: str = Field(..., description="Nome da conta ou lembrete (ex: 'Conta de Luz', 'Aluguel', 'Fatura Cartão')")
    amount: float = Field(0.0, description="Valor da conta a pagar ou a receber, se houver")
    type: Literal["to_pay", "to_receive"] = Field("to_pay", description="'to_pay' para contas a pagar ou 'to_receive' para valores a receber")
    due_date: str = Field(..., description="Data de vencimento em formato YYYY-MM-DD ou DD/MM")
    recurrence: Literal["none", "monthly", "weekly", "yearly"] = Field("none", description="Recorrência da conta")

class ExtractedGoalAction(BaseModel):
    model_config = ConfigDict(extra="ignore")
    action: Literal["deposit", "create", "check"] = Field(..., description="'deposit' para guardar/aportar valor, 'create' para nova meta, 'check' para ver progresso")
    goal_name: str = Field(..., description="Nome da meta (ex: 'Reserva de Emergência', 'Viagem')")
    amount: float = Field(0.0, description="Valor a ser guardado ou valor alvo da meta")
    target_date: Optional[str] = Field(None, description="Data limite para a meta caso informada")

class ExtractedVehicleAction(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: Literal["fuel", "oil_change", "revision", "repair", "odometer"] = Field(..., description="Tipo de registro veicular")
    description: str = Field(..., description="Descrição da manutenção ou abastecimento")
    amount: float = Field(0.0, description="Valor gasto")
    km: float = Field(..., description="Quilometragem (KM) atual do veículo")
    next_due_km: Optional[float] = Field(None, description="KM da próxima troca/revisão se aplicável")

class ShoppingItemSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str = Field(..., description="Nome do item")
    quantity: float = Field(1.0, description="Quantidade")
    unit: str = Field("un", description="Unidade de medida")
    estimated_price: float = Field(0.0, description="Preço estimado unitário")

class ExtractedShoppingAction(BaseModel):
    model_config = ConfigDict(extra="ignore")
    items: List[ShoppingItemSchema] = Field(default_factory=list, description="Lista de itens de compra")

class ExtractedTransfer(BaseModel):
    model_config = ConfigDict(extra="ignore")
    from_account: str = Field(..., description="Nome da conta de origem/devedora (ex: 'Nubank', 'Dinheiro', 'Caixa', 'Santander', 'Banco do Brasil')")
    to_account: str = Field(..., description="Nome da conta de destino/credora (ex: 'Santander', 'Dinheiro', 'Carteira', 'Caixa', 'Nubank')")
    amount: float = Field(..., description="Valor monetário a transferir em reais (ex: 150.00)")
    description: Optional[str] = Field("Transferência entre contas", description="Descrição ou motivo da transferência")

class AIParsedResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intent: Literal[
        "transaction_record",      # Lançamento de despesa ou receita
        "account_transfer",        # Transferência entre contas/bancos/carteira/dinheiro
        "reminder_create",         # Criar lembrete de conta a pagar/receber
        "goal_action",             # Ações com metas/caixinhas
        "vehicle_action",          # Registro de manutenção ou abastecimento
        "shopping_action",         # Adicionar ou gerenciar lista de compras
        "financial_query",         # Pergunta sobre saldo, gastos do mês, etc.
        "profile_switch",          # Trocar entre PF e PJ
        "general_chat"             # Conversa geral, saudação ou pedido de ajuda
    ] = Field(..., description="Intenção principal detectada na mensagem do usuário")
    
    transactions: List[ExtractedTransaction] = Field(default_factory=list, description="Lista de transações encontradas")
    transfer: Optional[ExtractedTransfer] = Field(None, description="Detalhes de transferência caso intent seja account_transfer")
    reminder: Optional[ExtractedReminder] = Field(None, description="Detalhes de lembrete caso intent seja reminder_create")
    goal: Optional[ExtractedGoalAction] = Field(None, description="Detalhes da meta caso intent seja goal_action")
    vehicle: Optional[ExtractedVehicleAction] = Field(None, description="Detalhes veiculares caso intent seja vehicle_action")
    shopping: Optional[ExtractedShoppingAction] = Field(None, description="Detalhes de compras caso intent seja shopping_action")
    target_profile: Optional[Literal["personal", "business", "family"]] = Field(None, description="Perfil desejado se for profile_switch")
    
    friendly_response: str = Field(..., description="Resposta amigável em português confirmando a ação ou respondendo à dúvida do usuário com formatação bonita para Telegram")

