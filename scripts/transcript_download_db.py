import os
from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.proxies import WebshareProxyConfig
from youtube_transcript_api._errors import TranscriptsDisabled
import psycopg2
from psycopg2 import sql
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "youtube_transcripts")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD")

def get_db_connection():
    """Get database connection."""
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
    )

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
    ytt_api = YouTubeTranscriptApi(
        proxy_config=WebshareProxyConfig(
        proxy_username=os.getenv("WEBSHARE_PROXY_USER"),
        proxy_password=os.getenv("WEBSHARE_PROXY_PASS"),
    )
    )
    fetched_transcript = {}
    fetched_transcript[video_id] = ytt_api.fetch(video_id).to_raw_data()
    
    return fetched_transcript

video_ids = get_video_ids("PL-osiE80TeTsqhIuOqKhwlXsIBIdSeYtc")
print(get_video_transcripts(video_ids[0]))