import os
import sys
from dotenv import load_dotenv
import psycopg2
from psycopg2 import sql

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "youtube_transcripts")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD")

def init_database():
    connection = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
        )
    
    cursor = connection.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS video (
            id SERIAL PRIMARY KEY,
            video_id VARCHAR(255) UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transcripts (
            id SERIAL PRIMARY KEY,
            video_id VARCHAR(255) NOT NULL REFERENCES videos(video_id),
            text TEXT NOT NULL,
            start_time FLOAT,
            duration FLOAT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transcript_enrichments (
            id SERIAL PRIMARY KEY,
            video_id VARCHAR(255) NOT NULL REFERENCES videos(video_id),
            language VARCHAR(10),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Create indexes for performance
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_videos_video_id ON videos(video_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_transcripts_video_id ON transcripts(video_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_enrichments_video_id ON transcript_enrichments(video_id)")
    
    connection.commit()
    connection.close()