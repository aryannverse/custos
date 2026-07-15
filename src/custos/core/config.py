utf-8"""
custos.core.config — Configuration loader.

Loads settings from:
  1. config/models.toml, config/guardrails.toml, config/confidence_weights.toml
  2. Environment variables (via .env file or actual environment)

Environment variables override TOML values for deployment flexibility.

CRITICAL: This module fails loudly at import time if GROQ_API_KEY is missing.
A silent empty-string key would cause confusing errors later; we want a clear
message at startup instead.
"""

from __future__ import annotations

import os
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv



load_dotenv()


_REPO_ROOT = Path(__file__).resolve().parents[3]
_CONFIG_DIR = _REPO_ROOT / "config"


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


def _load_toml(path: Path) -> dict[str, Any]:
    """Load a TOML file, returning an empty dict if it doesn't exist yet."""
    if not path.exists():
        return {}
    with open(path, "rb") as f:
        return tomllib.load(f)


@dataclass
class SchemaConfig:
    relevance_top_k: int = 5
    embedding_model: str = "all-MiniLM-L6-v2"


@dataclass
class ModelConfig:
    primary: str
    secondary: str
    requests_per_minute: int = 25
    max_retries: int = 3
    base_backoff_seconds: float = 1.0
    max_backoff_seconds: float = 30.0


@dataclass
class GuardrailConfig:
    default_row_limit: int = 1000
    max_row_limit: int = 10000
    max_subquery_depth: int = 3
    max_scan_rows_estimate: int = 1_000_000
    ddl_node_types: list[str] = field(default_factory=list)
    dml_node_types: list[str] = field(default_factory=list)
    tcl_node_types: list[str] = field(default_factory=list)
    blocked_functions: list[str] = field(default_factory=list)
    normalize_unicode: bool = True
    strip_comments_before_scan: bool = True
    reject_multi_statement: bool = True


@dataclass
class ConfidenceConfig:
    back_translation_alignment: float = 0.35
    sanity_check_pass_rate: float = 0.25
    multi_query_agreement: float = 0.25
    schema_coverage_plausibility: float = 0.15
    back_translation_min_similarity: float = 0.70
    confidence_warning_threshold: int = 50
    confidence_block_threshold: int = 20
    use_calibrated_weights: bool = False


@dataclass
class AppConfig:
    groq_api_key: str
    custos_api_key: str
    database_url: str
    load_demo_data: bool
    api_host: str
    api_port: int
    log_level: str
    models: ModelConfig
    guardrails: GuardrailConfig
    confidence: ConfidenceConfig
    schema: SchemaConfig


def load_config() -> AppConfig:
    """
    Load and validate the full application configuration.

    Raises ConfigError if any required value is missing.
    """
    models_raw = _load_toml(_CONFIG_DIR / "models.toml")
    guardrails_raw = _load_toml(_CONFIG_DIR / "guardrails.toml")
    confidence_raw = _load_toml(_CONFIG_DIR / "confidence_weights.toml")


    groq_api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not groq_api_key:
        raise ConfigError(
            "GROQ_API_KEY environment variable is not set or is empty. "
            "Copy .env.example to .env and fill in your Groq API key. "
            "Get one at: https://console.groq.com/keys"
        )

    custos_api_key = os.environ.get("CUSTOS_API_KEY", "").strip()
    if not custos_api_key:
        raise ConfigError(
            "CUSTOS_API_KEY environment variable is not set or is empty. "
            "Generate one with: python3 -c \"import secrets; print(secrets.token_urlsafe(32))\""
        )


    models_section = models_raw.get("models", {})
    rate_section = models_raw.get("rate_limits", {})
    schema_section = models_raw.get("schema", {})

    primary = os.environ.get("PRIMARY_MODEL", "").strip() or models_section.get(
        "primary", ""
    )
    secondary = os.environ.get("SECONDARY_MODEL", "").strip() or models_section.get(
        "secondary", ""
    )

    if not primary or not secondary:
        raise ConfigError(
            "Both PRIMARY_MODEL and secondary model must be configured in "
            "config/models.toml. Current values: "
            f"primary={primary!r}, secondary={secondary!r}"
        )

    model_config = ModelConfig(
        primary=primary,
        secondary=secondary,
        requests_per_minute=rate_section.get("requests_per_minute", 25),
        max_retries=rate_section.get("max_retries", 3),
        base_backoff_seconds=rate_section.get("base_backoff_seconds", 1.0),
        max_backoff_seconds=rate_section.get("max_backoff_seconds", 30.0),
    )

    schema_config = SchemaConfig(
        relevance_top_k=schema_section.get("relevance_top_k", 5),
        embedding_model=schema_section.get("embedding_model", "all-MiniLM-L6-v2")
    )


    limits = guardrails_raw.get("limits", {})
    blocklist = guardrails_raw.get("blocklist", {})
    adversarial = guardrails_raw.get("adversarial", {})

    guardrail_config = GuardrailConfig(
        default_row_limit=limits.get("default_row_limit", 1000),
        max_row_limit=limits.get("max_row_limit", 10000),
        max_subquery_depth=limits.get("max_subquery_depth", 3),
        max_scan_rows_estimate=limits.get("max_scan_rows_estimate", 1_000_000),
        ddl_node_types=blocklist.get("ddl_node_types", []),
        dml_node_types=blocklist.get("dml_node_types", []),
        tcl_node_types=blocklist.get("tcl_node_types", []),
        blocked_functions=blocklist.get("blocked_functions", []),
        normalize_unicode=adversarial.get("normalize_unicode", True),
        strip_comments_before_scan=adversarial.get("strip_comments_before_scan", True),
        reject_multi_statement=adversarial.get("reject_multi_statement", True),
    )


    weights = confidence_raw.get("weights", {})
    thresholds = confidence_raw.get("thresholds", {})
    calibration = confidence_raw.get("calibration", {})

    confidence_config = ConfidenceConfig(
        back_translation_alignment=weights.get("back_translation_alignment", 0.35),
        sanity_check_pass_rate=weights.get("sanity_check_pass_rate", 0.25),
        multi_query_agreement=weights.get("multi_query_agreement", 0.25),
        schema_coverage_plausibility=weights.get("schema_coverage_plausibility", 0.15),
        back_translation_min_similarity=thresholds.get(
            "back_translation_min_similarity", 0.70
        ),
        confidence_warning_threshold=thresholds.get("confidence_warning_threshold", 50),
        confidence_block_threshold=thresholds.get("confidence_block_threshold", 20),
        use_calibrated_weights=calibration.get("use_calibrated_weights", False),
    )


    database_url = os.environ.get(
        "DATABASE_URL", "duckdb:///data/custos_demo.duckdb"
    ).strip()
    load_demo_data = os.environ.get("LOAD_DEMO_DATA", "true").strip().lower() == "true"

    return AppConfig(
        groq_api_key=groq_api_key,
        custos_api_key=custos_api_key,
        database_url=database_url,
        load_demo_data=load_demo_data,
        api_host=os.environ.get("API_HOST", "0.0.0.0").strip(),
        api_port=int(os.environ.get("API_PORT", "8000")),
        log_level=os.environ.get("LOG_LEVEL", "INFO").strip().upper(),
        models=model_config,
        guardrails=guardrail_config,
        confidence=confidence_config,
        schema=schema_config,
    )




try:
    settings: AppConfig = load_config()
except ConfigError as _exc:


    print(f"\n[Custos] Configuration error: {_exc}\n", file=sys.stderr)
    sys.exit(1)
