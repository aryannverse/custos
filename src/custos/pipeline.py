from pydantic import BaseModel
from typing import Any

from custos.schema.introspection import SchemaIntrospector
from custos.schema.embeddings import SchemaEmbedder
from custos.schema.filter import RelevanceFilter
from custos.prompt.constructor import PromptConstructor
from custos.prompt.ambiguity import AmbiguityDetector

from custos.generation.generator import SQLGenerator
from custos.guardrails.middleware import GuardrailEngine, GuardrailViolationError
from custos.execution.sandbox import SandboxedExecutor

from custos.evaluation.back_translator import BackTranslator
from custos.evaluation.multi_query import MultiQueryValidator
from custos.evaluation.sanity_checker import SanityChecker
from custos.evaluation.confidence import ConfidenceAggregator, ConfidenceReport


class PipelineResult(BaseModel):
    sql: str
    explanation: str
    confidence_report: ConfidenceReport
    data: list[dict[str, Any]]
    columns: list[str]
    execution_time_ms: float
    is_ambiguous: bool
    ambiguity_reason: str | None


class TextToSQLPipeline:
    def __init__(self, database_url: str = None) -> None:
        import os
        from dotenv import load_dotenv
        load_dotenv()
        if database_url is None:
            database_url = os.getenv("DATABASE_URL", "duckdb:///data/custos_demo.duckdb")
            
        
        self.introspector = SchemaIntrospector(database_url)
        self.embedder = SchemaEmbedder()
        self.filter = RelevanceFilter(self.embedder)
        self.prompt_constructor = PromptConstructor()
        self.ambiguity_detector = AmbiguityDetector()
        
        
        self.generator = SQLGenerator()
        self.guardrails = GuardrailEngine()
        self.sandbox = SandboxedExecutor()
        
        
        self.back_translator = BackTranslator()
        self.multi_query = MultiQueryValidator()
        self.sanity_checker = SanityChecker()
        self.confidence_aggregator = ConfidenceAggregator()
        
    def setup_dynamic_db(self, database_url: str, session_id: str):
        """
        Dynamically sets up database-specific components (introspector, executor) 
        and an ephemeral embedder for a newly uploaded database.
        Returns a tuple of (introspector, filter, sandbox) for this dynamic DB.
        """
        dynamic_introspector = SchemaIntrospector(database_url)
        
        
        dynamic_embedder = SchemaEmbedder(
            is_ephemeral=True,
            collection_name=f"schema_{session_id}",
            embedding_model=self.embedder.embedding_model
        )
        
        dynamic_filter = RelevanceFilter(dynamic_embedder, top_k=self.filter.top_k)
        
        
        full_schema = dynamic_introspector.introspect()
        dynamic_embedder.embed_schema(full_schema)
        
        
        dynamic_sandbox = SandboxedExecutor(database_url)
        
        return dynamic_introspector, dynamic_filter, dynamic_sandbox

    def run(self, user_question: str, dynamic_components=None, chat_history: list[dict] | None = None) -> PipelineResult:
        
        
        if dynamic_components:
            current_introspector, current_filter, current_sandbox = dynamic_components
        else:
            current_introspector = self.introspector
            current_filter = self.filter
            current_sandbox = self.sandbox
            
        
        full_schema = current_introspector.introspect()
        
        
        search_query = user_question
        if chat_history:
            previous_queries = [msg['content'] for msg in chat_history if msg['role'] == 'user']
            if previous_queries:
                search_query = f"{' '.join(previous_queries)} {user_question}"
            
        filtered_schema = current_filter.filter_schema(search_query, full_schema)
        
        system_prompt, user_prompt = self.prompt_constructor.construct(user_question, filtered_schema)
        
        
        clarification = self.ambiguity_detector.detect(user_question, filtered_schema, chat_history)
        is_ambiguous = clarification.is_ambiguous
        reason = clarification.clarification_message
        
        
        gen_result = self.generator.generate(system_prompt, user_question, chat_history)
        
        
        try:
            safe_sql = self.guardrails.validate_and_format(gen_result.sql_query)
            exec_result = current_sandbox.execute(safe_sql)
            syntax_valid = True
            rows = exec_result.rows
            columns = exec_result.columns
            exec_time = exec_result.execution_time_ms
        except Exception as e:
            import structlog
            logger = structlog.get_logger(__name__)
            logger.error("Execution failed", error=str(e), sql=gen_result.sql_query)
            
            
            syntax_valid = False
            safe_sql = gen_result.sql_query
            rows = []
            columns = []
            exec_time = 0.0

        
        if syntax_valid:
            bt_score = self.back_translator.translate_and_compare(user_question, safe_sql)
            sanity_score = self.sanity_checker.check_plausibility(user_question, safe_sql, rows)
            
            
            is_complex = any(k in safe_sql.upper() for k in ["JOIN", "GROUP BY", "(SELECT"])
            mq_score = self.multi_query.check_agreement(system_prompt, user_question, rows, is_complex)
            
            schema_score = float(gen_result.confidence_score)
        else:
            bt_score = 0.0
            sanity_score = 0.0
            mq_score = 0.0
            schema_score = 0.0
            
        report = self.confidence_aggregator.aggregate(
            syntax_valid=syntax_valid,
            schema_coverage_score=schema_score,
            back_translation_score=bt_score,
            sanity_check_score=sanity_score,
            multi_query_score=mq_score
        )
        
        return PipelineResult(
            sql=safe_sql,
            explanation=gen_result.explanation,
            confidence_report=report,
            data=rows,
            columns=columns,
            execution_time_ms=exec_time,
            is_ambiguous=is_ambiguous,
            ambiguity_reason=reason
        )
