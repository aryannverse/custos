import structlog
from custos.schema.models import DatabaseSchema, TableDef, ColumnDef
from custos.schema.embeddings import SchemaEmbedder
from custos.core.config import settings

logger = structlog.get_logger(__name__)


class RelevanceFilter:
    def __init__(self, embedder: SchemaEmbedder | None = None, top_k: int | None = None):
        self.embedder = embedder or SchemaEmbedder()
        self.top_k = top_k or settings.schema.relevance_top_k

    def filter_schema(self, query: str, full_schema: DatabaseSchema) -> DatabaseSchema:
        """
        Embeds the query, retrieves the top K relevant schema elements,
        and returns a pruned DatabaseSchema containing only the necessary context.
        """
        logger.info("Filtering schema for query", query=query, top_k=self.top_k)


        query_embedding = self.embedder.embedding_model.encode([query]).tolist()


        results = self.embedder.collection.query(
            query_embeddings=query_embedding,
            n_results=self.top_k
        )

        if not results["metadatas"] or not results["metadatas"][0]:
            logger.warning("No relevant schema elements found.")
            return DatabaseSchema(tables={})

        required_tables = set()
        required_columns = set()

        for metadata in results["metadatas"][0]:
            table_name = metadata["table"]
            required_tables.add(table_name)
            if metadata["type"] == "column":
                required_columns.add((table_name, metadata["column"]))




        added_new = True
        while added_new:
            added_new = False
            current_tables = list(required_tables)
            for table_name in current_tables:
                if table_name not in full_schema.tables:
                    continue

                table_def = full_schema.tables[table_name]
                for col_name, col_def in table_def.columns.items():

                    if col_def.primary_key or col_def.foreign_key:
                        if (table_name, col_name) not in required_columns:
                            required_columns.add((table_name, col_name))


                        if col_def.foreign_key:
                            ref_table = col_def.foreign_key.referred_table
                            ref_col = col_def.foreign_key.referred_column

                            if ref_table not in required_tables:
                                required_tables.add(ref_table)
                                added_new = True
                            if (ref_table, ref_col) not in required_columns:
                                required_columns.add((ref_table, ref_col))




        pruned_tables = {}
        for table_name in required_tables:
            if table_name not in full_schema.tables:
                continue

            original_table = full_schema.tables[table_name]
            pruned_cols = {}






            has_explicit_cols = any(c for (t, c) in required_columns if t == table_name)

            for col_name, col_def in original_table.columns.items():
                if not has_explicit_cols or (table_name, col_name) in required_columns:
                    pruned_cols[col_name] = col_def

            pruned_tables[table_name] = TableDef(
                name=table_name,
                columns=pruned_cols,
                description=original_table.description
            )

        logger.info("Completed schema filtering", original_tables=len(full_schema.tables), pruned_tables=len(pruned_tables))
        return DatabaseSchema(tables=pruned_tables)
