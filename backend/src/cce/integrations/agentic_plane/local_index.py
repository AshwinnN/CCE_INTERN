"""pgvector-backed local index implementation behind the AgenticPlane boundary."""

from __future__ import annotations

import os
import uuid
import hashlib
from typing import Callable

import psycopg2
import psycopg2.extras

from cce.integrations.agentic_plane.chunking import payload_chunks as _payload_chunks


DEFAULT_EMBEDDING_MODEL = "models/text-embedding-004"


class LocalIndexClient:
    def __init__(
        self,
        dsn: str,
        *,
        embed_texts: Callable[[list[str]], list[list[float]]] | None = None,
    ):
        self._dsn = dsn
        self._embed_texts = embed_texts

    def index(self, payload: dict) -> dict:
        if payload.get("change_type") == "deleted":
            return self.delete(payload["document_id"])

        chunks = list(_payload_chunks(payload))
        if not chunks:
            return {"status": "indexed", "indexed": 0}

        embeddings = self._embed([chunk["chunk_text"] for chunk in chunks])
        source_uuid = _source_uuid(payload["source_id"])
        with psycopg2.connect(self._dsn) as conn:
            with conn.cursor() as cur:
                for chunk, embedding in zip(chunks, embeddings):
                    cur.execute(
                        """
                        INSERT INTO cce_local_index_chunk (
                            chunk_id, document_id, source_id, chunk_text, embedding,
                            source_ref, version, object_id, trace_id, metadata
                        ) VALUES (%s, %s, %s, %s, %s::vector, %s, %s, %s, %s, %s)
                        """,
                        (
                            str(uuid.uuid4()),
                            payload["document_id"],
                            source_uuid,
                            chunk["chunk_text"],
                            _vector_literal(embedding),
                            payload.get("source_ref") or payload["document_id"],
                            payload.get("revision") or "",
                            payload.get("object_id") or payload["document_id"],
                            payload.get("trace_id") or "",
                            psycopg2.extras.Json(chunk.get("metadata", {})),
                        ),
                    )
                conn.commit()
        return {"status": "indexed", "indexed": len(chunks)}

    def search(self, query: str, *, limit: int = 5) -> list[dict]:
        embedding = self._embed([query])[0]
        with psycopg2.connect(self._dsn) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # MVP corpora use exact search; tiny datasets can make ivfflat return no rows.
                cur.execute("SET LOCAL enable_indexscan = off")
                cur.execute("SET LOCAL enable_bitmapscan = off")
                cur.execute(
                    """
                    SELECT document_id, chunk_text, source_id::text AS source_id,
                           source_ref, version, object_id, trace_id, metadata,
                           embedding <=> %s::vector AS distance
                    FROM cce_local_index_chunk
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """,
                    (_vector_literal(embedding), _vector_literal(embedding), limit),
                )
                rows = cur.fetchall()
        # Boundary convention: score is cosine similarity, so higher is better.
        return [
            {
                "document_id": row["document_id"],
                "chunk_text": row["chunk_text"],
                "source_id": row["source_id"],
                "score": 1.0 - float(row["distance"]),
                "provenance": {
                    "source_id": row["source_id"],
                    "source_ref": row["source_ref"],
                    "version": row["version"],
                    "object_id": row["object_id"],
                    "trace_id": row["trace_id"],
                },
                "metadata": row["metadata"],
            }
            for row in rows
        ]

    def delete(self, document_id: str) -> dict:
        with psycopg2.connect(self._dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM cce_local_index_chunk WHERE document_id = %s",
                    (document_id,),
                )
                deleted = cur.rowcount
                conn.commit()
        return {"status": "deleted", "deleted": deleted}

    def graph(self, *args, **kwargs):
        raise NotImplementedError("local graph operations are not implemented")

    def _embed(self, texts: list[str]) -> list[list[float]]:
        if self._embed_texts is not None:
            return self._embed_texts(texts)
        if os.environ.get("CCE_LOCAL_INDEX_EMBEDDING_MODE") == "hash":
            return [_hash_embedding(text) for text in texts]
        api_key = os.environ.get("CCE_LLM_API_KEY")
        if not api_key:
            raise RuntimeError("missing CCE_LLM_API_KEY for local index embeddings")
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        embeddings = GoogleGenerativeAIEmbeddings(
            model=os.environ.get("CCE_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL),
            google_api_key=api_key,
        )
        return embeddings.embed_documents(texts)


def _source_uuid(source_id: str) -> str:
    try:
        uuid.UUID(str(source_id))
        return str(source_id)
    except ValueError:
        return str(uuid.uuid5(uuid.UUID("6f1b1a2e-6c1a-4b8e-9f2a-9e3b7c2d5a10"), source_id))


def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(str(float(value)) for value in values) + "]"


def _hash_embedding(text: str, dimensions: int = 768) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    values = []
    while len(values) < dimensions:
        for byte in digest:
            values.append((byte / 255.0) - 0.5)
            if len(values) == dimensions:
                break
        digest = hashlib.sha256(digest).digest()
    return values
