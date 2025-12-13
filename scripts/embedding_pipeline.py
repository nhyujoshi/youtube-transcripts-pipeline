import os
import re
import json
import threading
import queue
import time
from datetime import datetime
from typing import Dict, List, Optional
import psycopg2
from psycopg2.extras import execute_values
from openai import OpenAI
from tenacity import (
    retry,
    wait_random_exponential,
    stop_after_attempt,
    retry_if_not_exception_type,
)
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL')

if DATABASE_URL:
    import re
    from urllib.parse import urlparse, parse_qs
    
    # Parse the URL
    parsed = urlparse(DATABASE_URL)
    
    DB_USER = parsed.username
    DB_PASSWORD = parsed.password
    DB_HOST = parsed.hostname
    DB_PORT = parsed.port or 5432
    DB_NAME = parsed.path.lstrip('/')
    
    print(f"✓ Using hosted database: {DB_HOST}")
else:
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = os.getenv("DB_PORT", "5432")
    DB_NAME = os.getenv("DB_NAME", "youtube_transcripts")
    DB_USER = os.getenv("DB_USER", "postgres")
    DB_PASSWORD = os.getenv("DB_PASSWORD")

# Embedding configuration
EMBEDDING_MODEL = "nomic-ai/nomic-embed-text-v1.5-GGUF"
EMBEDDING_BATCH_SIZE = 20  # Process 20 texts per API call
PROCESSING_THREADS = 3

# OpenAI client
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY", "not-needed"),
    base_url=os.getenv("OPENAI_BASE_URL", "http://127.0.0.1:1234/v1")
)

# Thread-safe progress tracking
progress_lock = threading.Lock()
completed_count = 0
total_count = 0


# ==================== TEXT PROCESSING ====================

def normalize_text(s: str) -> str:
    """Normalize text by removing extra spaces and newlines."""
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\. ,", "", s)
    s = s.replace("..", ".")
    s = s.replace(". .", ".")
    s = s.replace("\n", " ")
    s = s.strip()
    return s


def chunk_transcript_by_time(
    transcript_entries: List[Dict],
    segment_minutes: int = 3,
    overlap_words: int = 20
) -> List[Dict]:
    """Split transcript into time-based segments with word overlap.

    Args:
        transcript_entries: List of {'text': ..., 'start': ..., 'duration': ...}
        segment_minutes: Length of each segment in minutes
        overlap_words: Number of words to overlap between segments

    Returns:
        List of segment dicts with keys:
        - text: The segment text
        - start_time_seconds: Start time in seconds
        - duration: Duration in seconds
    """
    if not transcript_entries:
        return []

    segment_seconds = segment_minutes * 60
    segments = []

    current_segment = {
        'words': [],
        'start_time': None,
        'end_time': 0
    }

    for entry in transcript_entries:
        entry_text = entry.get('text', '').strip()
        entry_start = entry.get('start_time', 0) or entry.get('start', 0)
        entry_duration = entry.get('duration', 0)
        entry_end = entry_start + entry_duration

        if not entry_text:
            continue

        # Initialize first segment
        if current_segment['start_time'] is None:
            current_segment['start_time'] = entry_start

        # Add words to current segment
        words = entry_text.split()
        current_segment['words'].extend(words)
        current_segment['end_time'] = entry_end

        # Check if segment is complete (reached time limit)
        duration = current_segment['end_time'] - current_segment['start_time']

        if duration >= segment_seconds:
            # Save completed segment
            segment_text = ' '.join(current_segment['words'])
            segments.append({
                'text': normalize_text(segment_text),
                'start_time_seconds': current_segment['start_time'],
                'duration': duration
            })

            # Start new segment with overlap
            overlap_text = current_segment['words'][-overlap_words:] if len(current_segment['words']) > overlap_words else []
            current_segment = {
                'words': overlap_text,
                'start_time': entry_end,
                'end_time': entry_end
            }

    # Add final segment if it has content
    if current_segment['words'] and current_segment['start_time'] is not None:
        segment_text = ' '.join(current_segment['words'])
        duration = current_segment['end_time'] - current_segment['start_time']
        segments.append({
            'text': normalize_text(segment_text),
            'start_time_seconds': current_segment['start_time'],
            'duration': duration
        })

    return segments


# EMBEDDING GENERATION

@retry(
    wait=wait_random_exponential(min=1, max=30),
    stop=stop_after_attempt(10),
    retry=retry_if_not_exception_type(Exception),
)
def get_text_embedding(text: str) -> List[float]:
    """Get embedding for a single text with automatic retries."""
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text
    )
    return response.data[0].embedding


def process_embeddings_batch(texts: List[str]) -> Optional[List[List[float]]]:
    """Generate embeddings for multiple texts in ONE API call.
    
    Returns list of embeddings or None if failed.
    """
    try:
        response = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=texts
        )
        return [item.embedding for item in response.data]
    except Exception as e:
        print(f"✗ Embedding batch failed: {e}")
        return None


# ==================== DATABASE OPERATIONS ====================

def get_connection():
    """Create a database connection."""
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
    )


def fetch_video_transcripts(video_id: str) -> List[Dict]:
    """Fetch all transcript entries for a video."""
    conn = get_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("""
            SELECT text, start_time, duration
            FROM transcripts
            WHERE video_id = %s
            ORDER BY start_time
        """, (video_id,))
        
        rows = cur.fetchall()
        return [
            {'text': row[0], 'start_time': row[1], 'duration': row[2]}
            for row in rows
        ]
    finally:
        cur.close()
        conn.close()


def get_unprocessed_videos() -> List[str]:
    """Get list of videos that haven't been chunked yet."""
    conn = get_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("""
            SELECT DISTINCT v.video_id
            FROM videos v
            WHERE NOT EXISTS (
                SELECT 1 FROM text_chunks tc
                WHERE tc.video_id = v.video_id
            )
            AND EXISTS (
                SELECT 1 FROM transcripts t
                WHERE t.video_id = v.video_id
            )
        """)
        
        return [row[0] for row in cur.fetchall()]
    finally:
        cur.close()
        conn.close()


def insert_chunks_with_embeddings(video_id: str, chunks: List[Dict]) -> bool:
    """Insert multiple text chunks with embeddings.
    
    chunks = [
        {
            'text': '...',
            'start_time_seconds': 0.0,
            'duration': 180.0,
            'embedding': [0.1, 0.2, ...]
        }
    ]
    """
    if not chunks:
        return True
        
    conn = get_connection()
    cur = conn.cursor()

    try:
        # Prepare data for bulk insert
        values = []
        for i, chunk in enumerate(chunks):
            chunk_id = f"{video_id}_chunk_{i}_{int(chunk['start_time_seconds'])}"
            
            # Format embedding as PostgreSQL array
            embedding = chunk.get('embedding')
            if embedding:
                embedding_str = '[' + ','.join(map(str, embedding)) + ']'
            else:
                embedding_str = None
            
            values.append((
                chunk_id,
                video_id,
                chunk['text'],
                chunk['start_time_seconds'],
                chunk.get('duration'),
                embedding_str,
                'embedded' if embedding else 'pending',
                datetime.utcnow()
            ))
        
        # Bulk insert with ON CONFLICT
        execute_values(
            cur,
            """
            INSERT INTO text_chunks
            (id, video_id, text, start_time_seconds, duration, embedding, status, created_at)
            VALUES %s
            ON CONFLICT (id) DO NOTHING
            """,
            values
        )
        
        conn.commit()
        return True
        
    except Exception as e:
        print(f"✗ Failed to insert chunks for {video_id}: {e}")
        conn.rollback()
        return False
    finally:
        cur.close()
        conn.close()


# ==================== PROCESSING PIPELINE ====================

def process_video_embeddings(video_id: str) -> bool:
    """Complete pipeline for one video: chunk + embed + store."""
    global completed_count
    
    try:
        # 1. Fetch transcript entries
        transcript_entries = fetch_video_transcripts(video_id)
        if not transcript_entries:
            print(f"✗ No transcript entries for {video_id}")
            return False
        
        # 2. Chunk the transcript
        chunks = chunk_transcript_by_time(
            transcript_entries,
            segment_minutes=3,
            overlap_words=20
        )
        
        if not chunks:
            print(f"✗ No chunks generated for {video_id}")
            return False
        
        # 3. Generate embeddings in batches
        texts = [chunk['text'] for chunk in chunks]
        all_embeddings = []
        
        for i in range(0, len(texts), EMBEDDING_BATCH_SIZE):
            batch_texts = texts[i:i + EMBEDDING_BATCH_SIZE]
            embeddings = process_embeddings_batch(batch_texts)
            
            if embeddings:
                all_embeddings.extend(embeddings)
            else:
                print(f"✗ Failed to generate embeddings for batch {i // EMBEDDING_BATCH_SIZE + 1}")
                return False
            
            # Small delay between batches
            time.sleep(0.5)
        
        # 4. Attach embeddings to chunks
        for chunk, embedding in zip(chunks, all_embeddings):
            chunk['embedding'] = embedding
        
        # 5. Store in database
        success = insert_chunks_with_embeddings(video_id, chunks)
        
        if success:
            with progress_lock:
                completed_count += 1
                print(f"✓ [{completed_count}/{total_count}] Processed {video_id} ({len(chunks)} chunks)")
            return True
        else:
            return False
            
    except Exception as e:
        print(f"✗ Error processing {video_id}: {e}")
        return False


def process_from_queue(q: queue.Queue):
    """Worker function that processes videos from the queue."""
    while True:
        try:
            video_id = q.get(timeout=1)
            process_video_embeddings(video_id)
            q.task_done()
        except queue.Empty:
            break
        except Exception as e:
            print(f"✗ Error in worker thread: {e}")
            q.task_done()


def main():
    """Main function to process all unprocessed videos."""
    global total_count
    
    print("Fetching unprocessed videos...")
    video_ids = get_unprocessed_videos()
    total_count = len(video_ids)
    
    if total_count == 0:
        print("No videos to process!")
        return
    
    print(f"Found {total_count} videos to process with {PROCESSING_THREADS} threads.\n")
    
    # Create queue and add all video IDs
    q = queue.Queue()
    for video_id in video_ids:
        q.put(video_id)
    
    # Create and start worker threads
    threads = []
    for i in range(PROCESSING_THREADS):
        t = threading.Thread(
            target=lambda: process_from_queue(q),
            name=f"Worker-{i+1}"
        )
        t.daemon = True
        t.start()
        threads.append(t)
    
    # Wait for completion
    q.join()
    for t in threads:
        t.join()
    
    print(f"\n{'='*60}")
    print(f"Processing complete! {completed_count}/{total_count} videos processed.")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()