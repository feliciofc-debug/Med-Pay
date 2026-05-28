"""Cria tabelas do módulo MedPag Vital (presença + sinais vitais).

Habilita ingestão de eventos de sensores RuView (ESP32 com WiFi CSI),
Aqara FP2 (mmWave) ou simulados (Docker). Esquema genérico permite
qualquer hardware compatível.

Tabelas criadas:
    vital_ambientes: lugares físicos monitorados
    vital_nos: sensores cadastrados (1 chip = 1 nó)
    vital_eventos: eventos recebidos (presença, queda, HR, BR, etc)

Enums criados:
    vital_tipo_ambiente
    vital_tipo_sensor
    vital_status_no
    vital_tipo_evento

Revision ID: 013_modulo_vital
Revises: 012_anestesista_codigos
Create Date: 2026-05-28 09:00:00 UTC
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "013_modulo_vital"
down_revision: str | None = "012_anestesista_codigos"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ----- ENUMs -----
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE vital_tipo_ambiente AS ENUM (
                'SALA_CIRURGICA', 'UTI', 'ENFERMARIA', 'CONSULTORIO',
                'PRONTO_SOCORRO', 'RESIDENCIAL', 'OUTRO'
            );
        EXCEPTION WHEN duplicate_object THEN null; END $$;
        """
    )
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE vital_tipo_sensor AS ENUM (
                'RUVIEW_ESP32_S3', 'RUVIEW_ESP32_C6',
                'AQARA_FP2', 'AQARA_FP1', 'SIMULADO', 'OUTRO'
            );
        EXCEPTION WHEN duplicate_object THEN null; END $$;
        """
    )
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE vital_status_no AS ENUM (
                'ONLINE', 'OFFLINE', 'DEGRADADO', 'NUNCA_VISTO'
            );
        EXCEPTION WHEN duplicate_object THEN null; END $$;
        """
    )
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE vital_tipo_evento AS ENUM (
                'PRESENCA', 'CONTAGEM_PESSOAS', 'MOVIMENTO',
                'BATIMENTO_CARDIACO', 'FREQUENCIA_RESPIRATORIA',
                'QUEDA', 'POSE',
                'PESSOA_DORMINDO', 'POSSIVEL_DISTRESS', 'SALA_ATIVA',
                'ANOMALIA_INATIVIDADE', 'REUNIAO', 'BANHEIRO',
                'RISCO_QUEDA', 'SAIDA_CAMA', 'SEM_MOVIMENTO',
                'TRANSICAO_MULTI_SALA',
                'HEARTBEAT', 'OUTRO'
            );
        EXCEPTION WHEN duplicate_object THEN null; END $$;
        """
    )

    # ----- vital_ambientes -----
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS vital_ambientes (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            cliente_id          UUID NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
            nome                VARCHAR(255) NOT NULL,
            tipo                vital_tipo_ambiente NOT NULL DEFAULT 'OUTRO',
            descricao           VARCHAR(1024),
            referencia_externa  VARCHAR(120),
            ativo               BOOLEAN NOT NULL DEFAULT TRUE,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_vital_ambiente_cliente_nome UNIQUE (cliente_id, nome)
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_vital_ambientes_cliente_id "
        "ON vital_ambientes (cliente_id);"
    )

    # ----- vital_nos -----
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS vital_nos (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            cliente_id          UUID NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
            ambiente_id         UUID REFERENCES vital_ambientes(id) ON DELETE SET NULL,
            node_id             VARCHAR(120) NOT NULL,
            tipo                vital_tipo_sensor NOT NULL DEFAULT 'RUVIEW_ESP32_S3',
            apelido             VARCHAR(255),
            api_key             VARCHAR(120) NOT NULL UNIQUE,
            status              vital_status_no NOT NULL DEFAULT 'NUNCA_VISTO',
            privacy_mode        BOOLEAN NOT NULL DEFAULT FALSE,
            firmware_version    VARCHAR(40),
            last_seen_at        TIMESTAMPTZ,
            last_rssi           DOUBLE PRECISION,
            ativo               BOOLEAN NOT NULL DEFAULT TRUE,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_vital_no_cliente_node UNIQUE (cliente_id, node_id)
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_vital_nos_cliente_id "
        "ON vital_nos (cliente_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_vital_nos_ambiente_id "
        "ON vital_nos (ambiente_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_vital_nos_api_key "
        "ON vital_nos (api_key);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_vital_nos_last_seen "
        "ON vital_nos (last_seen_at);"
    )

    # ----- vital_eventos -----
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS vital_eventos (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            cliente_id      UUID NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
            ambiente_id     UUID REFERENCES vital_ambientes(id) ON DELETE SET NULL,
            no_id           UUID REFERENCES vital_nos(id) ON DELETE SET NULL,
            tipo            vital_tipo_evento NOT NULL,
            valor_num       DOUBLE PRECISION,
            valor_texto     VARCHAR(255),
            confianca       DOUBLE PRECISION,
            observado_em    TIMESTAMPTZ NOT NULL,
            extras_json     VARCHAR(2048),
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_vital_eventos_cliente_id "
        "ON vital_eventos (cliente_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_vital_eventos_ambiente_id "
        "ON vital_eventos (ambiente_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_vital_eventos_no_id "
        "ON vital_eventos (no_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_vital_eventos_tipo "
        "ON vital_eventos (tipo);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_vital_eventos_observado_em "
        "ON vital_eventos (observado_em);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_vital_eventos_cliente_obs "
        "ON vital_eventos (cliente_id, observado_em);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_vital_eventos_ambiente_obs "
        "ON vital_eventos (ambiente_id, observado_em);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_vital_eventos_no_obs "
        "ON vital_eventos (no_id, observado_em);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_vital_eventos_tipo_obs "
        "ON vital_eventos (tipo, observado_em);"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS vital_eventos CASCADE;")
    op.execute("DROP TABLE IF EXISTS vital_nos CASCADE;")
    op.execute("DROP TABLE IF EXISTS vital_ambientes CASCADE;")
    op.execute("DROP TYPE IF EXISTS vital_tipo_evento;")
    op.execute("DROP TYPE IF EXISTS vital_status_no;")
    op.execute("DROP TYPE IF EXISTS vital_tipo_sensor;")
    op.execute("DROP TYPE IF EXISTS vital_tipo_ambiente;")
