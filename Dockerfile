# ========================================================
# Dockerfile - Sistema de Controle Financeiro Inteligente
# ========================================================
FROM python:3.11-slim

# Evita criação de arquivos .pyc e buffer de saída
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=America/Sao_Paulo

WORKDIR /app

# Instala dependências do sistema necessárias (curl para healthcheck, ffmpeg para áudio, tzdata)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ffmpeg \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# Instala dependências Python
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copia código fonte
COPY . /app

# Cria diretórios persistentes para banco e uploads
RUN mkdir -p /app/data /app/uploads/audio /app/uploads/receipts /app/uploads/exports /app/uploads/documents

# Expõe porta do Dashboard Web
EXPOSE 8085

# Healthcheck para monitoramento no Portainer
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8085/dashboard || exit 1

# Comando de inicialização (FastAPI + Bot Telegram + APScheduler)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8085"]
