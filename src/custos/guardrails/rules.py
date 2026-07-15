import sqlglot
from sqlglot import expressions as exp
from typing import Optional

from custos.core.config import settings

class GuardrailViolationError(Exception):
    """Raised when a query violates a guardrail rule."""
    def __init__(self, rule_name: str, message: str):
        self.rule_name = rule_name
        super().__init__(f"[{rule_name}] {message}")


class BaseRule:
    """Base class for AST-based SQL guardrail rules."""

    @property
    def name(self) -> str:
        return self.__class__.__name__

    def evaluate(self, node: exp.Expression) -> Optional[exp.Expression]:
        """
        Evaluate the AST node against the rule.

        Args:
            node: The root AST node of the query.

        Returns:
            The potentially modified AST node, or raises GuardrailViolationError.
        """
        raise NotImplementedError


class NoDMLRule(BaseRule):
    """Rejects any Data Manipulation Language (DML) or Data Definition Language (DDL)."""

    def __init__(self) -> None:

        self.blocked_types = set(
            settings.guardrails.ddl_node_types
            + settings.guardrails.dml_node_types
            + settings.guardrails.tcl_node_types
        )
        self.blocked_functions = {f.lower() for f in settings.guardrails.blocked_functions}

    def evaluate(self, node: exp.Expression) -> exp.Expression:
        for n in node.walk():







            pass


        for descendant in node.find_all(exp.Expression):
            node_type = descendant.__class__.__name__
            if node_type in self.blocked_types:
                raise GuardrailViolationError(
                    self.name, f"Blocked AST node type detected: {node_type}"
                )


            if isinstance(descendant, exp.Func):
                func_name = descendant.sql_name().lower()
                if func_name in self.blocked_functions:
                    raise GuardrailViolationError(
                        self.name, f"Blocked function detected: {func_name}"
                    )

        return node


class MaxNestingRule(BaseRule):
    """Ensures subquery nesting does not exceed the configured maximum."""

    def __init__(self) -> None:
        self.max_depth = settings.guardrails.max_subquery_depth

    def evaluate(self, node: exp.Expression) -> exp.Expression:


        def get_depth(n: exp.Expression, current_depth: int) -> int:
            if not n:
                return current_depth


            new_depth = current_depth + 1 if isinstance(n, exp.Select) else current_depth

            max_d = new_depth
            for child, _, _ in n.walk(prune=lambda _: True):

                pass
            return max_d

        def _calculate_depth(n: exp.Expression, depth: int) -> int:
            max_child_depth = depth
            is_select_or_subquery = isinstance(n, (exp.Select, exp.Subquery))
            new_depth = depth + 1 if is_select_or_subquery else depth

            for key, val in n.args.items():
                if isinstance(val, exp.Expression):
                    max_child_depth = max(max_child_depth, _calculate_depth(val, new_depth))
                elif isinstance(val, list):
                    for item in val:
                        if isinstance(item, exp.Expression):
                            max_child_depth = max(max_child_depth, _calculate_depth(item, new_depth))
            return max_child_depth

        depth = _calculate_depth(node, 0)
        if depth > self.max_depth:
            raise GuardrailViolationError(
                self.name,
                f"Query nesting depth ({depth}) exceeds maximum allowed ({self.max_depth})."
            )
        return node


class EnforceLimitRule(BaseRule):
    """Injects or clamps the LIMIT clause to prevent unbounded queries."""

    def __init__(self) -> None:
        self.default_limit = settings.guardrails.default_row_limit
        self.max_limit = settings.guardrails.max_row_limit

    def evaluate(self, node: exp.Expression) -> exp.Expression:

        if not isinstance(node, exp.Select):
            return node

        limit_expr = node.args.get("limit")
        if not limit_expr:

            node = node.limit(self.default_limit)
        else:

            try:

                limit_val = int(limit_expr.expression.name)
                if limit_val > self.max_limit:

                    limit_expr.set("expression", exp.convert(self.max_limit))
            except (ValueError, TypeError, AttributeError):


                limit_expr.set("expression", exp.convert(self.max_limit))

        return node
