utf-8import structlog
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import NullPool
from custos.schema.models import DatabaseSchema, TableDef, ColumnDef, ForeignKeyDef

logger = structlog.get_logger(__name__)

class SchemaIntrospector:
    def __init__(self, database_url: str):
        self.engine = create_engine(database_url, poolclass=NullPool)

    def introspect(self) -> DatabaseSchema:
        logger.info("Starting schema introspection", database_url=str(self.engine.url))
        inspector = inspect(self.engine)

        tables = {}
        for table_name in inspector.get_table_names():
            columns = {}


            is_duckdb = "duckdb" in str(self.engine.url)

            if is_duckdb:
                pk_cols = []
                with self.engine.connect() as conn:
                    try:
                        res = conn.execute(text(f"SELECT * FROM duckdb_constraints() WHERE table_name = '{table_name}' AND constraint_type = 'PRIMARY KEY'")).fetchall()
                        for row in res:
                            pk_cols.extend(row[11])
                    except Exception as e:
                        logger.warning("Failed to fetch duckdb PK constraints", error=str(e))
            else:
                pk_cols = inspector.get_pk_constraint(table_name).get("constrained_columns", [])

            try:
                fks = inspector.get_foreign_keys(table_name)
            except AttributeError:
                fks = []
                if is_duckdb:
                    with self.engine.connect() as conn:
                        try:
                            res = conn.execute(text(f"SELECT * FROM duckdb_constraints() WHERE table_name = '{table_name}' AND constraint_type = 'FOREIGN KEY'")).fetchall()
                            for row in res:
                                fks.append({
                                    "constrained_columns": row[11],
                                    "referred_table": row[13],
                                    "referred_columns": row[14]
                                })
                        except Exception as e:
                            logger.warning("Failed to fetch duckdb constraints", error=str(e))


            fk_map = {}
            for fk in fks:

                if len(fk["constrained_columns"]) == 1 and len(fk["referred_columns"]) == 1:
                    col = fk["constrained_columns"][0]
                    fk_map[col] = ForeignKeyDef(
                        referred_table=fk["referred_table"],
                        referred_column=fk["referred_columns"][0]
                    )

            for col in inspector.get_columns(table_name):
                col_name = col["name"]
                col_type = str(col["type"])


                sample_values = []

                if any(t in col_type.upper() for t in ("VARCHAR", "TEXT", "CHAR", "STRING")):
                    try:
                        with self.engine.connect() as conn:



                            query = text(f"SELECT DISTINCT {col_name} FROM {table_name} WHERE {col_name} IS NOT NULL LIMIT 3")
                            result = conn.execute(query).fetchall()
                            sample_values = [row[0] for row in result if row[0] is not None]
                    except Exception as e:
                        logger.warning("Failed to fetch sample values", table=table_name, column=col_name, error=str(e))

                columns[col_name] = ColumnDef(
                    name=col_name,
                    type=col_type,
                    primary_key=col_name in pk_cols,
                    foreign_key=fk_map.get(col_name),
                    sample_values=sample_values
                )

            tables[table_name] = TableDef(
                name=table_name,
                columns=columns
            )

        logger.info("Completed schema introspection", table_count=len(tables))
        return DatabaseSchema(tables=tables)
