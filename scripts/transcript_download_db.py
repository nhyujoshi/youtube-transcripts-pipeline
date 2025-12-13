import os
import sys
from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.proxies import WebshareProxyConfig
from youtube_transcript_api._errors import TranscriptsDisabled
from youtube_transcript_api.formatters import WebVTTFormatter
import psycopg2
from psycopg2 import sql
from dotenv import load_dotenv
import random
import time
import threading
import queue

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
    # Local database
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = os.getenv("DB_PORT", "5432")
    DB_NAME = os.getenv("DB_NAME", "youtube_transcripts")
    DB_USER = os.getenv("DB_USER", "postgres")
    DB_PASSWORD = os.getenv("DB_PASSWORD")

# Number of concurrent threads
PROCESSING_THREADS = 3

# Thread-safe counter for progress tracking
progress_lock = threading.Lock()
completed_count = 0
total_count = 0

def get_playlist_details(api_build, next_page_token, plistID=""):
    request = api_build.playlistItems().list(
        part="contentDetails",
        playlistId=plistID,
        maxResults=50,
        pageToken=next_page_token
    )
    response = request.execute()
    return response

def get_video_ids(playlistID=""):
    video_ids = []
    youtube = build("youtube", "v3", developerKey=os.getenv("GOOGLE_DEVELOPER_API_KEY"))
    next_page_token = None

    response = get_playlist_details(youtube, next_page_token, playlistID)

    # Extract video IDs
    for item in response['items']:
        video_ids.append(item['contentDetails']['videoId'])
    next_page_token = response.get('nextPageToken')
    while next_page_token is not None:
        response = get_playlist_details(youtube, next_page_token, playlistID)
        for item in response['items']:
            video_ids.append(item['contentDetails']['videoId'])
        next_page_token = response.get('nextPageToken')
    return video_ids

def get_video_transcripts(video_id):
    try:
        ytt_api = YouTubeTranscriptApi(
            proxy_config=WebshareProxyConfig(
                proxy_username=os.getenv("WEBSHARE_PROXY_USER"),
                proxy_password=os.getenv("WEBSHARE_PROXY_PASS"),
            ),
        )
    except Exception as e:
        print(f"Error initializing YouTubeTranscriptApi: {e}")
        return None
    
    fetched_transcript = {}
    
    try:
        fetched_object = ytt_api.fetch(video_id)
        fetched_transcript[video_id] = fetched_object.to_raw_data()
        return fetched_transcript
        
    except TranscriptsDisabled:
        print(f"✗ Transcript is disabled for video {video_id}.")
        return None
    except Exception as e:
        print(f"✗ Error fetching transcript for {video_id}: {e}")
        return None

def store_transcript(video_id, transcript):
    try:
        connection = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
        )
        cursor = connection.cursor()

        # Insert video (if not exists)
        cursor.execute(
            """
            INSERT INTO videos (video_id)
            VALUES (%s)
            ON CONFLICT (video_id) DO NOTHING
            """,
            (video_id,)
        )

        # Insert transcript entries
        transcript_data = [
            (video_id, each["text"], each["start"], each["duration"])
            for each in transcript
        ]
        
        insert_query = """
            INSERT INTO transcripts (video_id, text, start_time, duration)
            VALUES (%s, %s, %s, %s)
            """
        cursor.executemany(insert_query, transcript_data)

        connection.commit()
        cursor.close()
        connection.close()
        return True
        
    except Exception as db_e:
        print(f"✗ Database error storing {video_id}: {db_e}")
        return False

def process_video(video_id):
    """Process a single video: fetch transcript and store in DB"""
    global completed_count
    
    # Fetch transcript
    transcript_data = get_video_transcripts(video_id)
    
    if transcript_data:
        transcript_list = transcript_data.get(video_id, [])
        if transcript_list:
            # Store in database
            success = store_transcript(video_id, transcript_list)
            
            if success:
                with progress_lock:
                    completed_count += 1
                    print(f"✓ [{completed_count}/{total_count}] Successfully processed {video_id} ({len(transcript_list)} snippets)")
                return True
            else:
                print(f"✗ Failed to store {video_id}")
                return False
        else:
            print(f"✗ Empty transcript data for {video_id}")
            return False
    else:
        print(f"✗ Could not fetch transcript for {video_id}")
        return False
    
    return False

def process_from_queue(q):
    """Worker function that processes videos from the queue"""
    while True:
        try:
            # Get video_id from queue with timeout
            video_id = q.get(timeout=1)
            
            # Process the video
            process_video(video_id)
            
            # Add random delay to avoid rate limiting
            delay = random.uniform(2, 5)
            time.sleep(delay)
            
            # Mark task as done
            q.task_done()
            
        except queue.Empty:
            # Queue is empty, exit thread
            break
        except Exception as e:
            print(f"✗ Error in worker thread: {e}")
            q.task_done()

def main():
    global total_count
    
    # Fetch all video IDs from playlist
    print("Fetching video IDs from playlist...")
    video_ids = get_video_ids("PLZHQObOWTQDNU6R1_67000Dx_ZCJB-3pi")
    total_count = len(video_ids)
    print(f"Found {total_count} videos. Starting transcript fetch with {PROCESSING_THREADS} threads...\n")

    # Create queue and add all video IDs
    q = queue.Queue()
    for video_id in video_ids:
        q.put(video_id)

    # Create and start worker threads
    threads = []
    for i in range(PROCESSING_THREADS):
        t = threading.Thread(target=lambda: process_from_queue(q), name=f"Worker-{i+1}")
        t.daemon = True  # Thread will exit when main program exits
        t.start()
        threads.append(t)
        print(f"Started thread: Worker-{i+1}")

    # Wait for all tasks to complete
    q.join()
    
    # Wait for all threads to finish
    for t in threads:
        t.join()

    print(f"\n{'='*50}")
    print(f"Processing complete! Successfully processed {completed_count}/{total_count} videos.")
    print(f"{'='*50}")

if __name__ == "__main__":
    main()