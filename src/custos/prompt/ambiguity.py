import structlog
from pydantic import BaseModel, Field
import instructor
from groq import Groq
from custos.schema.models import DatabaseSchema
from custos.core.config import settings

logger = structlog.get_logger(__name__)


class ClarificationRequest(BaseModel):
    is_ambiguous: bool = Field(description="True if the user's question has more than one plausible interpretation given the database schema.")
    clarification_message: str | None = Field(description="If ambiguous, a short message asking the user to clarify their intent (e.g., 'By revenue, do you mean gross or net?'). Null if not ambiguous.")


class AmbiguityDetector:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or settings.groq_api_key

        self.client = instructor.from_groq(Groq(api_key=self.api_key), mode=instructor.Mode.JSON)
        self.model = settings.models.secondary

    def detect(self, query: str, schema: DatabaseSchema, chat_history: list[dict] | None = None) -> ClarificationRequest:
        """
        Runs a lightweight classification pass using the secondary model to flag ambiguous queries.
        """
        logger.info("Running ambiguity detection", model=self.model, query=query)


        schema_summary = []
        for t_name, t_def in schema.tables.items():
            cols = [c_name for c_name in t_def.columns]
            schema_summary.append(f"Table {t_name}: {', '.join(cols)}")
        schema_text = "\n".join(schema_summary)

        system_prompt = f"""You are an expert data analyst assistant.
Your job is to determine if a user's question is ambiguous given the available database schema.
A question is ambiguous if it could refer to multiple different columns, metrics (e.g. gross vs net), or entities, and the correct interpretation is not obvious.

Available Schema:
{schema_text}
"""

        messages = [{"role": "system", "content": system_prompt}]
        if chat_history:
            messages.extend(chat_history)
        messages.append({"role": "user", "content": query})

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                response_model=ClarificationRequest,
                messages=messages,
                max_tokens=256,
            )
            return response
        except Exception as e:
            logger.error("Ambiguity detection failed", error=str(e))

            return ClarificationRequest(is_ambiguous=False, clarification_message=None)
