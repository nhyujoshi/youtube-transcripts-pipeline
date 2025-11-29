import os
import sys
from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.proxies import WebshareProxyConfig
from youtube_transcript_api._errors import TranscriptsDisabled
import psycopg2
from psycopg2 import sql
from dotenv import load_dotenv
import random
import time

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "youtube_transcripts")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD")

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
        print(f"Transcript is disabled for video {video_id}.")
        return None
    except Exception as e:
        print(f"Error fetching transcript for {video_id}: {e}")
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
    except psycopg2.OperationalError as e:
        print(f"Error connecting to database: {e}")
        print("Please ensure your PostgreSQL server is running and your .env variables are correct.")
        sys.exit(1)
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

def main():
    video_ids = get_video_ids("PLlrATfBNZ98cpX2LuxLnLyLEmfD2FPpRA")
    print(f"Found {len(video_ids)} videos. Starting transcript fetch...")

    for i, vid_id in enumerate(video_ids):
        print(f"\n[{i+1}/{len(video_ids)}] Processing video ID: {vid_id}")
        
        transcript_data = get_video_transcripts(vid_id)
        
        if transcript_data:
            transcript_list = transcript_data.get(vid_id, [])
            if transcript_list:
                print(f"Successfully fetched {len(transcript_list)} snippets.")
                
                try:
                    store_transcript(vid_id, transcript_list)
                    print(f"Successfully stored transcript for {vid_id}.")
                except Exception as db_e:
                    print(f"Database error storing {vid_id}: {db_e}")
            else:
                print(f"Transcript data was empty for {vid_id}.")
        
        delay = random.uniform(5, 15)
        print(f"Pausing for {delay:.2f} seconds to avoid rate limiting...")
        time.sleep(delay)

if __name__ == "__main__":
    main()