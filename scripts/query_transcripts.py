import os
import sys
from dotenv import load_dotenv
import psycopg2
from psycopg2 import sql
import argparse

load_dotenv()

DB_HOST=os.getenv("DB_HOST","localhost")
DB_PORT=os.getenv("DB_PORT","5432")
DB_NAME=os.getenv("DB_NAME","youtube_transcripts")
DB_USER=os.getenv("DB_USER","postgres")
DB_PASSWORD=os.getenv("DB_PASSWORD","postgres")

def get_db_connection():
    try:
        connection = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME
        )
        return connection
    except psycopg2.OperationalError as e:
        print(f"Error connecting to database: {e}")
        print("Please ensure your PostgreSQL server is running and your .env variables are correct.")
        sys.exit(1)

def query_database():
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        # Get total video amount from videos table
        cursor.execute("""
            SELECT COUNT(video_id) FROM videos;
        """)
        video_count = cursor.fetchone()[0]

        cursor.execute("""
            SELECT COUNT(id) FROM transcripts;
        """)
        transcript_count = cursor.fetchone()[0]

        return video_count, transcript_count
    except Exception as e:
        print(f"Error getting totals:{e}")
        return 0,0
    finally:
        cursor.close()
        connection.close()

def search_by_keyword(keyword):
    """
    Searches the transcripts table for the given keyword (case-insensitive) 
    and prints matching snippets.
    
    :param keyword: The keyword user would like to search
    """
    if not keyword:
        print("Error: Keyword cannot be empty for search.")
        return
    
    connection = get_db_connection()
    cursor = connection.cursor()
    
    try:
        search_pattern = f"%{keyword}%" 
        
        cursor.execute("""
            SELECT 
                video_id, 
                start_time, 
                text 
            FROM transcripts
            WHERE text ILIKE %s
            ORDER BY start_time ASC;
        """, (search_pattern,))
        
        snippets = cursor.fetchall()

        print(f"\n--- Search Results for '{keyword}' ---")
        
        if snippets:
            print(f"Found {len(snippets)} results.")
            print(f"| {'Video ID':<11} | {'Start (sec)':<11} | {'Text':<50} |")
            print("-" * 82)
            for vid_id, start_time, text in snippets:
                display_text = text.replace('\n', ' ')
                print(f"| {vid_id:<11} | {start_time:<11.2f} | {display_text:<50} |")
        else:
            print("No matching transcripts found.")
        
    except Exception as e:
        print(f"Error executing keyword search: {e}")
    finally:
        cursor.close()
        connection.close()

if __name__ == "__main__":
    
    parser = argparse.ArgumentParser(
        description="Utility for querying the YouTube transcript database.",
        epilog="Use -k <keyword> to search transcripts"
    )

    parser.add_argument(
        '-k', '--keyword', 
        type=str, 
        help="Keyword to search for in the transcript texts.",
        default=None
    )

    args = parser.parse_args()
    
    if args.keyword:
        search_by_keyword(args.keyword)
    else:
        v_count, t_count = query_database()
        print("--- Database Counts ---")
        print(f"Total Videos: {v_count}")
        print(f"Total Transcript Snippets: {t_count}")