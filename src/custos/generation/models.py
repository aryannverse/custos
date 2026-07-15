from pydantic import BaseModel, Field

class SQLGenerationResult(BaseModel):
    sql_query: str = Field(description="The valid SQL query answering the user's question. MUST NOT include any markdown formatting like ```sql...```, just the raw SQL.")
    explanation: str = Field(description="A plain-language explanation of what the query does.")
    confidence_score: int = Field(ge=0, le=100, description="Self-reported confidence score (0-100) on how well the query answers the question given the schema.")
    tables_used: list[str] = Field(description="List of table names used in the query.")
