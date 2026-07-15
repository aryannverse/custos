import structlog
import sqlglot
import unicodedata
from sqlglot import parse_one
from sqlglot.errors import ParseError

from custos.core.config import settings
from custos.guardrails.rules import (
    BaseRule,
    NoDMLRule,
    MaxNestingRule,
    EnforceLimitRule,
    GuardrailViolationError,
)

logger = structlog.get_logger(__name__)

class GuardrailEngine:
    """
    Middleware that intercepts generated SQL and runs it through AST-level guardrails.
    """

    def __init__(self, rules: list[BaseRule] | None = None):
        self.rules = rules or [
            NoDMLRule(),
            MaxNestingRule(),
            EnforceLimitRule(),
        ]
        self.normalize_unicode = settings.guardrails.normalize_unicode
        self.reject_multi_stmt = settings.guardrails.reject_multi_statement

    def validate_and_format(self, raw_sql: str) -> str:
        """
        Runs the full defense-in-depth AST validation pipeline.

        Args:
            raw_sql: The raw SQL string from the LLM.

        Returns:
            A safe, formatted, and potentially modified SQL string (e.g. with LIMIT injected).

        Raises:
            GuardrailViolationError: If any rule blocks the query.
        """

        if self.normalize_unicode:
            raw_sql = unicodedata.normalize("NFKC", raw_sql)


        if self.reject_multi_stmt:
            try:

                stmts = sqlglot.parse(raw_sql, read="duckdb")

                stmts = [s for s in stmts if s is not None]
                if len(stmts) > 1:
                    raise GuardrailViolationError(
                        "MultiStatementRule",
                        "Multiple statements separated by semicolons are not allowed."
                    )
            except ParseError as e:
                raise GuardrailViolationError("ParseRule", f"Syntax error: {e}")

        try:

            ast = parse_one(raw_sql, read="duckdb")
        except ParseError as e:
            raise GuardrailViolationError("ParseRule", f"Syntax error: {e}")


        for rule in self.rules:
            try:
                ast = rule.evaluate(ast)
            except GuardrailViolationError as e:
                logger.warning(
                    "guardrail_blocked",
                    rule=rule.name,
                    reason=str(e),
                    raw_sql=raw_sql
                )
                raise e


        return ast.sql(dialect="duckdb")
