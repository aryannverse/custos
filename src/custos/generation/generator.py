utf-8import instructor
from groq import Groq

from custos.core.config import settings
from custos.generation.models import SQLGenerationResult

class SQLGenerator:
    """
    Generates structured SQL queries using a configured LLM via Groq.
    Enforces a strict Pydantic output schema (SQLGenerationResult).
    """
    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or settings.groq_api_key
        self.model = model or settings.models.primary

        self.client = instructor.from_groq(Groq(api_key=self.api_key), mode=instructor.Mode.TOOLS)

    def generate(self, system_prompt: str, user_prompt: str, chat_history: list[dict] | None = None) -> SQLGenerationResult:
        """
        Calls the primary LLM to generate the SQL query and explanation.

        Args:
            system_prompt: The fully constructed system prompt with schema context.
            user_prompt: The user's natural language question.
            chat_history: Optional history of previous messages to provide conversational context.

        Returns:
            SQLGenerationResult: Contains the raw SQL, explanation, and confidence.
        """
        messages = [{"role": "system", "content": system_prompt}]
        if chat_history:
            messages.extend(chat_history)
        messages.append({"role": "user", "content": user_prompt})

        try:
            result = self.client.chat.completions.create(
                model=self.model,
                response_model=SQLGenerationResult,
                messages=messages,
                temperature=0.0,
            )
            return result
        except Exception as e:
            
            import structlog
            logger = structlog.get_logger(__name__)
            logger.error("SQL Generation failed via Instructor", error=str(e))
            return SQLGenerationResult(
                sql_query="SELECT 'Query generation failed. The requested information may not exist in the database.' AS error",
                explanation="I could not generate a valid query for this request given the available database schema.",
                confidence_score=0,
                tables_used=[]
            )
