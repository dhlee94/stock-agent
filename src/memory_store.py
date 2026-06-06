import json
import os
import numpy as np
from typing import List, Dict, Any, Optional
from config import EMBEDDING_PROVIDER, EMBEDDING_MODEL, GEMINI_API_KEY, OPENAI_API_KEY
from database import get_connection

class MemoryStore:
    # 🚀 Class-level cache to prevent redundant model loading
    _local_tokenizer = None
    _local_model = None

    def __init__(self):
        print("[Memory] Initialized with SQLite database.")
        if EMBEDDING_PROVIDER == "openai":
            from openai import OpenAI
            self.client = OpenAI(api_key=OPENAI_API_KEY)
        else:
            self.client = None

    def _get_embedding(self, text: str) -> List[float]:
        text = text.replace("\n", " ")

        # 1. Try OpenAI
        if EMBEDDING_PROVIDER == "openai":
            try:
                return self.client.embeddings.create(
                    input=[text],
                    model=EMBEDDING_MODEL
                ).data[0].embedding
            except Exception as e:
                print(f"⚠️ OpenAI Embedding failed: {e}")
        
        # 2. Try Gemini
        if EMBEDDING_PROVIDER == "gemini" or GEMINI_API_KEY:
            try:
                from google import genai as _genai
                _client = _genai.Client(api_key=GEMINI_API_KEY)
                model_name = EMBEDDING_MODEL if EMBEDDING_PROVIDER == "gemini" else "models/gemini-embedding-001"
                result = _client.models.embed_content(
                    model=model_name,
                    contents=text,
                    config=_genai.types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT"),
                )
                return result.embeddings[0].values
            except Exception as e:
                pass  # Silent fallback to local

        # 3. 🚀 Local Embedding Fallback (Singleton Pattern)
        try:
            from transformers import AutoTokenizer, AutoModel
            import torch
            
            model_name = "sentence-transformers/all-distilroberta-v1"
            
            # Load only once per process
            if MemoryStore._local_tokenizer is None:
                print(f"📡 Loading local embedding model ({model_name})...")
                MemoryStore._local_tokenizer = AutoTokenizer.from_pretrained(model_name)
                MemoryStore._local_model = AutoModel.from_pretrained(model_name)
                print("   ✅ Local model loaded successfully.")
            
            inputs = MemoryStore._local_tokenizer(text, return_tensors='pt', padding=True, truncation=True, max_length=512)
            with torch.no_grad():
                outputs = MemoryStore._local_model(**inputs)
            
            embeddings = outputs.last_hidden_state.mean(dim=1)
            return embeddings[0].tolist()
            
        except Exception as e:
            # Random vectors make similarity search meaningless — log loudly.
            print(f"❌ [MemoryStore] All embedding methods failed: {e}. "
                  "Memory retrieval will return random results until an embedding provider is configured.")
            np.random.seed(hash(text) % (2**32))
            return np.random.rand(768).tolist()

    REWRITE_SIMILARITY_THRESHOLD = 0.92
    REWRITE_MIN_IMPROVEMENT = 0.1

    def save_trajectory(self, task: str, plan: str, result: str, feedback_score: float, lessons: List[str] = None):
        """Save task trajectory to episodic memory."""
        new_embedding = self._get_embedding(task)
        query = np.array(new_embedding)

        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, score, embedding_json FROM episodic_memory")
            rows = cursor.fetchall()
            
            for row in rows:
                existing_emb = np.array(json.loads(row['embedding_json']))
                if existing_emb.shape != query.shape:
                    continue
                similarity = np.dot(query, existing_emb) / (
                    np.linalg.norm(query) * np.linalg.norm(existing_emb) + 1e-9
                )
                
                if similarity >= self.REWRITE_SIMILARITY_THRESHOLD:
                    if feedback_score >= row['score'] + self.REWRITE_MIN_IMPROVEMENT:
                        cursor.execute('''
                            UPDATE episodic_memory SET 
                                task = ?, plan_json = ?, result = ?, score = ?, lessons_json = ?, embedding_json = ?, created_at = CURRENT_TIMESTAMP
                            WHERE id = ?
                        ''', (task, plan, result, feedback_score, json.dumps(lessons or []), json.dumps(new_embedding), row['id']))
                        return
                    return

            cursor.execute('''
                INSERT INTO episodic_memory (task, plan_json, result, score, lessons_json, embedding_json)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (task, plan, result, feedback_score, json.dumps(lessons or []), json.dumps(new_embedding)))

    def retrieve_similar(self, current_task: str, top_k: int = 3) -> List[Dict[str, Any]]:
        query_embedding = np.array(self._get_embedding(current_task))
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT task, plan_json, result, score, lessons_json, embedding_json FROM episodic_memory")
            rows = cursor.fetchall()
            if not rows: return []
            results = []
            for row in rows:
                traj_emb = np.array(json.loads(row['embedding_json']))
                if traj_emb.shape != query_embedding.shape: continue
                similarity = np.dot(query_embedding, traj_emb) / (np.linalg.norm(query_embedding) * np.linalg.norm(traj_emb) + 1e-9)
                results.append({"task": row['task'], "plan": row['plan_json'], "result": row['result'], "score": row['score'], 
                                "lessons": json.loads(row['lessons_json']), "combined_score": 0.7 * similarity + 0.3 * row['score']})
            results.sort(key=lambda x: x['combined_score'], reverse=True)
            return results[:top_k]

class SemanticMemory:
    def __init__(self):
        self.ms = MemoryStore() # Reuse MemoryStore instance

    def save_knowledge(self, lesson: str, source_task: str):
        with get_connection() as conn:
            cursor = conn.cursor()
            try:
                emb = self.ms._get_embedding(lesson)
                cursor.execute('''
                    INSERT OR IGNORE INTO semantic_memory (lesson, source_task, embedding_json)
                    VALUES (?, ?, ?)
                ''', (lesson, source_task, json.dumps(emb)))
            except Exception as e:
                print(f"⚠️ SemanticMemory save error: {e}")

    def retrieve_relevant(self, current_task: str, top_k: int = 5) -> List[str]:
        query_emb = np.array(self.ms._get_embedding(current_task))
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT lesson, embedding_json FROM semantic_memory")
            rows = cursor.fetchall()
            if not rows: return []
            scores = []
            for row in rows:
                emb = np.array(json.loads(row['embedding_json']))
                if emb.shape != query_emb.shape: continue
                similarity = np.dot(query_emb, emb) / (np.linalg.norm(query_emb) * np.linalg.norm(emb) + 1e-9)
                scores.append((similarity, row['lesson']))
            scores.sort(key=lambda x: x[0], reverse=True)
            return [lesson for _, lesson in scores[:top_k]]

class ProceduralMemory:
    def __init__(self, storage_file: str = "procedural_memory.json"):
        pass
    def save_tool_execution(self, tool_name: str, args: Dict, success: bool, output_summary: str):
        from database import log_tool_execution
        log_tool_execution(tool_name, args, output_summary[:500], success)
    def get_tool_tips(self, tool_name: str, top_k: int = 3) -> List[Dict]:
        from database import get_tool_history
        return [h for h in get_tool_history(tool_name, limit=top_k*2) if h.get('success')][:top_k]
