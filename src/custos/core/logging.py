"""
custos.core.logging — Structured JSON logging setup.

Every log entry produced anywhere in Custos has a consistent schema:
  timestamp, level, module, request_id, event, [phase-specific fields]

Phase-specific fields added in later phases:
  - Phase 2 adds: guardrail_decision, blocked_rule, sql_snippet
  - Phase 3 adds: confidence_score, hallucination_signal, back_translation_score
  - Phase 4 adds: endpoint, latency_ms, cache_hit

Usage:
    from custos.core.logging import get_logger
    log = get_logger(__name__)
    log.info("query_received", question="How many orders...", request_id=req_id)
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog


def configure_logging(log_level: str = "INFO") -> None:
    """
    Configure structlog for structured JSON output.

    Call this once at application startup (in the FastAPI lifespan or the
    Streamlit entry point). Safe to call multiple times — idempotent.
    """
    level = getattr(logging, log_level.upper(), logging.INFO)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,

            structlog.processors.JSONRenderer()
            if not sys.stderr.isatty()
            else structlog.dev.ConsoleRenderer(colors=True),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )



    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level,
    )


def get_logger(name: str) -> Any:
    """
    Return a structlog logger bound to the given module name.

    Usage:
        log = get_logger(__name__)
        log.info("event_name", key="value")
    """
    return structlog.get_logger(name)


def bind_request_context(request_id: str, **kwargs: Any) -> None:
    """
    Bind per-request context variables so they appear in every log line
    within the current async context (structlog contextvars).

    Call at the start of each request handler.
    """
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id=request_id, **kwargs)
