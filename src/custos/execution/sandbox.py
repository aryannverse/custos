import time
import structlog
import duckdb
from pydantic import BaseModel, Field
from typing import Any

from custos.core.config import settings

logger = structlog.get_logger(__name__)

class ExecutionResult(BaseModel):
    columns: list[str] = Field(description="List of column names returned.")
    rows: list[dict[str, Any]] = Field(description="The actual data rows returned.")
    execution_time_ms: float = Field(description="Time taken to execute the query in milliseconds.")
    explain_plan: str = Field(description="The EXPLAIN query plan output.")


class SandboxedExecutor:
    """
    Executes the validated SQL query in an unconditionally rolled-back transaction.
    """

    def __init__(self, db_path: str | None = None):
        url = db_path or settings.database_url

        if url.startswith("duckdb:///"):
            self.db_path = url.replace("duckdb:///", "")
        else:
            self.db_path = url

    def execute(self, safe_sql: str) -> ExecutionResult:
        """
        Executes the provided SQL in a sandboxed, read-only, unconditionally rolled-back transaction.

        Args:
            safe_sql: The validated, formatting SQL string from the GuardrailEngine.

        Returns:
            ExecutionResult containing data and metadata.
        """
        conn = duckdb.connect(self.db_path, read_only=True)


        try:
            conn.execute("BEGIN TRANSACTION READ ONLY")
        except Exception as e:



            logger.warning("readonly_tx_failed", error=str(e))
            conn.execute("BEGIN TRANSACTION")

        start_time = time.perf_counter()

        try:

            explain_res = conn.execute(f"EXPLAIN {safe_sql}").fetchall()
            explain_plan = "\n".join([str(row[1]) for row in explain_res])


            res = conn.execute(safe_sql)


            columns = [desc[0] for desc in res.description] if res.description else []

            rows_tuples = res.fetchall()
            rows = [dict(zip(columns, row)) for row in rows_tuples]

            execution_time_ms = (time.perf_counter() - start_time) * 1000

            return ExecutionResult(
                columns=columns,
                rows=rows,
                execution_time_ms=execution_time_ms,
                explain_plan=explain_plan,
            )
        finally:


            try:
                conn.execute("ROLLBACK")
            except Exception as e:
                logger.error("sandbox_rollback_failed", error=str(e))
            finally:
                conn.close()
