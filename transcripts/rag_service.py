from openai import OpenAI
from .semantic_search import semantic_search
from django.conf import settings
import os
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY", "not-needed"),
    base_url=os.getenv("OPENAI_BASE_URL", "http://127.0.0.1:1234/v1")
)

def answer_question(question: str, video_id: str = None, conversation_history: list = None, top_k: int = 3) -> dict:
    """RAG Pipeline: Retrieve → Augment → Generate → Cite"""

    # --- Step 1: RETRIEVAL - Find relevant transcript chunks ---
    retrieval_result = semantic_search(question, video_id=video_id, top_k=top_k)
    
    if 'error' in retrieval_result:
        if 'Failed to embed query' in retrieval_result['error']:
            return {"error": "LM Studio Embedding model connection failed (Check RAG UI state)."}
        return retrieval_result

    chunks = retrieval_result['results']
    if not chunks:
        return {"error": "No relevant content found in knowledge base."}

    # --- Step 2: AUGMENTATION - Format chunks into structured context ---
    context_text = "\n\n".join([
        f"Video: {chunk.get('title', 'Unknown')} (URL: https://youtube.com/watch?v={chunk.get('youtube_video_id', '')}&t={int(chunk.get('start_time_seconds', 0))}s)\nText: {chunk.get('text', '')}"
        for chunk in chunks
    ])

    # --- Step 3: GENERATION - LLM synthesizes answer using context ---
    system_prompt = """You are an AI tutor answering questions about YouTube video content.
IMPORTANT RULES:
1. Answer ONLY based on the provided video context.
2. If the question is not covered by the context, respond with: "This topic is not covered in the available videos."
3. Do NOT make up information.
4. Cite which video(s) provided your answer by including the video title and the full YouTube URL with timestamp (e.g., [Video Title] (URL: ...))."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Context from videos:\n{context_text}\n\nQuestion: {question}"}
    ]

    if conversation_history:
        messages = messages[:1] + conversation_history + messages[1:]

    try:
        response = client.chat.completions.create(
            model="openai/gpt-oss-20b", 
            messages=messages,
            temperature=0.7,
            max_tokens=512, 
        )

        answer = response.choices[0].message.content

        # --- Step 4: CITATION TRACKING - Extract and format sources ---
        citations = []
        similarity_scores = []
        
        for chunk in chunks:
            similarity = float(chunk.get('similarity_score', 0.0)) 
            similarity_scores.append(similarity)
            
            citations.append({
                "video_id": chunk.get('youtube_video_id', ''),
                "timestamp_seconds": chunk.get('start_time_seconds', 0), 
                "url": f"https://youtube.com/watch?v={chunk.get('youtube_video_id', '')}&t={int(chunk.get('start_time_seconds', 0))}s",
                "similarity": similarity 
            })

        confidence = sum(similarity_scores) / len(similarity_scores) if similarity_scores else 0.0

        return {
            "answer": answer,
            "sources": citations,
            "confidence": confidence,
            "model": "openai/gpt-oss-20b"
        }

    except Exception as e:
        print(f"LLM generation failed in rag_service.py: {str(e)}")
        return {"error": f"LLM generation failed: {str(e)}. Check LM Studio logs for /v1/chat/completions errors."}