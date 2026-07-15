import instructor
from groq import Groq
from typing import Any

from custos.core.config import settings
from custos.generation.models import SQLGenerationResult
from custos.guardrails.middleware import GuardrailEngine
from custos.execution.sandbox import SandboxedExecutor

class MultiQueryValidator:
    """
    Addresses Hallucinations by generating a second SQL query using an independent
    model (or temperature), executing it, and comparing the result sets.
    """
    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or settings.groq_api_key
        
        self.model = model or settings.models.secondary
        self.client = instructor.from_groq(Groq(api_key=self.api_key), mode=instructor.Mode.JSON)
        self.guardrails = GuardrailEngine()
        self.sandbox = SandboxedExecutor()

    def check_agreement(
        self, 
        system_prompt: str, 
        user_question: str, 
        primary_rows: list[dict[str, Any]],
        is_complex: bool
    ) -> float:
        """
        If the question is complex, generates an alternative query, executes it, 
        and compares the results.
        
        Args:
            system_prompt: Context including schema.
            user_question: The original user query.
            primary_rows: Data returned by the primary query.
            is_complex: Flag indicating if the query involves joins or subqueries.
            
        Returns:
            A score of 100.0 (agreement) or 0.0 (disagreement/failure).
        """
        
        if not is_complex:
            return 100.0
            
        alt_sys_prompt = (
            system_prompt + 
            "\n\nYou are a secondary verifier. Generate the query using a "
            "DIFFERENT SQL strategy (e.g., using JOINs instead of subqueries, "
            "or vice versa, or different aggregation grouping) if possible."
        )
        
        try:
            result = self.client.chat.completions.create(
                model=self.model,
                response_model=SQLGenerationResult,
                messages=[
                    {"role": "system", "content": alt_sys_prompt},
                    {"role": "user", "content": user_question},
                ],
                temperature=0.3  
            )
            
            safe_sql = self.guardrails.validate_and_format(result.sql_query)
            exec_result = self.sandbox.execute(safe_sql)
            
            
            
            
            def _freeze(row: dict[str, Any]) -> frozenset:
                return frozenset((k, str(v)) for k, v in row.items())
                
            primary_set = {_freeze(r) for r in primary_rows}
            secondary_set = {_freeze(r) for r in exec_result.rows}
            
            if primary_set == secondary_set:
                return 100.0
            else:
                return 0.0
                
        except Exception:
            
            return 0.0
