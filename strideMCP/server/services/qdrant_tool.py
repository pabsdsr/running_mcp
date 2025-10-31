from qdrant_client import QdrantClient
from qdrant_client.http.models import Filter, FieldCondition, MatchValue, FilterSelector, OrderBy
from qdrant_client.models import PayloadSchemaType, PointStruct
from datetime import datetime, timezone
from google import genai
import uuid
from google.genai import types
import asyncio
from dotenv import load_dotenv
import os

load_dotenv()

class QdrantService():
    def __init__(self):
        self.client: QdrantClient = QdrantClient(url=os.getenv("QDRANT_URL"), api_key= os.getenv("QDRANT_API_KEY"))
        self.collection_name: str = "running_mcp"
        self.score_threshold: float = 0.35
        self.embedding_model: str = "text-embedding-004"
        self._create_payloads()

    def _create_payloads(self):
        self.client.create_payload_index(
            collection_name=self.collection_name,
            field_name="date",
            field_schema= PayloadSchemaType.KEYWORD
        )

        self.client.create_payload_index(
            collection_name=self.collection_name,
            field_name="time_stamp",
            field_schema= PayloadSchemaType.FLOAT
        )
    
    async def _embed_all_activities(self, activities):
        """Embed multiple activities in parallel"""
        tasks = []
        for activity in activities:
            tasks.append(self._embed_activity(activity[1]))
        return await asyncio.gather(*tasks)
    
    def batch_embed(self, activities):
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

        embedding = client.models.embed_content(
            model="text-embedding-004",
            contents= activities,
            config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT")
        )

        return [e.values for e in embedding.embeddings]

    
    async def _embed_activity(self, activity_text: str):
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

        embedding = client.models.embed_content(
            model="text-embedding-004",
            contents= activity_text,
            config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT")
        )

        return embedding.embeddings[0].values

    
    def embed_query(self, query: str):
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

        embedding = client.models.embed_content(
            model="text-embedding-004",
            contents= query,
            config=types.EmbedContentConfig(task_type="RETRIEVAL_QUERY")
        )

        return embedding.embeddings[0].values
    
    def search_for_runs_by_embedding(self, vectorized_query):
        search_results = self.client.query_points(
            collection_name=self.collection_name,
            query=vectorized_query,
            # search filter allows us to filter by fields on the payload
            # query_filter=search_filter,
            limit=3,
            score_threshold=self.score_threshold,
        )

        return search_results

    
    def search_runs_by_date(self, date: str):
        search_filter = Filter(
            must=[
                FieldCondition(key="date", match=MatchValue(value=date))
            ]
        )

        search_result = self.client.scroll(
            collection_name=self.collection_name,
            scroll_filter= search_filter
        )

        return search_result

    def search_for_runs_by_n(self, n: int):
        search_result = self.client.scroll(
            collection_name=self.collection_name,
            limit=n,
            order_by=OrderBy(
                key="time_stamp",
                direction= "desc"
            )
        )

        return search_result
    
    def insert_points(self, points):
        points_to_be_inserted = []

        activites =[]
        for p in points:
            activites.append(p[1])

        vectors = self.batch_embed(activites)
        
        for point_data, vector in zip(points, vectors):
            run_json = point_data[0]
            
            date_str = str(run_json["date"])
            date_str = date_str.replace("Z", "+00:00")
            todays_date = datetime.fromisoformat(date_str)
            todays_date = todays_date.strftime("%Y-%m-%d")

            todays_date_obj = datetime.fromisoformat(date_str)
            time_stamp = int(todays_date_obj.timestamp())

            point = PointStruct(
                id=str(uuid.uuid4()),
                vector=vector,
                payload={
                    "run": run_json,
                    "date": todays_date,
                    "time_stamp": time_stamp,
                    "strava_id": "1"
                }
            )
            points_to_be_inserted.append(point)

        self.client.upsert(
            collection_name=self.collection_name,
            points=points_to_be_inserted
        )

qdrant_service = QdrantService()


    

