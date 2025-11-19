# ============================================
# DOKPLOY CONFIGURATION REQUISE
# ============================================
# Mounts:
#   - Type: Volume mount
#   - Name: logs_data
#   - Container path: /app/app/log
#
# Environment variables:
#   - APP_NAME="Prospection System - Backend"
#   - DEBUG=true
#   - HOST=0.0.0.0
#   - PORT=8000
#   - JWT_SECRET_KEY (générer avec: openssl rand -hex 32)
#   - JWT_ALGORITHM=HS256
#   - JWT_EXPIRATION_HOURS=24
#   - ADMIN_TOKEN (générer avec: openssl rand -hex 32)
#   - PRODUCTION=false
#   - DB_HOST=postgres
#   - DB_PORT=5432
#   - DB_NAME=prospection
#   - DB_USER=<user>
#   - DB_PASSWORD=<password>
#   - DB_PROD_URL=<url-if-prod>
#   - FRONTEND_URL=http://localhost:3000
#   - UNIPILE_DSN=<dsn>
#   - UNIPILE_API_KEY=<key>
#   - UNIPILE_ACCOUNT_ID=<id>
#   - OPENAI_API_KEY=<key>
#   - OPENAI_MODEL=gpt-4
#   - ANTHROPIC_API_KEY=<key>
#   - ANTHROPIC_MODEL=claude-3-opus-20240229
#   - CUTOFF_DAYS=30
#   - MAX_CONNECTIONS_PER_DAY=50
#   - REQUIRE_AVATAR=true
#   - MAX_BATCH_SIZE=10
#   - SCAN_INTERVAL=7200
#   - QUEUE_INTERVAL=1800
#   - MESSAGE_INTERVAL=1200
#   - DAILY_LIMIT_FIRST_CONTACT=50
#   - DAILY_LIMIT_FOLLOWUP_A1=30
#   - DAILY_LIMIT_FOLLOWUP_A2=30
#   - DAILY_LIMIT_FOLLOWUP_A3=30
#   - DAILY_LIMIT_FOLLOWUP_B=20
#   - DAILY_LIMIT_FOLLOWUP_C=10
#
# Ports:
#   - Container: 8000
#   - Public: Yes
# ============================================

FROM python:3.13.1-slim

# Installer dépendances système
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Créer user non-root
RUN useradd -m -u 1000 appuser

# Définir workdir
WORKDIR /app

# Copier requirements
COPY config/requirements.txt ./config/requirements.txt

# Installer dépendances Python
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r config/requirements.txt

# Créer dossier log avec bonnes permissions
RUN mkdir -p /app/app/log && \
    chown -R appuser:appuser /app/app/log

# Copier code source
COPY --chown=appuser:appuser . .

# Changer vers user non-root
USER appuser

# Exposer port
EXPOSE 8000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Mode dev : uvicorn avec hot-reload
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
