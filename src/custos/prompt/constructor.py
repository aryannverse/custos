import structlog
from custos.schema.models import DatabaseSchema

logger = structlog.get_logger(__name__)

class PromptConstructor:
    def __init__(self):

        self.system_prompt_template = """You are Custos, an expert SQL assistant.
Your task is to convert the user's natural language question into a valid, optimized SQL query.
You must use ONLY the tables and columns provided in the schema below.
DO NOT use DDL or DML statements. Your query must be read-only (SELECT).

SCHEMA:
{schema_ddl}

FEW-SHOT EXAMPLES:
{few_shot_examples}

Respond with only the SQL query, or a structured JSON response if required by the generation layer.
"""

    def _format_schema(self, schema: DatabaseSchema) -> str:
        lines = []
        for table_name, table_def in schema.tables.items():
            lines.append(f"CREATE TABLE {table_name} (")
            col_lines = []
            for col_name, col_def in table_def.columns.items():
                col_str = f"  {col_name} {col_def.type}"
                if col_def.primary_key:
                    col_str += " PRIMARY KEY"
                if col_def.foreign_key:
                    fk = col_def.foreign_key
                    col_str += f" REFERENCES {fk.referred_table}({fk.referred_column})"

                if col_def.sample_values:

                    samples = [str(s).replace("'", "''") for s in col_def.sample_values]
                    col_str += f" -- Sample values: {', '.join(samples)}"

                col_lines.append(col_str)
            lines.append(",\n".join(col_lines))
            lines.append(");\n")
        return "\n".join(lines)

    def _format_few_shots(self, examples: list[dict[str, str]]) -> str:
        if not examples:
            return "No examples provided."

        lines = []
        for i, ex in enumerate(examples, 1):
            lines.append(f"Example {i}:")
            lines.append(f"Question: {ex['question']}")
            lines.append(f"SQL: {ex['sql']}\n")
        return "\n".join(lines)

    def construct(self, query: str, schema: DatabaseSchema, few_shot_examples: list[dict[str, str]] | None = None) -> tuple[str, str]:
        """
        Returns a tuple of (system_prompt, user_prompt).
        """
        logger.info("Constructing prompt", tables=len(schema.tables))

        few_shots = self._format_few_shots(few_shot_examples or [])
        schema_ddl = self._format_schema(schema)

        system_prompt = self.system_prompt_template.format(
            schema_ddl=schema_ddl,
            few_shot_examples=few_shots
        )

        user_prompt = f"Question: {query}"

        return system_prompt, user_prompt
