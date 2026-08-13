"""Add deterministic model metadata used by the intelligent router.

Revision ID: 005_model_routing_metadata
Revises: 004_releases
"""

import sqlalchemy as sa

from alembic import op

revision = "005_model_routing_metadata"
down_revision = "004_releases"
branch_labels = None
depends_on = None


def _add_column_if_missing(column: str, definition: str) -> None:
    op.execute(f"ALTER TABLE models ADD COLUMN IF NOT EXISTS {column} {definition}")


def _add_check_if_missing(name: str, expression: str) -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = '{name}' AND conrelid = 'models'::regclass
            ) THEN
                ALTER TABLE models ADD CONSTRAINT {name} CHECK ({expression});
            END IF;
        END $$;
        """
    )


def upgrade() -> None:
    _add_column_if_missing("routing_tier", "INTEGER NOT NULL DEFAULT 1")
    _add_column_if_missing("quality_prior", "NUMERIC(5,4) NOT NULL DEFAULT 0.5")
    _add_column_if_missing("tool_reliability_prior", "NUMERIC(5,4) NOT NULL DEFAULT 0.5")
    _add_column_if_missing("latency_prior_ms", "INTEGER NOT NULL DEFAULT 3000")
    _add_column_if_missing("model_family", "VARCHAR(100) NOT NULL DEFAULT 'unknown'")
    _add_column_if_missing("model_vendor", "VARCHAR(100) NOT NULL DEFAULT 'unknown'")
    _add_column_if_missing("architecture_class", "VARCHAR(16) NOT NULL DEFAULT 'unknown'")
    _add_column_if_missing("supports_reasoning", "BOOLEAN NOT NULL DEFAULT FALSE")
    _add_column_if_missing("reasoning_levels", "JSONB NOT NULL DEFAULT '[]'::jsonb")
    _add_column_if_missing("input_price_microusd_per_million", "INTEGER NOT NULL DEFAULT 0")
    _add_column_if_missing("output_price_microusd_per_million", "INTEGER NOT NULL DEFAULT 0")
    _add_column_if_missing("routing_enabled", "BOOLEAN NOT NULL DEFAULT FALSE")

    op.execute(
        sa.text(
            """
            UPDATE models
            SET model_family = COALESCE(NULLIF(lower(trim(model_family)), ''), 'unknown'),
                model_vendor = COALESCE(NULLIF(lower(trim(model_vendor)), ''), 'unknown'),
                architecture_class = COALESCE(NULLIF(lower(trim(architecture_class)), ''), 'unknown'),
                reasoning_levels = COALESCE(reasoning_levels, '[]'::jsonb),
                routing_enabled = COALESCE(routing_enabled, FALSE)
            """
        )
    )
    _add_check_if_missing("ck_models_routing_tier", "routing_tier >= 0 AND routing_tier <= 3")
    _add_check_if_missing("ck_models_quality_prior", "quality_prior >= 0 AND quality_prior <= 1")
    _add_check_if_missing(
        "ck_models_tool_reliability_prior",
        "tool_reliability_prior >= 0 AND tool_reliability_prior <= 1",
    )
    _add_check_if_missing("ck_models_latency_prior", "latency_prior_ms > 0")
    _add_check_if_missing(
        "ck_models_architecture_class",
        "architecture_class IN ('dense','moe','hybrid','unknown')",
    )
    _add_check_if_missing("ck_models_input_price", "input_price_microusd_per_million >= 0")
    _add_check_if_missing("ck_models_output_price", "output_price_microusd_per_million >= 0")
    _add_check_if_missing(
        "ck_models_reasoning_levels",
        "supports_reasoning OR jsonb_array_length(reasoning_levels) = 0",
    )
    _add_check_if_missing(
        "ck_models_routing_identity",
        "NOT routing_enabled OR (model_family <> 'unknown' AND model_vendor <> 'unknown')",
    )


def downgrade() -> None:
    for name in (
        "ck_models_routing_identity",
        "ck_models_reasoning_levels",
        "ck_models_output_price",
        "ck_models_input_price",
        "ck_models_architecture_class",
        "ck_models_latency_prior",
        "ck_models_tool_reliability_prior",
        "ck_models_quality_prior",
        "ck_models_routing_tier",
    ):
        op.execute(f"ALTER TABLE models DROP CONSTRAINT IF EXISTS {name}")
    for column in (
        "routing_enabled",
        "output_price_microusd_per_million",
        "input_price_microusd_per_million",
        "reasoning_levels",
        "supports_reasoning",
        "architecture_class",
        "model_vendor",
        "model_family",
        "latency_prior_ms",
        "tool_reliability_prior",
        "quality_prior",
        "routing_tier",
    ):
        op.execute(f"ALTER TABLE models DROP COLUMN IF EXISTS {column}")
