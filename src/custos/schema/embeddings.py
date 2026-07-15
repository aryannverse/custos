utf-8import chromadb
from sentence_transformers import SentenceTransformer
from custos.schema.models import DatabaseSchema
import structlog

logger = structlog.get_logger(__name__)


class SchemaEmbedder:
    def __init__(self, persist_dir: str = "./data/chroma", model_name: str = "all-MiniLM-L6-v2", is_ephemeral: bool = False, collection_name: str = "schema_elements", embedding_model: SentenceTransformer | None = None):
        self.persist_dir = persist_dir
        self.model_name = model_name
        self.is_ephemeral = is_ephemeral
        
        if self.is_ephemeral:
            self.client = chromadb.EphemeralClient()
        else:
            self.client = chromadb.PersistentClient(path=persist_dir)
            
        self.embedding_model = embedding_model or SentenceTransformer(model_name)
        self.collection = self.client.get_or_create_collection(collection_name)

    def _generate_description(self, table_name: str, col_name: str | None = None) -> str:
        """
        Generate a basic natural language description for embedding.
        In a more advanced setup, this could be LLM-assisted or pull from database comments.
        """
        if col_name:
            return f"Column '{col_name}' in table '{table_name}'. Contains data related to {col_name.replace('_', ' ')}."
        return f"Table '{table_name}'. Contains records of {table_name.replace('_', ' ')}."

    def embed_schema(self, schema: DatabaseSchema) -> None:
        """
        Computes embeddings for all tables and columns and stores them in ChromaDB.
        """
        logger.info("Starting schema embedding", model=self.model_name)
        documents = []
        metadatas = []
        ids = []

        for table_name, table_def in schema.tables.items():

            desc = table_def.description or self._generate_description(table_name)
            documents.append(desc)
            metadatas.append({"type": "table", "table": table_name})
            ids.append(f"table:{table_name}")


            for col_name, col_def in table_def.columns.items():
                col_desc = col_def.description or self._generate_description(table_name, col_name)
                documents.append(col_desc)
                metadatas.append({"type": "column", "table": table_name, "column": col_name})
                ids.append(f"col:{table_name}:{col_name}")


        logger.info("Computing embeddings", count=len(documents))
        embeddings = self.embedding_model.encode(documents).tolist()


        logger.info("Upserting into ChromaDB")
        self.collection.upsert(
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
            ids=ids
        )
        logger.info("Finished schema embedding")
