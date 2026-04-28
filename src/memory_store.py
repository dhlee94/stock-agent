import json
import os
import numpy as np
from typing import List, Dict, Any
from config import EMBEDDING_PROVIDER, EMBEDDING_MODEL, GEMINI_API_KEY, OPENAI_API_KEY
from database import get_connection

class MemoryStore:
    def __init__(self):
        # Database is initialized in database.py
        print("[Memory] Initialized with SQLite database.")

        if EMBEDDING_PROVIDER == "openai":
            from openai import OpenAI
            self.client = OpenAI(api_key=OPENAI_API_KEY)
            print("[Memory] Using OpenAI embeddings.")
        else:
            self.client = None
            print(f"[Memory] Using Gemini embeddings (EMBEDDING_PROVIDER={EMBEDDING_PROVIDER}).")

    def _get_embedding(self, text: str) -> List[float]:
        text = text.replace("\n", " ")

        if EMBEDDING_PROVIDER == "openai":
            try:
                return self.client.embeddings.create(
                    input=[text],
                    model=EMBEDDING_MODEL
                ).data[0].embedding
            except Exception as e:
                print(f"⚠️ OpenAI Embedding failed: {e}. Falling back to local...")
        
        # Try Gemini
        if EMBEDDING_PROVIDER == "gemini" or GEMINI_API_KEY:
            try:
                import google.generativeai as _genai
                _genai.configure(api_key=GEMINI_API_KEY)
                gemini_embed_model = EMBEDDING_MODEL if EMBEDDING_PROVIDER == "gemini" else "models/text-embedding-004"
                result = _genai.embed_content(
                    model=gemini_embed_model,
                    content=text,
                    task_type="retrieval_document"
                )
                return result['embedding']
            except Exception as e:
                print(f"⚠️ Gemini Embedding failed (Quota?): {e}. Falling back to local...")

        # 🚀 Local Embedding Fallback (Free & Unlimited)
        try:
            from transformers import AutoTokenizer, AutoModel
            import torch
            
            # Use a small, efficient model (approx 90MB)
            model_name = "sentence-transformers/all-MiniLM-L6-v2"
            
            # Lazy load model to save memory
            if not hasattr(self, '_local_tokenizer'):
                print(f"📡 Downloading local embedding model ({model_name})...")
                self._local_tokenizer = AutoTokenizer.from_pretrained(model_name)
                self._local_model = AutoModel.from_pretrained(model_name)
            
            inputs = self._local_tokenizer(text, return_tensors='pt', padding=True, truncation=True, max_length=512)
            with torch.no_grad():
                outputs = self._local_model(**inputs)
            
            # Mean Pooling
            embeddings = outputs.last_hidden_state.mean(dim=1)
            return embeddings[0].tolist()
            
        except Exception as e:
            print(f"⚠️ Local Embedding failed: {e}. Using deterministic fallback.")
            # Final Fallback: deterministic hash-based (not recommended for search)
            import numpy as np
            np.random.seed(hash(text) % (2**32))
            return np.random.rand(384).tolist() # MiniLM dim is 384

    REWRITE_SIMILARITY_THRESHOLD = 0.92
    REWRITE_MIN_IMPROVEMENT = 0.1

    def save_trajectory(self, task: str, plan: str, result: str, feedback_score: float, lessons: List[str] = None):
        """Save task trajectory to episodic memory with similarity-based rewriting."""
        new_embedding = self._get_embedding(task)
        query = np.array(new_embedding)

        with get_connection() as conn:
            cursor = conn.cursor()
            # Check for very similar existing trajectories
            cursor.execute("SELECT id, score, embedding_json FROM episodic_memory")
            rows = cursor.fetchall()
            
            for row in rows:
                existing_emb = np.array(json.loads(row['embedding_json']))
                similarity = np.dot(query, existing_emb) / (
                    np.linalg.norm(query) * np.linalg.norm(existing_emb) + 1e-9
                )
                
                if similarity >= self.REWRITE_SIMILARITY_THRESHOLD:
                    if feedback_score >= row['score'] + self.REWRITE_MIN_IMPROVEMENT:
                        print(f"[Memory] Rewriting trajectory {row['id']} (similarity={similarity:.2f})")
                        cursor.execute('''
                            UPDATE episodic_memory SET 
                                task = ?, plan_json = ?, result = ?, score = ?, lessons_json = ?, embedding_json = ?, created_at = CURRENT_TIMESTAMP
                            WHERE id = ?
                        ''', (task, plan, result, feedback_score, json.dumps(lessons or []), json.dumps(new_embedding), row['id']))
                        return
                    else:
                        print(f"[Memory] Kept existing trajectory {row['id']} (similarity={similarity:.2f})")
                        return

            # If no similar case, insert new
            print(f"[Memory] Saving new trajectory (score={feedback_score:.2f})")
            cursor.execute('''
                INSERT INTO episodic_memory (task, plan_json, result, score, lessons_json, embedding_json)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (task, plan, result, feedback_score, json.dumps(lessons or []), json.dumps(new_embedding)))

    def retrieve_similar(self, current_task: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """Retrieve similar trajectories from episodic memory."""
        query_embedding = np.array(self._get_embedding(current_task))
        
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT task, plan_json, result, score, lessons_json, embedding_json FROM episodic_memory")
            rows = cursor.fetchall()
            
            if not rows:
                return []

            results = []
            for row in rows:
                traj_embedding = np.array(json.loads(row['embedding_json']))
                similarity = np.dot(query_embedding, traj_embedding) / (
                    np.linalg.norm(query_embedding) * np.linalg.norm(traj_embedding) + 1e-9
                )
                combined_score = 0.7 * similarity + 0.3 * row['score']
                
                results.append({
                    "task": row['task'],
                    "plan": row['plan_json'],
                    "result": row['result'],
                    "score": row['score'],
                    "lessons": json.loads(row['lessons_json']),
                    "combined_score": combined_score
                })

            results.sort(key=lambda x: x['combined_score'], reverse=True)
            return results[:top_k]


class SemanticMemory:
    """Stores generalized knowledge in SQLite."""
    def __init__(self):
        print("[SemanticMemory] Initialized with SQLite database.")
        if EMBEDDING_PROVIDER == "openai":
            from openai import OpenAI
            self.client = OpenAI(api_key=OPENAI_API_KEY)
        else:
            self.client = None

    def _get_embedding(self, text: str) -> List[float]:
        # Simple reuse of MemoryStore embedding logic (could be centralized)
        ms = MemoryStore()
        return ms._get_embedding(text)

    def save_knowledge(self, lesson: str, source_task: str):
        """Store a generalized lesson in semantic memory."""
        with get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    INSERT OR IGNORE INTO semantic_memory (lesson, source_task, embedding_json)
                    VALUES (?, ?, ?)
                ''', (lesson, source_task, json.dumps(self._get_embedding(lesson))))
                if cursor.rowcount > 0:
                    print(f"[SemanticMemory] Stored: {lesson[:80]}")
            except Exception as e:
                print(f"⚠️ SemanticMemory save error: {e}")

    def retrieve_relevant(self, current_task: str, top_k: int = 5) -> List[str]:
        """Retrieve relevant lessons using vector similarity."""
        query_embedding = np.array(self._get_embedding(current_task))
        
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT lesson, embedding_json FROM semantic_memory")
            rows = cursor.fetchall()
            
            if not rows:
                return []

            scores = []
            for row in rows:
                emb = np.array(json.loads(row['embedding_json']))
                similarity = np.dot(query_embedding, emb) / (
                    np.linalg.norm(query_embedding) * np.linalg.norm(emb) + 1e-9
                )
                scores.append((similarity, row['lesson']))
            
            scores.sort(key=lambda x: x[0], reverse=True)
            return [lesson for _, lesson in scores[:top_k]]


class ProceduralMemory:
    """
    Procedural Memory for Executor: stores tool execution history in SQLite.
    Allows Executor to learn from past tool usage patterns.
    """
    def __init__(self, storage_file: str = "procedural_memory.json"):
        # Storage file is no longer used, kept for compatibility
        self.storage_file = storage_file
        print("[ProceduralMemory] Initialized with SQLite database.")

    def _load_memory(self):
        """Deprecated: Logic moved to database.py"""
        pass

    def _save_memory(self):
        """Deprecated: Logic moved to database.py"""
        pass

    def save_tool_execution(self, tool_name: str, args: Dict, success: bool, output_summary: str):
        """Save a tool execution record to database."""
        from database import log_tool_execution
        
        log_tool_execution(
            tool_name=tool_name,
            args=args,
            result_summary=output_summary[:500], # Truncate for storage
            success=success
        )

    def get_tool_tips(self, tool_name: str, top_k: int = 3) -> List[Dict]:
        """Retrieve past successful executions for a specific tool from database."""
        from database import get_tool_history
        
        history = get_tool_history(tool_name, limit=top_k*2)
        # Filter for successful ones and return top_k
        successful = [h for h in history if h.get('success')]
        return successful[:top_k]


if __name__ == "__main__":
    mem = MemoryStore()
    print("MemoryStore initialized.")

