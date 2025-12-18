"""
Knowledge Store for Company Intelligence Agent
Vector storage using AWS Titan embeddings for semantic search
"""

import json
import logging
import hashlib
import math
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from dataclasses import dataclass, field, asdict
import sqlite3
import os

logger = logging.getLogger(__name__)


@dataclass
class KnowledgeChunk:
    """A chunk of knowledge with its embedding"""
    id: str
    content: str
    url: str
    title: str
    page_type: str
    chunk_index: int
    total_chunks: int
    embedding: Optional[List[float]] = None
    created_at: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchResult:
    """A search result with relevance score"""
    chunk: KnowledgeChunk
    score: float
    context: str = ""


class KnowledgeStore:
    """
    Vector-based knowledge store using AWS Titan embeddings.
    Stores company knowledge and enables semantic search.
    """

    EMBEDDING_MODEL = "amazon.titan-embed-text-v1"
    EMBEDDING_DIMENSION = 1536  # Titan embedding dimension

    def __init__(
        self,
        bedrock_client,
        db_path: str = "knowledge_store.db",
        user_id: Optional[str] = None
    ):
        """
        Initialize the knowledge store.

        Args:
            bedrock_client: AWS Bedrock client
            db_path: Path to SQLite database
            user_id: User ID for multi-tenant storage
        """
        self.bedrock_client = bedrock_client
        self.user_id = user_id or "default"

        # Use user-specific database
        if user_id:
            db_dir = os.path.dirname(db_path) or "."
            db_name = f"knowledge_{user_id}.db"
            self.db_path = os.path.join(db_dir, db_name)
        else:
            self.db_path = db_path

        self._init_database()

    def _init_database(self):
        """Initialize SQLite database for storage"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Knowledge chunks table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS knowledge_chunks (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                content TEXT,
                url TEXT,
                title TEXT,
                page_type TEXT,
                chunk_index INTEGER,
                total_chunks INTEGER,
                embedding BLOB,
                created_at TEXT,
                metadata TEXT
            )
        """)

        # Company profile table (basic info)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS company_profile (
                user_id TEXT PRIMARY KEY,
                domain TEXT,
                company_name TEXT,
                total_chunks INTEGER DEFAULT 0,
                total_pages INTEGER DEFAULT 0,
                last_crawl TEXT,
                crawl_status TEXT DEFAULT 'none',
                metadata TEXT
            )
        """)

        # Crawl history
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS crawl_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                domain TEXT,
                pages_crawled INTEGER,
                chunks_created INTEGER,
                started_at TEXT,
                completed_at TEXT,
                status TEXT,
                errors TEXT
            )
        """)

        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_user ON knowledge_chunks(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_page_type ON knowledge_chunks(page_type)")

        conn.commit()
        conn.close()

    async def get_embedding(self, text: str) -> List[float]:
        """
        Get embedding vector for text using AWS Titan.

        Args:
            text: Text to embed

        Returns:
            List of floats representing the embedding
        """
        try:
            # Truncate long text
            text = text[:8000]

            response = self.bedrock_client.invoke_model(
                modelId=self.EMBEDDING_MODEL,
                body=json.dumps({
                    "inputText": text
                })
            )

            response_body = json.loads(response["body"].read())
            return response_body["embedding"]

        except Exception as e:
            logger.error(f"Embedding error: {e}")
            # Return zero vector as fallback
            return [0.0] * self.EMBEDDING_DIMENSION

    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """Calculate cosine similarity between two vectors (pure Python)"""
        if len(a) != len(b):
            return 0.0

        dot_product = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return dot_product / (norm_a * norm_b)

    async def add_chunk(self, chunk: KnowledgeChunk) -> str:
        """
        Add a knowledge chunk to the store.

        Args:
            chunk: The knowledge chunk to add

        Returns:
            The chunk ID
        """
        # Generate ID if not set
        if not chunk.id:
            chunk.id = hashlib.md5(
                f"{chunk.url}:{chunk.chunk_index}:{chunk.content[:100]}".encode()
            ).hexdigest()

        # Get embedding if not set
        if not chunk.embedding:
            chunk.embedding = await self.get_embedding(chunk.content)

        chunk.created_at = chunk.created_at or datetime.utcnow().isoformat()

        # Store in database
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT OR REPLACE INTO knowledge_chunks
            (id, user_id, content, url, title, page_type, chunk_index, total_chunks, embedding, created_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            chunk.id,
            self.user_id,
            chunk.content,
            chunk.url,
            chunk.title,
            chunk.page_type,
            chunk.chunk_index,
            chunk.total_chunks,
            json.dumps(chunk.embedding),  # Store as JSON blob
            chunk.created_at,
            json.dumps(chunk.metadata)
        ))

        conn.commit()
        conn.close()

        return chunk.id

    async def add_chunks_batch(self, chunks: List[KnowledgeChunk]) -> int:
        """
        Add multiple chunks efficiently.

        Args:
            chunks: List of chunks to add

        Returns:
            Number of chunks added
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        count = 0

        for chunk in chunks:
            try:
                if not chunk.id:
                    chunk.id = hashlib.md5(
                        f"{chunk.url}:{chunk.chunk_index}:{chunk.content[:100]}".encode()
                    ).hexdigest()

                if not chunk.embedding:
                    chunk.embedding = await self.get_embedding(chunk.content)

                chunk.created_at = chunk.created_at or datetime.utcnow().isoformat()

                cursor.execute("""
                    INSERT OR REPLACE INTO knowledge_chunks
                    (id, user_id, content, url, title, page_type, chunk_index, total_chunks, embedding, created_at, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    chunk.id,
                    self.user_id,
                    chunk.content,
                    chunk.url,
                    chunk.title,
                    chunk.page_type,
                    chunk.chunk_index,
                    chunk.total_chunks,
                    json.dumps(chunk.embedding),
                    chunk.created_at,
                    json.dumps(chunk.metadata)
                ))
                count += 1

            except Exception as e:
                logger.error(f"Error adding chunk: {e}")

        conn.commit()
        conn.close()

        return count

    async def search(
        self,
        query: str,
        top_k: int = 5,
        page_types: Optional[List[str]] = None,
        min_score: float = 0.3
    ) -> List[SearchResult]:
        """
        Semantic search over knowledge base.

        Args:
            query: Search query
            top_k: Number of results to return
            page_types: Filter by page types (e.g., ["product", "pricing"])
            min_score: Minimum similarity score

        Returns:
            List of SearchResult objects
        """
        # Get query embedding
        query_embedding = await self.get_embedding(query)

        # Get all chunks for this user
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        if page_types:
            placeholders = ",".join("?" * len(page_types))
            cursor.execute(f"""
                SELECT id, content, url, title, page_type, chunk_index, total_chunks, embedding, created_at, metadata
                FROM knowledge_chunks
                WHERE user_id = ? AND page_type IN ({placeholders})
            """, [self.user_id] + page_types)
        else:
            cursor.execute("""
                SELECT id, content, url, title, page_type, chunk_index, total_chunks, embedding, created_at, metadata
                FROM knowledge_chunks
                WHERE user_id = ?
            """, (self.user_id,))

        results = []
        for row in cursor.fetchall():
            chunk_embedding = json.loads(row[7])
            score = self._cosine_similarity(query_embedding, chunk_embedding)

            if score >= min_score:
                chunk = KnowledgeChunk(
                    id=row[0],
                    content=row[1],
                    url=row[2],
                    title=row[3],
                    page_type=row[4],
                    chunk_index=row[5],
                    total_chunks=row[6],
                    embedding=chunk_embedding,
                    created_at=row[8],
                    metadata=json.loads(row[9]) if row[9] else {}
                )
                results.append(SearchResult(chunk=chunk, score=score))

        conn.close()

        # Sort by score and return top_k
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:top_k]

    async def get_context_for_query(
        self,
        query: str,
        max_tokens: int = 2000
    ) -> str:
        """
        Get relevant context for a query, formatted for LLM use.

        Args:
            query: The query to find context for
            max_tokens: Approximate max tokens to return

        Returns:
            Formatted context string
        """
        results = await self.search(query, top_k=10)

        if not results:
            return "No relevant company information found."

        context_parts = []
        current_length = 0
        max_chars = max_tokens * 4  # Rough approximation

        for result in results:
            chunk = result.chunk
            part = f"[{chunk.page_type.upper()}] {chunk.title}\n{chunk.content}\n"

            if current_length + len(part) > max_chars:
                break

            context_parts.append(part)
            current_length += len(part)

        return "\n---\n".join(context_parts)

    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics about the knowledge store"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Total chunks
        cursor.execute(
            "SELECT COUNT(*) FROM knowledge_chunks WHERE user_id = ?",
            (self.user_id,)
        )
        total_chunks = cursor.fetchone()[0]

        # Chunks by page type
        cursor.execute("""
            SELECT page_type, COUNT(*)
            FROM knowledge_chunks
            WHERE user_id = ?
            GROUP BY page_type
        """, (self.user_id,))
        by_page_type = dict(cursor.fetchall())

        # Unique URLs
        cursor.execute(
            "SELECT COUNT(DISTINCT url) FROM knowledge_chunks WHERE user_id = ?",
            (self.user_id,)
        )
        unique_urls = cursor.fetchone()[0]

        # Get company profile
        cursor.execute(
            "SELECT domain, company_name, last_crawl FROM company_profile WHERE user_id = ?",
            (self.user_id,)
        )
        profile = cursor.fetchone()

        conn.close()

        return {
            "total_chunks": total_chunks,
            "by_page_type": by_page_type,
            "unique_pages": unique_urls,
            "domain": profile[0] if profile else None,
            "company_name": profile[1] if profile else None,
            "last_crawl": profile[2] if profile else None
        }

    def update_company_profile(
        self,
        domain: str,
        company_name: Optional[str] = None,
        total_chunks: Optional[int] = None,
        total_pages: Optional[int] = None,
        crawl_status: Optional[str] = None,
        metadata: Optional[Dict] = None
    ):
        """Update the company profile"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Check if exists
        cursor.execute(
            "SELECT 1 FROM company_profile WHERE user_id = ?",
            (self.user_id,)
        )
        exists = cursor.fetchone()

        if exists:
            updates = []
            values = []

            if domain:
                updates.append("domain = ?")
                values.append(domain)
            if company_name:
                updates.append("company_name = ?")
                values.append(company_name)
            if total_chunks is not None:
                updates.append("total_chunks = ?")
                values.append(total_chunks)
            if total_pages is not None:
                updates.append("total_pages = ?")
                values.append(total_pages)
            if crawl_status:
                updates.append("crawl_status = ?")
                values.append(crawl_status)
                updates.append("last_crawl = ?")
                values.append(datetime.utcnow().isoformat())
            if metadata:
                updates.append("metadata = ?")
                values.append(json.dumps(metadata))

            if updates:
                values.append(self.user_id)
                cursor.execute(
                    f"UPDATE company_profile SET {', '.join(updates)} WHERE user_id = ?",
                    values
                )
        else:
            cursor.execute("""
                INSERT INTO company_profile
                (user_id, domain, company_name, total_chunks, total_pages, crawl_status, last_crawl, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                self.user_id,
                domain,
                company_name,
                total_chunks or 0,
                total_pages or 0,
                crawl_status or "none",
                datetime.utcnow().isoformat(),
                json.dumps(metadata or {})
            ))

        conn.commit()
        conn.close()

    def clear_knowledge(self):
        """Clear all knowledge for this user"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            "DELETE FROM knowledge_chunks WHERE user_id = ?",
            (self.user_id,)
        )
        cursor.execute(
            "DELETE FROM company_profile WHERE user_id = ?",
            (self.user_id,)
        )

        conn.commit()
        conn.close()

    def log_crawl(
        self,
        domain: str,
        pages_crawled: int,
        chunks_created: int,
        started_at: str,
        completed_at: str,
        status: str,
        errors: List[str]
    ):
        """Log a crawl operation"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO crawl_history
            (user_id, domain, pages_crawled, chunks_created, started_at, completed_at, status, errors)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            self.user_id,
            domain,
            pages_crawled,
            chunks_created,
            started_at,
            completed_at,
            status,
            json.dumps(errors)
        ))

        conn.commit()
        conn.close()


class InMemoryKnowledgeStore:
    """
    In-memory knowledge store for testing or small datasets.
    No persistence, but faster for development.
    """

    def __init__(self, bedrock_client):
        self.bedrock_client = bedrock_client
        self.chunks: Dict[str, KnowledgeChunk] = {}
        self.user_id = "memory"

    async def get_embedding(self, text: str) -> List[float]:
        """Get embedding from Bedrock"""
        try:
            text = text[:8000]
            response = self.bedrock_client.invoke_model(
                modelId="amazon.titan-embed-text-v1",
                body=json.dumps({"inputText": text})
            )
            response_body = json.loads(response["body"].read())
            return response_body["embedding"]
        except Exception as e:
            logger.error(f"Embedding error: {e}")
            return [0.0] * 1536

    async def add_chunk(self, chunk: KnowledgeChunk) -> str:
        if not chunk.id:
            chunk.id = hashlib.md5(f"{chunk.url}:{chunk.chunk_index}".encode()).hexdigest()
        if not chunk.embedding:
            chunk.embedding = await self.get_embedding(chunk.content)
        chunk.created_at = chunk.created_at or datetime.utcnow().isoformat()
        self.chunks[chunk.id] = chunk
        return chunk.id

    async def search(self, query: str, top_k: int = 5, **kwargs) -> List[SearchResult]:
        query_embedding = await self.get_embedding(query)

        results = []
        for chunk in self.chunks.values():
            if chunk.embedding:
                score = self._cosine_similarity(query_embedding, chunk.embedding)
                if score > 0.3:
                    results.append(SearchResult(chunk=chunk, score=score))

        results.sort(key=lambda x: x.score, reverse=True)
        return results[:top_k]

    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """Calculate cosine similarity between two vectors (pure Python)"""
        if len(a) != len(b):
            return 0.0
        dot_product = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot_product / (norm_a * norm_b)

    def get_statistics(self) -> Dict[str, Any]:
        return {
            "total_chunks": len(self.chunks),
            "unique_pages": len(set(c.url for c in self.chunks.values()))
        }

    def clear_knowledge(self):
        self.chunks.clear()
