# 💎 Sistema de Gestão Financeira Inteligente (Telegram + IA)

Plataforma completa de gestão e controle financeiro baseada em **Telegram Bot**, **Inteligência Artificial Multimodal (Google Gemini 2.0 / 1.5 Flash)** e **Dashboard Web Interativo / Telegram Mini App**, inspirada no modelo do Nivoro.

---

## 🌟 Funcionalidades Principais

### 1. 🤖 Registro em Linguagem Natural & Multimodal (Telegram)
- **Texto Livre**: Interpreta gastos ou receitas em linguagem coloquial (ex: *"Gastei 45 no almoço no cartão"*, *"Recebi 3500 de salário no pix"*).
- **Áudios de Voz**: Envie mensagens de voz diretamente no Telegram; a IA transcreve e extrai os lançamentos financeiros automaticamente.
- **Leitura de Recibos & Cupons Fiscais (OCR)**: Envie fotos de comprovantes e cupons fiscais para identificar estabelecimento, data, itens e valor total.

### 2. 📊 Dashboard Web & Telegram Mini App
- Visual moderno com **Glassmorphism**, suporte a modo escuro e paleta harmônica.
- **Gráficos Dinâmicos com Chart.js**: Gastos por categoria (Doughnut) e Fluxo de Caixa Mensal (Bar).
- **Índice de Saúde Financeira**: Cálculo automático de score e status do mês.
- **Exportação de Relatórios**: Download instantâneo em **Excel (.xlsx)** e **PDF (.pdf)**.
- Compatível como **Telegram Mini App** (abre direto no chat do Telegram).

### 3. 👤 / 🏢 Separação de Perfis (PF / PJ / Múltiplas Contas)
- Alterne entre **Pessoa Física (PF)** e **Empresa (PJ)** com um único clique no menu do Telegram ou no Dashboard Web.
- Cada workspace mantém categorias, relatórios, saldos e metas completamente isolados.

### 4. 👨‍👩‍👧‍👦 Conta Família / Gestão Compartilhada
- Compartilhamento de contas através de **Código de Convite**.
- Múltiplos membros registram lançamentos a partir de seus próprios celulares, sincronizados em tempo real.

### 5. ⏰ Controle de Vencimentos & Lembretes Automáticos
- Cadastro rápido: *"Lembrar de pagar internet 120 dia 10"*.
- Notificações automáticas programadas no Telegram antes do vencimento com botões interativos `[✅ Marcar como Pago]` e `[⏳ Adiar]`.

### 6. 🎯 Metas & Caixinhas Financeiras
- Objetivos de economia com progresso visual em texto e barras dinâmicas no painel.
- Lançamentos rápidos: *"Guardei 200 pra viagem"*.

### 7. 🚗 Módulo Veicular Integrado
- Histórico de manutenções, trocas de peças e abastecimentos.
- Alertas automáticos de **troca de óleo** e revisões periódicas com base no odômetro (KM).

### 8. 🛒 Lista de Mercado Inteligente
- Checklist dinâmico com preços estimados por item.
- Botão para **finalizar compra** e converter automaticamente a lista em despesa no fluxo de caixa.

---

## 🛠️ Tecnologias Utilizadas

- **Backend API**: Python 3, FastAPI, Uvicorn
- **Telegram Bot**: `python-telegram-bot` (modo assíncrono com polling ou webhook)
- **Inteligência Artificial**: `google-genai` (Gemini 2.0 Flash / 1.5 Flash com Structured Outputs e fallback inteligente)
- **Banco de Dados**: SQLAlchemy ORM (SQLite / PostgreSQL)
- **Agendamento de Notificações**: APScheduler
- **Frontend / Mini App**: HTML5, Vanilla CSS Glassmorphism, Chart.js, Jinja2
- **Exportações**: Pandas, OpenPyXL, ReportLab

---

## 🚀 Como Executar o Projeto

### 1. Pré-requisitos
Certifique-se de ter o Python 3.10+ instalado no seu sistema.

### 2. Configurar o arquivo `.env`
Abra o arquivo `.env` e preencha suas chaves:

```env
# Token obtido com o @BotFather no Telegram
TELEGRAM_BOT_TOKEN="123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ"

# Chave de API do Google Gemini (gratuita em https://aistudio.google.com)
GEMINI_API_KEY="AIzaSy..."

# Banco de Dados
DATABASE_URL="sqlite:///./finance_control.db"

# Configuração do Servidor Web
HOST="0.0.0.0"
PORT=8000
BASE_URL="http://localhost:8000"
```

### 3. Executar o Servidor & Bot
Execute com o ambiente virtual:

```bash
# Ativar o ambiente virtual
source venv/bin/activate

# Iniciar o sistema completo (FastAPI + Telegram Bot + APScheduler)
python -m app.main
```

O servidor estará disponível em:
- **Dashboard Web**: `http://localhost:8000/dashboard`
- **Documentação da API (Swagger)**: `http://localhost:8000/docs`

---

## 📱 Principais Comandos no Telegram

| Comando | Descrição |
| :--- | :--- |
| `/start` | Inicia o bot, cria os perfis (PF/PJ) e exibe o teclado rápido |
| `/saldo` | Exibe o resumo de receitas, despesas e saúde financeira do mês |
| `/extrato` | Lista os últimos lançamentos financeiros |
| `/perfil` | Alterna entre conta Pessoal (PF), Empresa (PJ) ou Família |
| `/lembretes` | Visualiza e gerencia contas a pagar/receber |
| `/metas` | Acompanha objetivos de economia e caixinhas |
| `/veiculo` | Consulta odômetro, manutenções e alertas de óleo |
| `/mercado` | Abre a lista de compras interativa |
| `/painel` | Envia o link de acesso direto ao Dashboard Web |
