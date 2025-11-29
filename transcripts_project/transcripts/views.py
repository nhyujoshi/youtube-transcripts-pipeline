from django.shortcuts import render
from django.http import HttpResponse
from .models import Videos, Transcripts
from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView
from collections import Counter
import re

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

# Create your views here.

class TotalCountsAPIView(APIView):
    def get(self, request):
        try:
            video_count = Videos.objects.count()
            transcript_count = Transcripts.objects.count()

            return Response({
                "total_videos": video_count,
                "total_transcripts": transcript_count
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class KeywordSearchAPIView(APIView):
    def get(self, request):
        keyword = request.query_params.get('q', '').strip()

        if not keyword:
            return Response({"error": "Cannot process empty keyword!"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            snippets = Transcripts.objects.filter(
                text__icontains=keyword
            ).order_by('start_time').values('video_id', 'start_time', 'text')

            results = [
                {
                    "video_id": snippet['video_id'],
                    "start_time":snippet['start_time'],
                    "text":snippet['text'].replace('\n',' '),
                }for snippet in snippets
            ]

            return Response({
                "keyword":keyword,
                "count":len(results),
                "results": results
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error":str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class CommonWordsAPIView(APIView):
    def get(self, request):
        try:
            max_num = int(request.query_params.get('n', 10)) 

            text_list = Transcripts.objects.values_list("text", flat=True)

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

            results = [{"word": word, "count": count} for word, count in most_common]

            return Response(results, status=status.HTTP_200_OK)
        
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

def index(request):
    return render(request, 'transcripts/index.html')