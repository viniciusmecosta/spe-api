# Usa imagem oficial do Python leve
FROM python:3.11-slim

# Define variáveis de ambiente para evitar arquivos .pyc e buffering de logs
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Define diretório de trabalho
WORKDIR /app

# Instala dependências do sistema necessárias para compilar alguns pacotes python (se necessário)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copia e instala dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o código da aplicação
COPY . .

# Cria diretório de uploads
RUN mkdir -p uploads

# Exposição da porta (documental)
EXPOSE 8000

# Script de entrada para rodar migrações e iniciar o app
COPY ./entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]