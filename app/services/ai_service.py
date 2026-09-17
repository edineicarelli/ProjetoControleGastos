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
    AIParsedResult, ExtractedTransaction, ExtractedReminder, ExtractedReminderUpdate,
    ExtractedTransactionUpdate, ExtractedGoalAction, ExtractedVehicleAction, ExtractedTransfer
)
from app.utils import format_currency_br, format_number_br

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Você é o cérebro financeiro do Bot de Gestão Financeira Inteligente no Telegram.
Sua missão é analisar mensagens dos usuários (texto livre, transcrição de áudios de voz ou fotos de cupons/recibos/notas fiscais/PDFs) e extrair os dados financeiros estruturados com máxima precisão.

Você deve responder RIGOROSAMENTE em formato JSON com as chaves:
- `intent`: Uma das opções: 'transaction_record', 'transaction_update', 'account_transfer', 'reminder_create', 'reminder_update', 'goal_action', 'vehicle_action', 'shopping_action', 'financial_query', 'profile_switch', 'general_chat'
- `transactions`: Lista de transações encontradas se for transaction_record: [{"type": "expense" ou "income", "amount": float, "description": str, "category_name": str, "payment_method": str, "date_offset_days": int, "items": [{"name": str, "quantity": float, "unit": str, "unit_price": float, "total_price": float, "category": str}]}]
  OBSERVAÇÃO SOBRE ITENS E UNIDADE DE MEDIDA: Sempre que o comprovante/cupom fiscal/nota fiscal/PDF contiver detalhamento de produtos (ex: compras de mercado, farmácia, atacado, materiais, consumo detalhado), extraia na chave `items` cada produto individualmente com nome, quantidade, unidade, preço unitário e valor total.
  ATENÇÃO À UNIDADE COMERCIAL: Itens vendidos a granel ou por peso na balança (ex: Pão Francês, Pão de Sal, Pão de Queijo a peso, Queijo/Presunto fatiado, Carnes/Açougue/Frango/Peixe, Hortifruti/Frutas/Legumes/Verduras) SEMPRE devem ter a unidade `kg` (ou `g`), NUNCA `un`. Para produtos em embalagens fechadas use `un`, `pct`, `cx` ou `l`.
- `transaction_update`: Se for transaction_update (alterar/corrigir valor ou data de um lançamento/gasto/receita já efetivado no extrato): {"description_query": str (termo de busca como 'mercado', 'almoço', 'posto' ou 'ultimo'), "new_amount": float ou null, "new_date": "YYYY-MM-DD" ou null, "date_offset_days": int ou null (ex: -1 para ontem, 0 para hoje)}
- `transfer`: Se for account_transfer (transferência entre contas, bancos, dinheiro, saques, depósitos): {"from_account": str (conta devedora/origem), "to_account": str (conta credora/destino), "amount": float, "description": str}
- `reminder`: Se for reminder_create: {"title": str, "amount": float, "type": "to_pay" ou "to_receive", "due_date": "YYYY-MM-DD", "recurrence": "none"|"monthly"|"weekly"}
- `reminder_update`: Se for reminder_update (alterar/mudar/adiar a data de vencimento OU alterar valor de uma conta/lembrete/boleto existente): {"title": str, "new_due_date": "YYYY-MM-DD" ou null, "new_amount": float ou null}
- `goal`: Se for goal_action: {"action": "deposit"|"create"|"check", "goal_name": str, "amount": float}
- `vehicle`: Se for vehicle_action: {"type": "fuel"|"oil_change"|"revision"|"repair"|"odometer", "description": str, "amount": float, "km": float, "next_due_km": float ou null}
- `shopping`: Se for shopping_action: {"items": [{"name": str, "quantity": float, "unit": str, "estimated_price": float}]}
- `target_profile`: Se for profile_switch: "personal" ou "business" ou "family"
- `friendly_response`: Resposta amigável e elegante em português com emojis e markdown do Telegram. Sempre formate valores monetários no padrão brasileiro Real: R$ 1.250,00 (vírgula para decimais e ponto para milhares).
"""

class AIService:
    def __init__(self):
        self.models = [
            "gemini-flash-lite-latest",
            "gemini-3.1-flash-lite-preview",
            "gemini-3.6-flash",
            "gemini-3-flash-preview"
        ]
        self._client: Optional[httpx.AsyncClient] = None

    def get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(15.0, connect=5.0),
                limits=httpx.Limits(max_keepalive_connections=20, max_connections=50)
            )
        return self._client

    @property
    def api_key(self) -> str:
        return settings.GEMINI_API_KEY

    def is_gemini_active(self) -> bool:
        return bool(self.api_key and self.api_key != "SUA_GEMINI_API_KEY_AQUI")

    async def _call_gemini(self, parts: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Executa a chamada HTTP assíncrona para a API do Gemini com client pool e failover rápido"""
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

        client = self.get_client()
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

    def _is_clean_fast_path(self, text: str) -> bool:
        """Verifica se a mensagem é um comando financeiro direto e objetivo que pode ser processado instantaneamente"""
        text_clean = text.strip()
        words = text_clean.split()
        if len(words) > 12:
            return False  # Sentenças longas ou conversacionais vão para IA

        # Se tiver interrogação, provavelmente é pergunta que requer IA
        if "?" in text:
            return False

        # Verifica padrões simples de gasto ou receita: [descrição] [valor] [conta/forma]
        # Ex: "Almoço 40", "Gasolina 150 dinheiro", "Gastei 50 no mercado", "Recebi 1200 freela pix", "Salário 5000"
        has_number = bool(re.search(r"\d+(?:[.,]\d{1,2})?", text))
        if not has_number:
            return False

        return True

    async def parse_text(self, text: str, user_context: Optional[Dict[str, Any]] = None) -> AIParsedResult:
        """Analisa mensagem de texto usando Fast-Path instantâneo ou Gemini ultra-rápido com fallback"""
        # 1. Tenta Fast-Path local para resposta em < 5ms em comandos simples e objetivos
        if self._is_clean_fast_path(text):
            try:
                fast_result = self._fallback_parse_text(text)
                if fast_result and fast_result.intent != "general_chat":
                    return fast_result
            except Exception:
                pass

        # 2. Chama a IA Gemini com o modelo mais rápido e preciso
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
        if not self.is_gemini_active():
            return AIParsedResult(
                intent="general_chat",
                friendly_response=(
                    "⚠️ *Chave de IA (Google Gemini) não configurada.*\n\n"
                    "Para ler comprovantes e fotos automaticamente, configure sua chave no menu de configurações do painel web ou envie o gasto digitado."
                )
            )

        if os.path.exists(image_file_path):
            try:
                with open(image_file_path, "rb") as f:
                    img_b64 = base64.b64encode(f.read()).decode("utf-8")

                mime_type = "image/jpeg"
                lower_path = image_file_path.lower()
                if lower_path.endswith(".png"):
                    mime_type = "image/png"
                elif lower_path.endswith(".webp"):
                    mime_type = "image/webp"

                context_str = f"Data atual: {datetime.now().strftime('%Y-%m-%d')}\nContexto: {json.dumps(user_context or {}, ensure_ascii=False)}"
                prompt_ocr = (
                    f"{context_str}\n\n"
                    f"Você é um especialista em OCR e leitura inteligente de cupons fiscais brasileiros, NFC-e, SAT, DANFE, "
                    f"recibos de maquininha (Cielo, Stone, Rede, PagSeguro), comprovantes de PIX, transferências ou extratos.\n\n"
                    f"Analise a imagem com extrema atenção:\n"
                    f"1. Identifique o Nome do Estabelecimento ou Beneficiário (ex: 'Supermercado X', 'Posto Y', 'Farmácia Z', 'João Silva').\n"
                    f"2. Identifique o VALOR TOTAL PAGO (procure por 'TOTAL R$', 'VALOR A PAGAR', 'VALOR TOTAL', 'VALOR LÍQUIDO', 'VALOR:', 'PAGAMENTO', 'R$').\n"
                    f"3. Identifique a forma de pagamento ou banco (ex: Pix, Cartão de Crédito, Débito, Dinheiro, Banco do Brasil, Caixa, Santander, Nubank, Itaú, Bradesco, Inter).\n"
                    f"4. Categorize a despesa (Alimentação, Supermercado, Transporte, Saúde, Moradia, etc.) ou se for comprovante recebido marque como 'income'.\n"
                    f"5. DETALHAMENTO DE ITENS (MUITO IMPORTANTE): Se o cupom/recibo/nota contiver uma lista de produtos/itens comprados (ex: compras de supermercado, farmácia, atacado, restaurante detalhado, materiais), extraia CADA PRODUTO individualmente no array 'items' dentro da transação contendo:\n"
                    f"   - 'name': Nome legível e completo do produto\n"
                    f"   - 'quantity': Quantidade comprada (float, ex: 1.0, 2.5, 0.75)\n"
                    f"   - 'unit': Unidade comercial ('kg' para itens pesados na balança como pão francês, hortifruti, carnes e frios; 'un', 'pct', 'cx', 'l' para os demais)\n"
                    f"   - 'unit_price': Preço unitário em reais\n"
                    f"   - 'total_price': Preço total do item (quantity * unit_price)\n"
                    f"   - 'category': Categoria sugerida para o item (ex: 'Mercearia', 'Hortifruti', 'Carnes & Aves', 'Laticínios & Frios', 'Bebidas', 'Limpeza', 'Higiene & Beleza', 'Padaria', 'Farmácia', 'Geral')\n"
                    f"6. Se a imagem NÃO for um comprovante financeiro ou estiver ilegível/embaçada e não for possível encontrar o valor, retorne intent 'general_chat' com friendly_response explicando de forma clara e amigável que não conseguiu ler o comprovante e orientando o usuário a enviar uma foto mais nítida.\n"
                    f"7. Retorne RIGOROSAMENTE o JSON solicitado."
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
            friendly_response=(
                "❌ *Não consegui ler este comprovante/foto.*\n\n"
                "A imagem parece estar embaçada, cortada ou ilegível.\n\n"
                "💡 *Dicas para envio:*\n"
                "• Envie uma foto nítida e bem iluminada\n"
                "• Enquadre o **Valor Total** e o **Nome do Estabelecimento**\n"
                "• Se preferir, digite: `Mercado 150,00 no Cartão`"
            )
        )

    async def parse_document(self, document_file_path: str, mime_type: str = "application/pdf", user_context: Optional[Dict[str, Any]] = None) -> AIParsedResult:
        """Analisa documentos (PDF, notas fiscais eletrônicas, recibos em arquivo) usando Gemini Multimodal e pypdf"""
        caption = (user_context or {}).get("caption", "")
        extracted_pdf_text = ""

        if os.path.exists(document_file_path) and document_file_path.lower().endswith(".pdf"):
            try:
                import pypdf
                reader = pypdf.PdfReader(document_file_path)
                for page in reader.pages[:5]:
                    t = page.extract_text()
                    if t:
                        extracted_pdf_text += "\n" + t
            except Exception as e:
                logger.debug(f"pypdf extraction error: {e}")

        if self.is_gemini_active() and os.path.exists(document_file_path):
            try:
                with open(document_file_path, "rb") as f:
                    doc_b64 = base64.b64encode(f.read()).decode("utf-8")

                context_str = f"Data atual: {datetime.now().strftime('%Y-%m-%d')}\nContexto: {json.dumps(user_context or {}, ensure_ascii=False)}"
                if caption:
                    context_str += f"\nLegenda/Comentário enviado pelo usuário: \"{caption}\""

                pdf_text_prompt = ""
                if extracted_pdf_text:
                    pdf_text_prompt = f"\n\nTexto extraído do documento PDF:\n\"\"\"\n{extracted_pdf_text[:3000]}\n\"\"\"\n"

                prompt_doc = (
                    f"{context_str}{pdf_text_prompt}\n\n"
                    f"Você é um especialista em análise financeira e leitura de documentos brasileiros (PDFs de boletos bancários, contas de consumo como energia/luz/água/internet, faturas, DANFE, notas fiscais e comprovantes de transferência/Pix).\n\n"
                    f"Analise o documento e a legenda do usuário com extrema atenção:\n"
                    f"1. Se o documento for um BOLETO A PAGAR, CONTA DE CONSUMO (Luz/Energia/Água/Internet/Aluguel) OU se a legenda indicar que é uma conta a pagar/lembrete (ex: 'boleto a pagar de energia', 'lembrete de conta', 'pagar até dia X'):\n"
                    f"   - Retorne intent 'reminder_create' com:\n"
                    f"     - title: Nome da conta (ex: 'Conta de Energia', 'Boleto CPFL', 'Conta de Luz')\n"
                    f"     - amount: Valor total a pagar\n"
                    f"     - due_date: Data de vencimento no formato YYYY-MM-DD\n"
                    f"     - type: 'to_pay'\n"
                    f"     - recurrence: 'none' ou 'monthly' se for recorrente\n"
                    f"2. Se o documento for um COMPROVANTE DE PAGAMENTO JÁ REALIZADO, PIX EFETUADO, NOTA FISCAL (DANFE/NFC-e) OU CUPOM FISCAL:\n"
                    f"   - Retorne intent 'transaction_record' com o lançamento de despesa ou receita correspondente.\n"
                    f"   - DETALHAMENTO DE ITENS: Se o documento contiver produtos/itens discriminados (ex: DANFE, cupom de compras, mercado, farmácia), extraia CADA PRODUTO individualmente no array 'items' dentro da transação contendo: name, quantity, unit, unit_price, total_price e category.\n"
                    f"3. Se o documento for ilegível, protegido por senha ou sem dados financeiros, retorne intent 'general_chat' explicando o problema de forma clara.\n"
                    f"4. Retorne RIGOROSAMENTE o JSON especificado."
                )

                parts = [
                    {
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": doc_b64
                        }
                    },
                    {
                        "text": prompt_doc
                    }
                ]

                gemini_json = await self._call_gemini(parts)
                if gemini_json:
                    return AIParsedResult.model_validate(gemini_json)
            except Exception as e:
                logger.error(f"Erro ao processar documento: {e}")

        # Fallback local se o Gemini falhar mas temos texto do PDF ou legenda
        if extracted_pdf_text or caption:
            combined_text = f"{caption}\n{extracted_pdf_text}"
            parsed_fallback = self._fallback_parse_document_text(combined_text)
            if parsed_fallback:
                return parsed_fallback

        return AIParsedResult(
            intent="general_chat",
            friendly_response=(
                "❌ *Não consegui ler as informações deste documento/arquivo.*\n\n"
                "O arquivo pode estar protegido por senha, corrompido ou sem dados financeiros legíveis.\n\n"
                "💡 *Sugestão:* Envie uma foto do comprovante ou digite os dados diretamente no chat."
            )
        )

    def _fallback_parse_document_text(self, text: str) -> Optional[AIParsedResult]:
        """Fallback baseado em regras para extrair boletos e faturas de texto de PDFs"""
        text_lower = text.lower()
        val_match = re.search(r"(?:total\s*(?:a\s*pagar)?|valor\s*(?:do\s*documento|cobrado|total|líquido)?|r\$)\s*[:.]?\s*(\d{1,3}(?:\.\d{3})*,\d{2}|\d+[.,]\d{2})", text_lower)
        if not val_match:
            val_match = re.search(r"(\d{1,3}(?:\.\d{3})*,\d{2})", text)

        valor = 0.0
        if val_match:
            v_str = val_match.group(1).replace(".", "").replace(",", ".")
            try:
                valor = float(v_str)
            except Exception:
                pass

        if valor <= 0:
            return None

        # Procura data de vencimento
        due_match = re.search(r"(?:vencimento|vence\s*(?:em|dia)?|data\s*de\s*vencimento)\s*[:.]?\s*(\d{2}/\d{2}/\d{4}|\d{2}/\d{2})", text_lower)
        now = datetime.now()
        due_str = f"{now.year}-{now.month:02d}-{now.day:02d}"
        if due_match:
            d_raw = due_match.group(1)
            parts = d_raw.split("/")
            if len(parts) == 3:
                due_str = f"{parts[2]}-{parts[1]}-{parts[0]}"
            elif len(parts) == 2:
                due_str = f"{now.year}-{parts[1]}-{parts[0]}"

        # Identifica título
        title = "Conta de Consumo"
        if any(w in text_lower for w in ["energia", "luz", "eletricidade", "enel", "copel", "cemig", "cpfl", "energisa", "equatorial", "neoenergia"]):
            title = "Conta de Energia"
        elif any(w in text_lower for w in ["água", "agua", "sabesp", "copasa", "sanepar", "saneago"]):
            title = "Conta de Água"
        elif any(w in text_lower for w in ["internet", "claro", "vivo", "tim", "fibra", "oi"]):
            title = "Conta de Internet"
        elif any(w in text_lower for w in ["boleto", "fatura", "cartão"]):
            title = "Boleto / Fatura"

        is_reminder = any(w in text_lower for w in ["a pagar", "boleto", "fatura", "vencimento", "vence", "lembrete"])
        if is_reminder:
            return AIParsedResult(
                intent="reminder_create",
                reminder=ExtractedReminder(
                    title=title,
                    amount=valor,
                    due_date=due_str,
                    type="to_pay",
                    recurrence="monthly" if any(w in text_lower for w in ["mensal", "todo mês"]) else "none"
                ),
                friendly_response=f"⏰ *Conta / Lembrete Cadastrado!*\n📝 *{title}*\n💰 Valor: *{format_currency_br(valor)}*\n📅 Vencimento: *{due_str}*."
            )
        else:
            return AIParsedResult(
                intent="transaction_record",
                transactions=[
                    ExtractedTransaction(
                        type="expense",
                        amount=valor,
                        description=title,
                        category_name="Moradia" if "Conta" in title else "Outros",
                        payment_method="Boleto",
                        date_offset_days=0
                    )
                ],
                friendly_response=f"🔴 Saída: *{format_currency_br(valor)}* ({title}) registrada com sucesso!"
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

        # 5. Alteração / Edição de Lançamentos Efetivados (Gastos/Receitas já registrados)
        is_reminder_term = any(w in text_lower for w in ["conta de", "boleto", "vencimento", "fatura", "conta da", "conta do", "lembrete", "luz", "água", "agua", "aluguel", "condomínio", "condominio", "internet"])
        is_tx_edit_keyword = any(w in text_lower for w in [
            "alterar valor", "mudar valor", "corrigir valor", "alterar data", "mudar data", "trocar data", "corrigir data",
            "alterar o valor", "mudar o valor", "corrigir o valor", "alterar a data", "mudar a data", "trocar a data",
            "editar valor", "editar lançamento", "editar gasto", "editar data", "alterar último", "alterar ultimo",
            "mudar último", "mudar ultimo", "corrigir último", "corrigir ultimo", "alterar lançamento", "mudar lançamento"
        ])

        if is_tx_edit_keyword and not is_reminder_term:
            # Extrai novo valor se informado
            new_val = None
            val_match = re.search(r"(?:para\s*(?:r\$\s*)?|r\$\s*)(\d+(?:[.,]\d{1,2})?)", text_lower)
            if val_match:
                try:
                    new_val = float(val_match.group(1).replace(",", "."))
                except Exception:
                    pass

            # Extrai nova data se informada
            now = datetime.now()
            new_date_str = None
            offset_days = None
            if "ontem" in text_lower:
                offset_days = -1
                dt = now - timedelta(days=1)
                new_date_str = dt.strftime("%Y-%m-%d")
            elif "hoje" in text_lower:
                offset_days = 0
                new_date_str = now.strftime("%Y-%m-%d")
            else:
                date_match = re.search(r"(\d{1,2}/\d{1,2}/\d{4}|\d{1,2}/\d{1,2})", text_lower)
                if date_match:
                    d_raw = date_match.group(1)
                    d_parts = d_raw.split("/")
                    if len(d_parts) == 3:
                        ano = int(d_parts[2]) if len(d_parts[2]) == 4 else 2000 + int(d_parts[2])
                        new_date_str = f"{ano:04d}-{int(d_parts[1]):02d}-{int(d_parts[0]):02d}"
                    elif len(d_parts) == 2:
                        d_day = int(d_parts[0])
                        d_month = int(d_parts[1])
                        d_year = now.year if (d_month > now.month or (d_month == now.month and d_day >= now.day)) else now.year + 1
                        new_date_str = f"{d_year:04d}-{d_month:02d}-{d_day:02d}"

            # Extrai termo de busca do lançamento
            search_query = "ultimo"
            query_match = re.search(r"(?:gasto\s+(?:d[aoe]\s+|no\s+|na\s+)?|compra\s+(?:d[aoe]\s+|no\s+|na\s+)?|lançamento\s+(?:d[aoe]\s+|no\s+|na\s+)?|valor\s+(?:d[aoe]\s+|no\s+|na\s+)?|data\s+(?:d[aoe]\s+|no\s+|na\s+)?)(.+?)(?:\s+para|\s+pr[ao]|$)", text_lower)
            if query_match:
                q = query_match.group(1).replace("último", "").replace("ultimo", "").replace("gasto", "").replace("lançamento", "").replace("compra", "").strip()
                if q and len(q) > 1:
                    search_query = q.title()

            return AIParsedResult(
                intent="transaction_update",
                transaction_update=ExtractedTransactionUpdate(
                    description_query=search_query,
                    new_amount=new_val,
                    new_date=new_date_str,
                    date_offset_days=offset_days
                ),
                friendly_response=f"✏️ Solicitação para editar lançamento *{search_query}*."
            )

        # 6. Alteração de Data de Vencimento ou Valor de Contas/Lembretes Existentes
        if any(w in text_lower for w in [
            "alterar vencimento", "mudar vencimento", "trocar vencimento", "adiar vencimento",
            "prorrogar vencimento", "postergar vencimento", "alterar a data de vencimento",
            "mudar a data de vencimento", "adiar conta", "adiar o boleto", "adiar boleto",
            "adiar fatura", "adiar o aluguel", "adiar aluguel", "prorrogar fatura", "prorrogar conta",
            "alterar data da conta", "mudar data da conta", "alterar valor da conta", "mudar valor da conta",
            "alterar valor do boleto", "mudar valor do boleto", "alterar valor da fatura", "mudar valor da fatura",
            "corrigir valor da conta", "corrigir valor do boleto", "corrigir valor da fatura"
        ]) or (is_tx_edit_keyword and is_reminder_term):
            # Extrai nova data se informada
            now = datetime.now()
            due_str = None
            date_match = re.search(r"(\d{1,2}/\d{1,2}/\d{4}|\d{1,2}/\d{1,2})", text_lower)
            if date_match:
                d_raw = date_match.group(1)
                d_parts = d_raw.split("/")
                if len(d_parts) == 3:
                    ano = int(d_parts[2]) if len(d_parts[2]) == 4 else 2000 + int(d_parts[2])
                    due_str = f"{ano:04d}-{int(d_parts[1]):02d}-{int(d_parts[0]):02d}"
                elif len(d_parts) == 2:
                    d_day = int(d_parts[0])
                    d_month = int(d_parts[1])
                    d_year = now.year if (d_month > now.month or (d_month == now.month and d_day >= now.day)) else now.year + 1
                    due_str = f"{d_year:04d}-{d_month:02d}-{d_day:02d}"
            elif "dia " in text_lower:
                dia_match = re.search(r"(?:dia\s*)(\d{1,2})", text_lower)
                if dia_match:
                    d_day = int(dia_match.group(1))
                    d_month = now.month if d_day >= now.day else (now.month % 12) + 1
                    d_year = now.year if d_day >= now.day or d_month > 1 else now.year + 1
                    due_str = f"{d_year:04d}-{d_month:02d}-{d_day:02d}"

            # Extrai novo valor se informado
            new_amount_val = None
            if "valor" in text_lower or "r$" in text_lower or "reais" in text_lower:
                val_m = re.search(r"(?:para\s*(?:r\$\s*)?|r\$\s*)(\d+(?:[.,]\d{1,2})?)", text_lower)
                if val_m:
                    try:
                        new_amount_val = float(val_m.group(1).replace(",", "."))
                    except Exception:
                        pass

            # Extrai nome da conta / termo de busca
            title = "Conta"
            tit_match = re.search(r"(?:vencimento\s+(?:d[aoe]\s+)?|adiar\s+(?:a\s+|o\s+)?|prorrogar\s+(?:a\s+|o\s+)?|mudar\s+(?:a\s+data\s+d[aoe]\s+|o\s+valor\s+d[aoe]\s+)?|alterar\s+(?:o\s+valor\s+d[aoe]\s+|a\s+data\s+d[aoe]\s+)?)(.+?)(?:\s+para\s+|\s+pr[ao]\s+|$)", text_lower)
            if tit_match:
                extracted_t = tit_match.group(1).replace("data de", "").replace("vencimento", "").replace("valor de", "").replace("valor da", "").replace("valor do", "").replace("da conta de", "").replace("do boleto", "").strip()
                if extracted_t and len(extracted_t) > 1:
                    title = extracted_t.title()

            return AIParsedResult(
                intent="reminder_update",
                reminder_update=ExtractedReminderUpdate(
                    title=title,
                    new_due_date=due_str,
                    new_amount=new_amount_val
                ),
                friendly_response=f"📅 Solicitação para alterar dados da conta *{title}*."
            )

        # 7. Lembretes e Contas a Vencer (Criação)
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
