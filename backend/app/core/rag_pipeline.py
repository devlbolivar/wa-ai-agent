# Embedding + retrieval + augment
"""
RAG Pipeline.
Manages embeddings and vector search using Qdrant.

Each tenant has its own namespace (collection) in Qdrant:
    tenant_{uuid} → isolated vector space

Flow:
    1. Admin uploads KB entry → generate embedding → store in Qdrant
    2. Patient asks question → embed question → search Qdrant → return top K results
"""

import logging
from uuid import UUID
from dataclasses import dataclass

import httpx
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
)

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass
class RetrievedChunk:
    """A piece of knowledge retrieved from the vector DB."""
    content: str
    title: str
    category: str
    score: float
    kb_id: str


class RAGPipeline:
    """
    Retrieval-Augmented Generation pipeline.
    Handles embedding generation and vector similarity search.
    """

    EMBEDDING_MODEL = "text-embedding-3-small"
    EMBEDDING_DIM = 1536
    TOP_K = 4  # Number of results to retrieve

    def __init__(self):
        self.qdrant = QdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
        )
        self.openai_api_key = settings.openai_api_key

    # ============================================
    # Collection Management (per tenant)
    # ============================================
    def _collection_name(self, tenant_id: UUID) -> str:
        """Each tenant gets its own collection: tenant_{uuid}"""
        return f"tenant_{str(tenant_id).replace('-', '_')}"

    async def ensure_collection(self, tenant_id: UUID):
        """Create the Qdrant collection for a tenant if it doesn't exist."""
        collection_name = self._collection_name(tenant_id)

        try:
            self.qdrant.get_collection(collection_name)
            logger.debug(f"Collection exists: {collection_name}")
        except Exception:
            self.qdrant.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=self.EMBEDDING_DIM,
                    distance=Distance.COSINE,
                ),
            )
            logger.info(f"Collection created: {collection_name}")

    # ============================================
    # Embedding Generation
    # ============================================
    async def generate_embedding(self, text: str) -> list[float]:
        """
        Generate an embedding vector using OpenAI's API.
        Uses text-embedding-3-small: cheap ($0.02/1M tokens), 1536 dims.
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/embeddings",
                headers={
                    "Authorization": f"Bearer {self.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.EMBEDDING_MODEL,
                    "input": text,
                },
            )
            response.raise_for_status()
            data = response.json()

        embedding = data["data"][0]["embedding"]
        logger.debug(f"Embedding generated: {len(embedding)} dims for '{text[:50]}...'")
        return embedding

    # ============================================
    # Index: Store KB entry in Qdrant
    # ============================================
    async def index_knowledge(
        self,
        tenant_id: UUID,
        kb_id: str,
        title: str,
        content: str,
        category: str = "general",
    ):
        """
        Vectorize and store a knowledge base entry.

        Args:
            tenant_id: Tenant UUID
            kb_id: Knowledge base entry ID (from PostgreSQL)
            title: Entry title (e.g., "Blanqueamiento dental")
            content: Full text content to embed
            category: Category for filtering (e.g., "servicios", "precios", "horarios")
        """
        await self.ensure_collection(tenant_id)
        collection_name = self._collection_name(tenant_id)

        # Combine title + content for richer embedding
        text_to_embed = f"{title}\n{content}"
        embedding = await self.generate_embedding(text_to_embed)

        # Store in Qdrant with metadata
        self.qdrant.upsert(
            collection_name=collection_name,
            points=[
                PointStruct(
                    id=kb_id,  # Use the same ID as PostgreSQL
                    vector=embedding,
                    payload={
                        "title": title,
                        "content": content,
                        "category": category,
                        "kb_id": kb_id,
                    },
                )
            ],
        )

        logger.info(
            f"Indexed KB entry: '{title}' in {collection_name} (category={category})"
        )

    # ============================================
    # Retrieve: Search for relevant knowledge
    # ============================================
    async def retrieve(
        self,
        tenant_id: UUID,
        query: str,
        category: str | None = None,
        top_k: int | None = None,
    ) -> list[RetrievedChunk]:
        """
        Search the tenant's knowledge base for relevant entries.

        Args:
            tenant_id: Tenant UUID
            query: The user's question or message
            category: Optional category filter
            top_k: Number of results (default: self.TOP_K)

        Returns:
            List of RetrievedChunk with content, scores, and metadata
        """
        collection_name = self._collection_name(tenant_id)
        k = top_k or self.TOP_K

        try:
            # Embed the query
            query_embedding = await self.generate_embedding(query)

            # Build optional category filter
            search_filter = None
            if category:
                search_filter = Filter(
                    must=[
                        FieldCondition(
                            key="category",
                            match=MatchValue(value=category),
                        )
                    ]
                )

            # Search Qdrant
            results = self.qdrant.search(
                collection_name=collection_name,
                query_vector=query_embedding,
                query_filter=search_filter,
                limit=k,
                score_threshold=0.3,  # Minimum similarity score
            )

            chunks = [
                RetrievedChunk(
                    content=hit.payload.get("content", ""),
                    title=hit.payload.get("title", ""),
                    category=hit.payload.get("category", ""),
                    score=hit.score,
                    kb_id=hit.payload.get("kb_id", ""),
                )
                for hit in results
            ]

            logger.info(
                f"RAG retrieve: '{query[:50]}...' → {len(chunks)} results "
                f"(top score: {chunks[0].score:.3f})" if chunks else
                f"RAG retrieve: '{query[:50]}...' → 0 results"
            )

            return chunks

        except Exception as e:
            logger.exception(f"RAG retrieve error: {e}")
            return []

    # ============================================
    # Delete: Remove KB entry from Qdrant
    # ============================================
    async def delete_knowledge(self, tenant_id: UUID, kb_id: str):
        """Remove a KB entry from the vector store."""
        collection_name = self._collection_name(tenant_id)

        try:
            self.qdrant.delete(
                collection_name=collection_name,
                points_selector=[kb_id],
            )
            logger.info(f"Deleted KB entry {kb_id} from {collection_name}")
        except Exception as e:
            logger.exception(f"Error deleting from Qdrant: {e}")

    # ============================================
    # Reindex: Rebuild entire KB for a tenant
    # ============================================
    async def reindex_tenant(self, tenant_id: UUID, entries: list[dict]):
        """
        Rebuild the entire vector index for a tenant.
        Useful after bulk edits or imports.

        Args:
            entries: List of dicts with keys: kb_id, title, content, category
        """
        collection_name = self._collection_name(tenant_id)

        # Delete and recreate collection
        try:
            self.qdrant.delete_collection(collection_name)
        except Exception:
            pass

        self.qdrant.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(
                size=self.EMBEDDING_DIM,
                distance=Distance.COSINE,
            ),
        )

        # Index all entries
        for entry in entries:
            await self.index_knowledge(
                tenant_id=tenant_id,
                kb_id=entry["kb_id"],
                title=entry["title"],
                content=entry["content"],
                category=entry.get("category", "general"),
            )

        logger.info(f"Reindexed {len(entries)} entries for {collection_name}")


# Singleton
rag_pipeline = RAGPipeline()