# db.py - Gestion de base de données asynchrone minimaliste

import asyncpg
import uuid
from config.config import settings

async def get_async_db_connection():
    """Retourne une connexion PostgreSQL asynchrone."""
    return await asyncpg.connect(
        host=settings.db_host,
        port=settings.db_port,
        database=settings.db_name,
        user=settings.db_user,
        password=settings.db_password
    )

async def init_db():
    """Crée la base de données et ses tables si elles n'existent pas."""
    try:
        conn = await get_async_db_connection()
    except Exception as e:
        print(f"⚠️  Database connection failed: {e}")
        print("⚠️  Running in demo mode without database")
        return

    try:
        # Table users
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                email VARCHAR UNIQUE NOT NULL,
                password_hash VARCHAR NOT NULL,
                first_name VARCHAR,
                last_name VARCHAR,
                role VARCHAR DEFAULT 'user' CHECK (role IN ('admin', 'user')),
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # Table password_reset_tokens
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                token VARCHAR NOT NULL UNIQUE,
                expires_at VARCHAR NOT NULL,
                is_used BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT NOW(),

                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            )
        """)

        # Table accounts (LinkedIn accounts)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                unipile_account_id VARCHAR UNIQUE NOT NULL,
                linkedin_url VARCHAR UNIQUE NOT NULL,
                first_name VARCHAR,
                last_name VARCHAR,
                headline VARCHAR,
                company VARCHAR,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),

                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_accounts_user ON accounts(user_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_accounts_unipile ON accounts(unipile_account_id)")

        # Table prospects
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS prospects (
                id SERIAL PRIMARY KEY,
                account_id INTEGER NOT NULL,
                linkedin_url VARCHAR UNIQUE NOT NULL,
                linkedin_identifier VARCHAR,
                unipile_invitation_id VARCHAR,
                first_name VARCHAR,
                last_name VARCHAR,
                company VARCHAR,
                job_title VARCHAR,
                headline VARCHAR,
                avatar_match BOOLEAN DEFAULT FALSE,
                status VARCHAR DEFAULT 'pending' CHECK (status IN ('pending', 'connected', 'rejected')),
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),

                FOREIGN KEY (account_id) REFERENCES accounts (id) ON DELETE CASCADE
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_prospects_account ON prospects(account_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_prospects_status ON prospects(status)")

        # Migration: ajouter colonnes manquantes si elles n'existent pas
        try:
            await conn.execute("ALTER TABLE prospects ADD COLUMN IF NOT EXISTS linkedin_identifier VARCHAR")
            await conn.execute("ALTER TABLE prospects ADD COLUMN IF NOT EXISTS unipile_invitation_id VARCHAR")
            await conn.execute("ALTER TABLE prospects ADD COLUMN IF NOT EXISTS headline VARCHAR")
            await conn.execute("ALTER TABLE prospects ADD COLUMN IF NOT EXISTS attendee_provider_id VARCHAR")
        except Exception as e:
            print(f"Migration warning (non-critical): {e}")

        # Table connections
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS connections (
                id SERIAL PRIMARY KEY,
                prospect_id INTEGER NOT NULL UNIQUE,
                account_id INTEGER NOT NULL,
                connection_date TIMESTAMP,
                initiated_by VARCHAR CHECK (initiated_by IN ('account', 'prospect')),
                status VARCHAR DEFAULT 'sent' CHECK (status IN ('sent', 'accepted', 'rejected')),
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),

                FOREIGN KEY (prospect_id) REFERENCES prospects (id) ON DELETE CASCADE,
                FOREIGN KEY (account_id) REFERENCES accounts (id) ON DELETE CASCADE
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_connections_prospect ON connections(prospect_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_connections_account ON connections(account_id)")

        # Table messages
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id SERIAL PRIMARY KEY,
                prospect_id INTEGER NOT NULL,
                account_id INTEGER,
                sent_by VARCHAR NOT NULL CHECK (sent_by IN ('account', 'prospect', 'llm')),
                content TEXT NOT NULL,
                message_type VARCHAR CHECK (message_type IN ('first_contact', 'followup', 'llm_reply', 'manual', 'reply')),
                sent_at TIMESTAMP DEFAULT NOW(),
                strategy_context JSONB,

                FOREIGN KEY (prospect_id) REFERENCES prospects (id) ON DELETE CASCADE,
                FOREIGN KEY (account_id) REFERENCES accounts (id) ON DELETE SET NULL
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_prospect ON messages(prospect_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_sent_at ON messages(sent_at)")

        # Table followups
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS followups (
                id SERIAL PRIMARY KEY,
                prospect_id INTEGER NOT NULL,
                account_id INTEGER NOT NULL,
                followup_type VARCHAR NOT NULL CHECK (followup_type IN ('auto_first', 'auto_conversation', 'long_term')),
                scheduled_at TIMESTAMP NOT NULL,
                status VARCHAR DEFAULT 'pending' CHECK (status IN ('pending', 'sent', 'cancelled')),
                content TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),

                FOREIGN KEY (prospect_id) REFERENCES prospects (id) ON DELETE CASCADE,
                FOREIGN KEY (account_id) REFERENCES accounts (id) ON DELETE CASCADE
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_followups_scheduled ON followups(scheduled_at, status)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_followups_type ON followups(followup_type)")

        # Table logs (fusion logs + tasks)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                id SERIAL PRIMARY KEY,
                user_id INTEGER,
                account_id INTEGER,
                prospect_id INTEGER,
                action VARCHAR NOT NULL,
                entity_type VARCHAR CHECK (entity_type IN ('user', 'account', 'prospect', 'connection', 'message', 'followup')),
                entity_id INTEGER,
                source VARCHAR NOT NULL CHECK (source IN ('user', 'llm', 'system')),
                requires_validation BOOLEAN DEFAULT FALSE,
                validation_status VARCHAR CHECK (validation_status IN ('pending', 'approved', 'rejected', 'auto_executed')),
                payload JSONB,
                details JSONB,
                status VARCHAR CHECK (status IN ('success', 'failed', 'pending')),
                error_message TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                executed_at TIMESTAMP,

                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE SET NULL,
                FOREIGN KEY (account_id) REFERENCES accounts (id) ON DELETE SET NULL,
                FOREIGN KEY (prospect_id) REFERENCES prospects (id) ON DELETE SET NULL
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_user ON logs(user_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_validation ON logs(validation_status)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_action ON logs(action)")

        # Migration: ajouter colonne priority pour gestion task queue
        await conn.execute("""
            ALTER TABLE logs
            ADD COLUMN IF NOT EXISTS priority INTEGER DEFAULT 3
        """)

        # Index optimisé pour récupérer actions pending à exécuter
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_logs_pending_actions
            ON logs(status, validation_status, created_at)
            WHERE status = 'pending'
        """)

        # Table daily_metrics
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS daily_metrics (
                id SERIAL PRIMARY KEY,
                date DATE UNIQUE NOT NULL,
                messages_sent INT DEFAULT 0,
                responses_received INT DEFAULT 0,
                calls_scheduled INT DEFAULT 0,
                prospects_archived INT DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_daily_metrics_date ON daily_metrics(date DESC)")

        # Run migrations
        import os
        migrations_dir = os.path.join(os.path.dirname(__file__), "migrations")
        if os.path.exists(migrations_dir):
            migration_files = sorted([f for f in os.listdir(migrations_dir) if f.endswith(".sql")])
            for migration_file in migration_files:
                migration_path = os.path.join(migrations_dir, migration_file)
                try:
                    with open(migration_path, 'r') as f:
                        migration_sql = f.read()
                    await conn.execute(migration_sql)
                    print(f"✅ Migration applied: {migration_file}")
                except Exception as e:
                    print(f"⚠️  Migration {migration_file} skipped or already applied: {e}")

        print("Database initialized successfully")
    finally:
        await conn.close()