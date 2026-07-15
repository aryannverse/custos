import json
import instructor
from groq import Groq
from pydantic import BaseModel, Field
from typing import Any

from custos.core.config import settings

class SanityCheckResult(BaseModel):
    is_plausible: bool = Field(description="True if the result data appears logical and physically possible given the question, False otherwise.")
    reason: str = Field(description="Explanation of why the data is or isn't plausible.")

class SanityChecker:
    """
    Evaluates executed data for obvious logical impossibilities using 
    both heuristics and the secondary (Critic) model.
    """
    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or settings.groq_api_key
        
        self.model = model or settings.models.secondary
        self.client = instructor.from_groq(Groq(api_key=self.api_key), mode=instructor.Mode.JSON)

    def check_plausibility(self, question: str, sql: str, rows: list[dict[str, Any]]) -> float:
        """
        Runs a NULL density check and an LLM-based plausibility check on the executed data.
        
        Args:
            question: Original user question.
            sql: The generated SQL.
            rows: The list of dicts returned from execution.
            
        Returns:
            A score (0.0 or 100.0).
        """
        if not rows:
            return 100.0  
            
        
        
        
        num_rows = len(rows)
        for col in rows[0].keys():
            null_count = sum(1 for row in rows if row.get(col) is None)
            if num_rows > 5 and (null_count / num_rows) > 0.9:
                return 0.0
                
        
        
        sample_rows = rows[:10]
        
        system_prompt = (
            "You are a strict data quality critic. Your job is to look at a user's question, "
            "the SQL query generated, and the sample result data returned from the database. "
            "Check for obvious logical impossibilities (e.g., negative ages, order of magnitude errors on counts, "
            "dates in the year 9999, NULLs where there should be values). "
            "Return whether the data looks plausible."
        )
        
        user_content = (
            f"Question: {question}\n"
            f"SQL: {sql}\n"
            f"Sample Data (JSON): {json.dumps(sample_rows, default=str)}\n"
        )
        
        try:
            result = self.client.chat.completions.create(
                model=self.model,
                response_model=SanityCheckResult,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                temperature=0.0
            )
            return 100.0 if result.is_plausible else 0.0
        except Exception:
            
            return 100.0
