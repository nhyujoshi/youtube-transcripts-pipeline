from django.shortcuts import render
from django.http import HttpResponse
from django.db import transaction
from django.shortcuts import get_object_or_404
from .models import Videos, Transcripts, Conversation, Message
from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView
from collections import Counter
import re

from .semantic_search import semantic_search
from .rag_service import answer_question

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
        
class SemanticSearchAPIView(APIView):
    """Semantic search API endpoint."""

    def post(self, request):
        """
        POST body:
        {
            "query": "What is machine learning?",
            "video_id": "dQw4w9WgXcQ",  # optional
            "top_k": 5
        }
        """
        query = request.data.get('query', '').strip()
        video_id = request.data.get('video_id')
        top_k = request.data.get('top_k', 5)

        if not query:
            return Response(
                {'error': 'query parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        result = semantic_search(query, video_id, top_k)

        if 'error' in result:
            return Response(result, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(result, status=status.HTTP_200_OK)

HISTORY_LIMIT = 10 

class ChatAPIView(APIView):
    """RAG Chat endpoint - answers questions with cited sources and persistent history."""

    @transaction.atomic
    def post(self, request):
        """
        POST chat/

        Request body:
        {
            "question": "What is backpropagation?",
            "conversation_id": "user_123",  # Mandatory unique ID for history tracking
            "video_id": "abc123",           # Optional: to search specific video only
            "top_k": 3                      # Optional: number of chunks to retrieve
        }
        """

        # Validate input
        question = request.data.get('question', '').strip()
        conversation_id = request.data.get('conversation_id')
        video_id = request.data.get('video_id')
        top_k = request.data.get('top_k', 3)

        if not question:
            return Response(
                {'error': 'question parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not conversation_id:
             return Response(
                {'error': 'conversation_id parameter is required for history tracking'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if len(question) > 500:
            return Response(
                {'error': 'question must be under 500 characters'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 1. Initialize or Retrieve Conversation
        conversation, created = Conversation.objects.get_or_create(
            session_id=conversation_id
        )

        # 2. Retrieve Conversation History
        history_qs = conversation.messages.filter(
            role__in=['user', 'assistant']
        ).order_by('-timestamp')[:HISTORY_LIMIT]
        
        # Format the history for the LLM API
        conversation_history = [
            {"role": msg.role, "content": msg.content}
            for msg in reversed(history_qs) # Reverse order to be chronological
        ]

        # 3. Add current user message to history before sending to service
        conversation_history.append({"role": "user", "content": question})

        # 4. Generate answer using RAG pipeline
        result = answer_question(question, video_id, conversation_history, top_k)
        
        # Remove the last user message from the list sent to the service, 
        # so we only save the database messages plus the assistant's response.
        conversation_history.pop() 


        if 'error' in result:
            # Save the failed user message before returning an error
            Message.objects.create(
                conversation=conversation,
                role='user',
                content=question
            )
            return Response(result, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # 5. Save the User and Assistant Messages to the database
        
        # Save User Message
        Message.objects.create(
            conversation=conversation,
            role='user',
            content=question
        )
        
        # Save Assistant Response
        Message.objects.create(
            conversation=conversation,
            role='assistant',
            content=result['answer']
        )

        return Response(result, status=status.HTTP_200_OK)
    
def index(request):
    return render(request, 'transcripts/index.html')