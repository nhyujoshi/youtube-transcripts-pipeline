import os
import sys
from dotenv import load_dotenv
import psycopg2
from psycopg2 import sql
import argparse
import re
from collections import Counter

load_dotenv()

DB_HOST=os.getenv("DB_HOST","localhost")
DB_PORT=os.getenv("DB_PORT","5432")
DB_NAME=os.getenv("DB_NAME","youtube_transcripts")
DB_USER=os.getenv("DB_USER","postgres")
DB_PASSWORD=os.getenv("DB_PASSWORD","postgres")

STOP_WORDS = set([
    'the', 'a', 'an', 'is', 'it', 'he', 'she', 'we', 'they', 'you', 'i', 
    'to', 'of', 'and', 'in', 'on', 'at', 'for', 'with', 'about', 'as', 
    'by', 'or', 'so', 'if', 'but', 'not', 'what', 'where', 'when', 'why', 
    'how', 'this', 'that', 'these', 'those', 'just', 'like', 'get', 'up',
    'down', 'out', 'be', 'been', 'have', 'had', 'do', 'does', 'did', 'will', 
    'would', 'can', 'could', 'one', 'two', 'three', 'four', 'five', 'time',
    'know', 'all', 'from', 'really', 'very', 'gonna', 'wanna', 'yeah', 'okay', 
    'it\'s', 'i\'m', 'you\'re', 'that\'s', 'we\'re', 'they\'re', 'don\'t', 'we', 'um', 
    'yeah', 'right', 'so', 'going', 'me', 'some', 'lot', 'a lot', 'way',
    'little', 'back', 'make', 'want', 'think', 'see', 'good', 'now', 'here', 'then', 'our',
    'because', 'which', 'well', 'its', 'are'
])

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

def fetch_all_transcript_text():
    """Fetches all 'text' content from the transcripts table."""
    connection = get_db_connection()
    cursor = connection.cursor()
    
    try:
        print("Fetching all transcript text from the database...")
        cursor.execute("SELECT text FROM transcripts ORDER BY video_id;")
        
        text_rows = cursor.fetchall()
        
        all_text = [row[0] for row in text_rows]
        
        print(f"Successfully retrieved text from {len(all_text)} transcript snippets.")
        return all_text
        
    except Exception as e:
        print(f"Error fetching transcript text: {e}")
        return []
    finally:
        cursor.close()
        connection.close()

def analyze_common_words(text_list, max_num):
    """
    Counts most common words in all transcript text
    in the database
    
    :param text_list: List of transcript texts
    :param max_num: Max number of most common words user would like to see
    """
    word_counter = Counter()

    for text in text_list:
        cleaned_text = re.sub(r"[^a-z\s]", "", text.lower())
        words = cleaned_text.split()

        filtered_words = [
            word
            for word in words
            if len(word) > 2 and word not in STOP_WORDS
        ]

        word_counter.update(filtered_words)

    most_common = word_counter.most_common(max_num)

    return most_common

if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="Analyzes all YouTube transcript text in the database to find the most common words.",
        epilog="Use -n to specify the max number of words to display."
    )

    parser.add_argument(
        '-n', '--number', 
        type=int, 
        default=10, 
        help="The number of top common words to display (default: 10)."
    )
    
    args = parser.parse_args()
    max_num_count = args.number
    
    all_transcript_text = fetch_all_transcript_text()
    
    if all_transcript_text:
        print("\nAnalyzing word frequencies...")
        
        common_words = analyze_common_words(all_transcript_text, max_num_count)
        
        print(f"\n------- Top {len(common_words)} Most Common Words -------")
        
        for i, (word, count) in enumerate(common_words):
            print(f"| {i+1:>3}. | {word:<{12}} | {count} occurrences |")
        
        print("-" * 39)
    else:
        print("\nAnalysis failed: Could not retrieve any transcript text.")