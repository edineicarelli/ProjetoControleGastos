import os
import json
import logging
import base64
import re
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import httpx
from app.config import settings
from app.schemas.ai_response import (
    AIParsedResult, ExtractedTransaction, ExtractedReminder, 
    ExtractedGoalAction, ExtractedVehicleAction, ExtractedTransfer
)
from app.utils import format_currency_br, format_number_br

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Você é o cérebro financeiro do Bot de Gestão Financeira Inteligente no Telegram.
Sua missão é analisar mensagens dos usuários (texto livre, transcrição de áudios de voz ou fotos de cupons/recibos/notas fiscais) e extrair os dados financeiros estruturados.

Você deve responder RIGOROSAMENTE em formato JSON com as chaves:
- `intent`: Uma das opções: 'transaction_record', 'account_transfer', 'reminder_create', 'goal_action', 'vehicle_action', 'shopping_action', 'financial_query', 'profile_switch', 'general_chat'
- `transactions`: Lista de transações encontradas: [{"type": "expense" ou "income", "amount": float, "description": str, "category_name": str, "payment_method": str, "date_offset_days": int}]
- `transfer`: Se for account_transfer (transferência entre contas, bancos, dinheiro, saques, depósitos): {"from_account": str (conta devedora/origem), "to_account": str (conta credora/destino), "amount": float, "description": str}
- `reminder`: Se for reminder_create: {"title": str, "amount": float, "type": "to_pay" ou "to_receive", "due_date": "YYYY-MM-DD", "recurrence": "none"|"monthly"|"weekly"}
- `goal`: Se for goal_action: {"action": "deposit"|"create"|"check", "goal_name": str, "amount": float}
- `vehicle`: Se for vehicle_action: {"type": "fuel"|"oil_change"|"revision"|"repair"|"odometer", "description": str, "amount": float, "km": float, "next_due_km": float ou null}
- `shopping`: Se for shopping_action: {"items": [{"name": str, "quantity": float, "unit": str, "estimated_price": float}]}
- `target_profile`: Se for profile_switch: "personal" ou "business" ou "family"
- `friendly_response`: Resposta amigável e elegante em português com emojis e markdown do Telegram. Sempre formate valores monetários no padrão brasileiro Real: R$ 1.250,00 (vírgula para decimais e ponto para milhares).
"""

class AIService:
    def __init__(self):
        self.api_key = settings.GEMINI_API_KEY
        self.models = [
            "gemini-3.1-flash-lite",
            "gemini-3.5-flash",
            "gemini-3.7-flash",
            "gemini-flash-latest"
        ]

    def is_gemini_active(self) -> bool:
        return bool(self.api_key and self.api_key != "SUA_GEMINI_API_KEY_AQUI")

    async def _call_gemini(self, parts: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Executa a chamada HTTP assíncrona para a API do Gemini com failover automático de modelos"""
        if not self.is_gemini_active():
            return None

        payload = {
            "system_instruction": {
                "parts": [{"text": SYSTEM_PROMPT}]
            },
            "contents": [{
                "parts": parts
            }],
            "generationConfig": {
                "responseMimeType": "application/json"
            }
        }

        async with httpx.AsyncClient(timeout=25.0) as client:
            for model_name in self.models:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={self.api_key}"
                try:
                    response = await client.post(url, json=payload)
                    if response.status_code == 200:
                        data = response.json()
                        raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
                        return json.loads(raw_text)
                    else:
                        logger.warning(f"Modelo {model_name} retornou status {response.status_code}. Tentando próximo modelo...")
                except Exception as e:
                    logger.warning(f"Exceção no modelo {model_name}: {e}. Tentando próximo modelo...")

        return None

    async def parse_text(self, text: str, user_context: Optional[Dict[str, Any]] = None) -> AIParsedResult:
        """Analisa mensagem de texto usando Gemini ou Fallback"""
        if self.is_gemini_active():
            context_str = f"Data atual: {datetime.now().strftime('%Y-%m-%d %H:%M')}\nContexto: {json.dumps(user_context or {}, ensure_ascii=False)}"
            prompt = f"{context_str}\nMensagem do usuário: \"{text}\""
            
            gemini_json = await self._call_gemini([{"text": prompt}])
            if gemini_json:
                try:
                    return AIParsedResult.model_validate(gemini_json)
                except Exception as e:
                    logger.error(f"Erro ao validar schema do Gemini: {e}")

        return self._fallback_parse_text(text)

    async def parse_audio(self, audio_file_path: str, user_context: Optional[Dict[str, Any]] = None) -> AIParsedResult:
        """Analisa arquivo de áudio de voz do Telegram enviando como dado base64 inline"""
        if self.is_gemini_active() and os.path.exists(audio_file_path):
            try:
                with open(audio_file_path, "rb") as f:
                    audio_b64 = base64.b64encode(f.read()).decode("utf-8")

                mime_type = "audio/ogg"
                if audio_file_path.endswith(".mp3"):
                    mime_type = "audio/mp3"
                elif audio_file_path.endswith(".wav"):
                    mime_type = "audio/wav"

                context_str = f"Data atual: {datetime.now().strftime('%Y-%m-%d %H:%M')}\nContexto: {json.dumps(user_context or {}, ensure_ascii=False)}"
                parts = [
                    {
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": audio_b64
                        }
                    },
                    {
                        "text": f"{context_str}\n\nTranscreva esta mensagem de voz e extraia os dados financeiros estruturados."
                    }
                ]

                gemini_json = await self._call_gemini(parts)
                if gemini_json:
                    return AIParsedResult.model_validate(gemini_json)
            except Exception as e:
                logger.error(f"Erro ao processar áudio: {e}")

        return AIParsedResult(
            intent="general_chat",
            friendly_response="🎙️ *Áudio recebido!* Não foi possível transcrever no momento."
        )

    async def parse_receipt_image(self, image_file_path: str, user_context: Optional[Dict[str, Any]] = None) -> AIParsedResult:
        """Analisa foto de nota fiscal / comprovante / cupom usando OCR Multimodal do Gemini"""
        if self.is_gemini_active() and os.path.exists(image_file_path):
            try:
                with open(image_file_path, "rb") as f:
                    img_b64 = base64.b64encode(f.read()).decode("utf-8")

                mime_type = "image/jpeg"
                if image_file_path.lower().endswith(".png"):
                    mime_type = "image/png"

                context_str = f"Data atual: {datetime.now().strftime('%Y-%m-%d')}\nContexto: {json.dumps(user_context or {}, ensure_ascii=False)}"
                prompt_ocr = (
                    f"{context_str}\n\n"
                    f"Você é um especialista em OCR e leitura inteligente de cupons fiscais brasileiros, NFC-e, SAT, DANFE, "
                    f"recibos de maquininha (Cielo, Stone, Rede, PagSeguro) e comprovantes de PIX / transferência.\n\n"
                    f"Analise a imagem com extrema atenção:\n"
                    f"1. Identifique o Nome do Estabelecimento (ex: 'Supermercado X', 'Posto Y', 'Farmácia Z').\n"
                    f"2. Identifique o VALOR TOTAL PAGO (procure por 'TOTAL R$', 'VALOR A PAGAR', 'VALOR TOTAL', 'VALOR LÍQUIDO', 'VALOR:', 'PAGAMENTO').\n"
                    f"3. Identifique a forma de pagamento ou banco (ex: Pix, Cartão de Crédito, Débito, Dinheiro, Banco do Brasil, Caixa, Santander, Nubank).\n"
                    f"4. Categorize a despesa (Alimentação, Transporte, Saúde, Moradia, etc.).\n"
                    f"5. Retorne RIGOROSAMENTE o JSON com intent 'transaction_record' e a transação preenchida."
                )
                parts = [
                    {
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": img_b64
                        }
                    },
                    {
                        "text": prompt_ocr
                    }
                ]

                gemini_json = await self._call_gemini(parts)
                if gemini_json:
                    return AIParsedResult.model_validate(gemini_json)
            except Exception as e:
                logger.error(f"Erro ao processar imagem: {e}")

        return AIParsedResult(
            intent="general_chat",
            friendly_response="📸 *Foto recebida!* Não foi possível ler os dados do comprovante no momento."
        )

    def _fallback_parse_text(self, text: str) -> AIParsedResult:
        """Parser inteligente baseado em regras para contingência com suporte a todos os módulos"""
        text_lower = text.lower().strip()

        # 1. Troca de perfis
        if "perfil pj" in text_lower or "conta pj" in text_lower or ("empresa" in text_lower and "mudar" in text_lower):
            return AIParsedResult(
                intent="profile_switch",
                target_profile="business",
                friendly_response="🏢 Alternando para o perfil **Pessoa Jurídica (PJ)**."
            )
        if "perfil pf" in text_lower or "conta pf" in text_lower or ("pessoal" in text_lower and "mudar" in text_lower):
            return AIParsedResult(
                intent="profile_switch",
                target_profile="personal",
                friendly_response="👤 Alternando para o perfil **Pessoal (PF)**."
            )

        # 2. Consultas de saldo / relatórios
        if any(w in text_lower for w in ["saldo", "quanto tenho", "extrato", "gastos do mes", "resumo"]):
            return AIParsedResult(
                intent="financial_query",
                friendly_response="📊 Consultando seu resumo financeiro..."
            )

        # 3. Transferência entre contas / saques / depósitos
        is_transfer = any(w in text_lower for w in [
            "transferir", "transferi", "transferência", "transferencia", 
            "saquei", "sacar", "saque", "depositei", "depositar", "depósito", "deposito"
        ]) or (("pix" in text_lower or "mandei" in text_lower or "passei" in text_lower) and any(p in text_lower for p in [" pro ", " para ", " pra ", " p/ "]))

        if is_transfer:
            val_match = re.search(r"(?:r\$\s*|valor\s*(?:de)?\s*|de\s*)?(\d+(?:[.,]\d{1,2})?)", text_lower)
            all_nums = re.findall(r"(\d+(?:[.,]\d{1,2})?)", text)
            valor = float(all_nums[-1].replace(",", ".")) if all_nums else 0.0

            known_banks = ["banco do brasil", "santander", "nubank", "caixa", "itaú", "itau", "inter", "bradesco", "poupança", "poupanca", "dinheiro", "carteira", "especie", "bb", "nu"]
            
            from_acc = "Conta"
            to_acc = "Conta"

            if any(w in text_lower for w in ["saquei", "sacar", "saque"]):
                to_acc = "Dinheiro"
                for b in known_banks:
                    if b in text_lower and b not in ["dinheiro", "carteira", "especie"]:
                        from_acc = b.title()
                        break
            elif any(w in text_lower for w in ["depositei", "depositar", "depósito", "deposito"]):
                from_acc = "Dinheiro"
                for b in known_banks:
                    if b in text_lower and b not in ["dinheiro", "carteira", "especie"]:
                        to_acc = b.title()
                        break
            else:
                # Procura padrões "do [A] para [B]" ou "[A] pro [B]"
                found_banks = []
                for b in known_banks:
                    if b in text_lower and not any(b in existing for existing in found_banks):
                        found_banks.append(b)
                found_banks.sort(key=lambda b: text_lower.find(b))
                if len(found_banks) >= 2:
                    from_acc = found_banks[0].title()
                    to_acc = found_banks[1].title()
                elif len(found_banks) == 1:
                    from_acc = found_banks[0].title()
                    to_acc = "Dinheiro"


            return AIParsedResult(
                intent="account_transfer",
                transfer=ExtractedTransfer(
                    from_account=from_acc,
                    to_account=to_acc,
                    amount=valor,
                    description="Transferência entre contas"
                ),
                friendly_response=f"🔄 *Transferência:* *{format_currency_br(valor)}* de *{from_acc}* para *{to_acc}*."
            )

        # 4. Módulo Veicular (Troca de óleo, manutenção, KM, combustível com KM)
        if any(w in text_lower for w in ["óleo", "oleo", "troquei óleo", "troca de óleo", "troca de oleo", "revisão", "revisao", "manutenção", "manutencao"]):
            # Extrai KM (ex: "174566 km" ou "km 174566" ou número grande)
            km_match = re.search(r"(?:km\s*)?(\d{4,6})(?:\s*km)?", text_lower)
            km_val = float(km_match.group(1)) if km_match else 0.0

            # Extrai valor em dinheiro (ex: "876,50", "valor de 300", "r$ 250")
            val_match = re.search(r"(?:r\$\s*|valor\s*(?:de)?\s*|por\s*)(\d+(?:[.,]\d{1,2})?)", text_lower)
            if not val_match:
                # Procura número decimal ou número diferente do KM
                all_nums = re.findall(r"(\d+(?:[.,]\d{1,2})?)", text)
                nums_float = [float(n.replace(",", ".")) for n in all_nums]
                val_candidates = [n for n in nums_float if n != km_val and n < 50000]
                valor = val_candidates[-1] if val_candidates else 0.0
            else:
                valor = float(val_match.group(1).replace(",", "."))

            return AIParsedResult(
                intent="vehicle_action",
                vehicle=ExtractedVehicleAction(
                    type="oil_change" if ("óleo" in text_lower or "oleo" in text_lower) else "revision",
                    description="Troca de Óleo e Filtros" if ("óleo" in text_lower or "oleo" in text_lower) else "Manutenção do Veículo",
                    amount=valor,
                    km=km_val,
                    next_due_km=km_val + 10000.0 if km_val > 0 else None
                ),
                friendly_response=f"🚗 *Registro Veicular Salvo!*\n🛠️ Ação: *Troca de Óleo*\n📟 Odômetro: *{format_number_br(km_val)} km* (Próxima troca em: *{format_number_br(km_val + 10000)} km*)\n💰 Valor: *{format_currency_br(valor)}*"
            )

        # 4. Metas e Caixinhas (Criar, Adicionar, Guardar)
        if any(w in text_lower for w in ["meta", "caixinha", "guardar", "guardei", "depositei", "reservei"]):
            is_create = any(w in text_lower for w in ["nova meta", "adicionar meta", "adiciona meta", "criar meta"])
            val_match = re.search(r"(\d+(?:[.,]\d{1,2})?)", text)
            valor = float(val_match.group(1).replace(",", ".")) if val_match else 0.0

            # Nome da meta
            nome_meta = "Reserva"
            meta_match = re.search(r"(?:meta|caixinha|pra|para|de)\s+([a-zA-ZÀ-ÿ\s]+)", text)
            if meta_match:
                clean_name = meta_match.group(1).strip().title()
                if clean_name and not clean_name.startswith("De ") and len(clean_name) > 2:
                    nome_meta = clean_name.replace("De ", "").replace("E Caixinha", "").strip()

            return AIParsedResult(
                intent="goal_action",
                goal=ExtractedGoalAction(
                    action="create" if is_create else "deposit",
                    goal_name=nome_meta,
                    amount=valor
                ),
                friendly_response=f"🎯 *Meta {nome_meta} atualizada!* Valor: *{format_currency_br(valor)}*."
            )

        # 5. Lembretes e Contas a Vencer
        if any(w in text_lower for w in ["lembrar", "vencimento", "vence", "conta de", "pagar internet", "pagar luz", "pagar aluguel", "pagar condomínio"]):
            # Extrai dia
            dia_match = re.search(r"(?:dia\s*)(\d{1,2})", text_lower)
            dia = int(dia_match.group(1)) if dia_match else datetime.now().day

            # Extrai valor
            val_match = re.search(r"(?:valor\s*(?:de)?\s*|r\$\s*)(\d+(?:[.,]\d{1,2})?)", text_lower)
            if not val_match:
                all_nums = [float(n.replace(",", ".")) for n in re.findall(r"(\d+(?:[.,]\d{1,2})?)", text)]
                val_candidates = [n for n in all_nums if int(n) != dia]
                valor = val_candidates[0] if val_candidates else 0.0
            else:
                valor = float(val_match.group(1).replace(",", "."))

            # Nome da conta
            title = "Conta Agendada"
            tit_match = re.search(r"(?:lembrar\s+(?:de\s+)?pagar|pagar|conta\s+de)\s+([a-zA-ZÀ-ÿ\s]+?)(?:\s+dia|\s+no\s+valor|\s+de\s+\d|$)", text_lower)
            if tit_match:
                title = tit_match.group(1).strip().title()

            is_monthly = "cada mês" in text_lower or "todo mês" in text_lower or "mensal" in text_lower
            now = datetime.now()
            mes = now.month if dia >= now.day else (now.month % 12) + 1
            ano = now.year if dia >= now.day or mes > 1 else now.year + 1
            due_str = f"{ano}-{mes:02d}-{dia:02d}"

            return AIParsedResult(
                intent="reminder_create",
                reminder=ExtractedReminder(
                    title=title,
                    amount=valor,
                    due_date=due_str,
                    recurrence="monthly" if is_monthly else "none"
                ),
                friendly_response=f"⏰ *Lembrete Cadastrado!*\n📝 *{title}*\n💰 Valor: *{format_currency_br(valor)}*\n📅 Vencimento: *{dia:02d}/{mes:02d}*{' (Recorrente mensal)' if is_monthly else ''}."
            )

        # 6. Despesas e Receitas comuns
        all_nums = re.findall(r"(\d+(?:[.,]\d{1,2})?)", text)
        if all_nums:
            valor = float(all_nums[-1].replace(",", "."))
            is_income = any(w in text_lower for w in ["recebi", "ganhei", "salário", "salario", "freela", "pix recebido", "venda", "entrada"])

            cat = "Outros"
            if any(w in text_lower for w in ["almoço", "almoco", "jantar", "lanche", "mercado", "padaria", "comida", "pizza", "hamburguer", "restaurante"]):
                cat = "Alimentação"
            elif any(w in text_lower for w in ["uber", "gasolina", "combustivel", "combustível", "onibus", "metrô", "pedagio", "estacionamento"]):
                cat = "Transporte"
            elif any(w in text_lower for w in ["aluguel", "luz", "agua", "água", "internet", "condominio", "condomínio", "gas", "gás"]):
                cat = "Moradia"
            elif any(w in text_lower for w in ["farmacia", "farmácia", "remedio", "remédio", "medico", "médico", "dentista", "consulta"]):
                cat = "Saúde"
            elif is_income:
                cat = "Salário" if ("salario" in text_lower or "salário" in text_lower) else "Receitas"

            pagamento = "Pix"
            if "credito" in text_lower or "crédito" in text_lower:
                pagamento = "Cartão de Crédito"
            elif "debito" in text_lower or "débito" in text_lower:
                pagamento = "Cartão de Débito"
            elif "dinheiro" in text_lower:
                pagamento = "Dinheiro"

            offset = -1 if "ontem" in text_lower else 0
            tipo_icon = "🟢 Entrada" if is_income else "🔴 Saída"

            return AIParsedResult(
                intent="transaction_record",
                transactions=[
                    ExtractedTransaction(
                        type="income" if is_income else "expense",
                        amount=valor,
                        description=text.capitalize(),
                        category_name=cat,
                        payment_method=pagamento,
                        date_offset_days=offset
                    )
                ],
                friendly_response=f"{tipo_icon}: *{format_currency_br(valor)}* ({cat}) via *{pagamento}* registrado com sucesso!"
            )

        return AIParsedResult(
            intent="general_chat",
            friendly_response="👋 Olá! Envie uma despesa, receita, áudio de voz ou foto de comprovante para eu registrar automaticamente!"
        )

ai_service = AIService()
