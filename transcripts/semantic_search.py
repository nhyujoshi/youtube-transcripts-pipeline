"""Semantic search using pgvector cosine similarity."""

import os
import time
from openai import OpenAI
from django.db import connection
#from .models import Transcripts, Videos
from dotenv import load_dotenv

load_dotenv()

# OpenAI Client and Embedding
EMBEDDING_MODEL = "nomic-ai/nomic-embed-text-v1.5-GGUF"
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY", "not-needed"),
    base_url=os.getenv("OPENAI_BASE_URL", "http://127.0.0.1:1234/v1")
)

def semantic_search(query: str, video_id: str = None, top_k: int = 5) -> dict:
    """Find semantically similar transcripts using embeddings.

    Args:
        query: User's search query (e.g., "How do transformers work?")
        video_id: Optional - search specific video only
        top_k: Number of results to return

    Returns:
        Dict with results and metadata
    """
    start_time = time.time()

    # Step 1: Generate embedding for query
    try:
        query_response = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=query
        )
        query_embedding = query_response.data[0].embedding
    except Exception as e:
        return {
            'error': f'Failed to embed query: {str(e)}',
            'query': query
        }

    # Step 2: Format as pgvector expects
    embedding_str = '[' + ','.join(map(str, query_embedding)) + ']'

    # Step 3: Build SQL based on filters
    if video_id:
        where_clause = "WHERE t.video_id = %s AND t.embedding IS NOT NULL"
        params = [embedding_str, video_id, embedding_str, top_k]
    else:
        where_clause = "WHERE t.embedding IS NOT NULL"
        params = [embedding_str, embedding_str, top_k]

    # Step 4: Query database using pgvector <-> operator
    # <-> is cosine distance operator (lower = more similar)
    sql = f"""
    SELECT
        t.id,
        t.video_id,
        t.text,
        t.start_time_seconds,
        v.video_id as youtube_video_id,
        
        1 - (t.embedding <-> %s::vector) as similarity_score
    FROM text_chunks t
    JOIN videos v ON t.video_id = v.video_id
    {where_clause}
    ORDER BY t.embedding <-> %s::vector  -- Sort by distance (closest first)
    LIMIT %s
    """

    try:
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            columns = [col[0] for col in cursor.description]
            rows = cursor.fetchall()

        # Step 5: Format results
        results = [dict(zip(columns, row)) for row in rows]

        # Step 6: Add YouTube links with timestamps
        for result in results:
            if result['start_time_seconds']:
                mins = int(result['start_time_seconds'] // 60)
                secs = int(result['start_time_seconds'] % 60)
                result['youtube_url'] = (
                    f"https://youtube.com/watch?v="
                    f"{result['youtube_video_id']}&t={mins}m{secs}s"
                )

        execution_time = (time.time() - start_time) * 1000  # milliseconds

        return {
            'query': query,
            'results_count': len(results),
            'execution_time_ms': execution_time,
            'results': results
        }

    except Exception as e:
        return {
            'error': f'Search failed: {str(e)}',
            'query': query
        }