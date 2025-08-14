from qdrant_client import QdrantClient
from qdrant_client.http.models import Filter, FieldCondition, MatchValue, FilterSelector, OrderBy
from dotenv import load_dotenv
import os

load_dotenv()

class QdrantTool():
    def __init__(self):
        self.client: QdrantClient = None
        self.collection_name: str = "running_mcp"
        self.score_threshold: float = 0.35
        self.qdrant_url: str = os.getenv("QDRANT_URL")
        self.qdrant_api_key: str = os.getenv("QDRANT_API_KEY")
        self.embedding_model: str = "text-embedding-004"
    
    # def _convert_activities_summaries(activities: )

