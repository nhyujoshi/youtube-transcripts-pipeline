# YouTube RAG Chatbot (Retrieval Augmented Generation)

## How to setup Local LLM to run

1. Install LM Studio
2. Install openai/gpt-oss-20b for chat completion and nomic-ai/nomic-embed-text-v1.5-GGUF for embedding
3. Load both models
4. Run the server

## Architecture

```
Question
    ↓
Convert to Embedding (OpenAI)
    ↓
Semantic Search in PostgreSQL + pgvector
    ↓
Retrieve Top-K Relevant Transcript Chunks
    ↓
Format as Context (Prompt Engineering)
    ↓
Send to LLM (GPT-4): [Context + Question]
    ↓
LLM Generates Grounded Answer
    ↓
Track Citations: Which videos were used
    ↓
Display Answer + Sources (Web UI)
```

## Key Components

- **Understanding the Retrieval Layer:**

Your system uses **PostgreSQL + pgvector** as the vector database. This stores embeddings (semantic vectors) of all transcript chunks.

**How Vector Search Works:**

1. User question → Convert to embedding using same model as training
2. Database query → Find chunks with nearest embeddings using cosine distance
3. Distance metric → `<->` operator finds closest vectors (lower = more similar)
4. Top-K retrieval → Return top 3-5 most relevant chunks

```sql
-- The core RAG retrieval query
SELECT text, video_id, start_time,
       1 - (embedding <-> query_embedding::vector) as similarity
FROM text_chunks
ORDER BY embedding <-> query_embedding::vector  -- Cosine distance
LIMIT 5;  -- Top 5 most similar chunks
```

**Vector Similarity Methods:**

Your pgvector setup uses **cosine similarity** (angle between vectors):

| Method                    | Formula                        | Use Case                                 |
| ------------------------- | ------------------------------ | ---------------------------------------- |
| **Cosine Distance** `<->` | 1 - (dot product / magnitudes) | Best for semantic meaning (what you use) |
| **Euclidean Distance**    | √(sum of squared differences)  | Geometric distance                       |
| **Inner Product**         | sum(v1 \* v2)                  | Raw similarity score                     |

For text embeddings, **cosine similarity is ideal** because it measures semantic meaning independent of length.

## Usage

**Web UI - Chat with Your Videos:**

```bash
python manage.py runserver
# Visit: http://localhost:8000/
# Type: "What is neural network?"
```

## RAG vs Pure Search

| Aspect        | Semantic Search      | RAG System                          |
| ------------- | -------------------- | ----------------------------------- |
| **Input**     | "backpropagation"    | "Explain how backpropagation works" |
| **Process**   | Similarity matching  | Retrieve + Generate                 |
| **Output**    | List of chunks       | Conversational answer               |
| **Citations** | Implicit             | Explicit with timestamps            |
| **Cost**      | Embedding API only   | Embedding + LLM API                 |
| **Use Case**  | Find relevant videos | Answer questions naturally          |

**RAG Approaches (From Academic Research):**

Two main approaches to implement RAG:

1. **RAG-Sequence**: Generate one answer for all retrieved documents

   - Retrieve top-K chunks once
   - Generate answer using all context at once
   - Simpler implementation, faster response
   - **Your approach** - retrieves 3-5 chunks, generates one cohesive answer

2. **RAG-Token**: Retrieve and generate iteratively
   - Generate answer token-by-token
   - For each token, retrieve most relevant context
   - More complex but potentially more accurate
   - Used by cutting-edge systems

Your implementation uses **RAG-Sequence** (simpler, proven effective for educational Q&A).

## Performance Considerations

- **Batch embeddings** for efficiency (20x cost savings)
- **Cache popular questions** to reduce LLM calls
- **Stream responses** for better UX
- **Set max context length** to stay within LLM token limits