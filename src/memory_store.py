import json
import os
import numpy as np
from typing import List, Dict, Any
from dotenv import load_dotenv

# Load .env file from project root
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

# Provider selection: "gemini" (default, free) or "openai"
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "gemini").lower()
MOCK_MODE = False

# Check API keys
if LLM_PROVIDER == "gemini":
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not GEMINI_API_KEY:
        MOCK_MODE = True
    else:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
elif LLM_PROVIDER == "openai":
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
    if not OPENAI_API_KEY:
        MOCK_MODE = True
    else:
        from openai import OpenAI

class MemoryStore:
    def __init__(self, storage_file: str = "memory_store.json"):
        self.storage_file = storage_file
        self.trajectories: List[Dict[str, Any]] = []
        self._load_memory()
        
        if MOCK_MODE:
            print(f"[Memory] Running in MOCK mode (no API key for {LLM_PROVIDER}).")
            self.client = None
        elif LLM_PROVIDER == "openai":
            self.client = OpenAI()
            print("[Memory] Using OpenAI embeddings.")
        else:
            self.client = None
            print("[Memory] Using Gemini embeddings.")

    def _load_memory(self):
        if os.path.exists(self.storage_file):
            with open(self.storage_file, 'r', encoding='utf-8') as f:
                try:
                    self.trajectories = json.load(f)
                except json.JSONDecodeError:
                    self.trajectories = []
        else:
            self.trajectories = []

    def _save_memory(self):
        with open(self.storage_file, 'w', encoding='utf-8') as f:
            json.dump(self.trajectories, f, ensure_ascii=False, indent=2)

    def _get_embedding(self, text: str) -> List[float]:
        if MOCK_MODE:
            np.random.seed(hash(text) % (2**32))
            return np.random.rand(256).tolist()

        text = text.replace("\n", " ")

        if LLM_PROVIDER == "openai":
            return self.client.embeddings.create(
                input=[text],
                model="text-embedding-3-small"
            ).data[0].embedding
        else:
            try:
                import google.generativeai as _genai
                gemini_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
                if gemini_key:
                    _genai.configure(api_key=gemini_key)
                result = _genai.embed_content(
                    model="models/text-embedding-004",
                    content=text,
                    task_type="retrieval_document"
                )
                return result['embedding']
            except Exception:
                # Fallback: deterministic hash-based embedding
                np.random.seed(hash(text) % (2**32))
                return np.random.rand(768).tolist()

    REWRITE_SIMILARITY_THRESHOLD = 0.92  # 같은 task로 간주할 유사도
    REWRITE_MIN_IMPROVEMENT = 0.1       # 교체하려면 최소 이 이상 score가 높아야 함

    def save_trajectory(self, task: str, plan: str, result: str, feedback_score: float, lessons: List[str] = None):
        new_embedding = self._get_embedding(task)
        query = np.array(new_embedding)

        # Memory Rewriting: 매우 유사한 기존 trajectory가 있으면 교체 여부 판단
        for i, traj in enumerate(self.trajectories):
            existing_emb = np.array(traj.get("embedding", []))
            if existing_emb.size == 0:
                continue
            similarity = np.dot(query, existing_emb) / (
                np.linalg.norm(query) * np.linalg.norm(existing_emb) + 1e-9
            )
            if similarity >= self.REWRITE_SIMILARITY_THRESHOLD:
                existing_score = traj.get("score", 0)
                if feedback_score >= existing_score + self.REWRITE_MIN_IMPROVEMENT:
                    print(f"[Memory] Rewriting trajectory (similarity={similarity:.2f}, {existing_score:.2f} → {feedback_score:.2f})")
                    self.trajectories[i] = {
                        "task": task,
                        "plan": plan,
                        "result": result,
                        "score": feedback_score,
                        "lessons": lessons or [],
                        "embedding": new_embedding
                    }
                    self._save_memory()
                    return
                else:
                    print(f"[Memory] Kept existing trajectory (similarity={similarity:.2f}, existing={existing_score:.2f} >= new={feedback_score:.2f})")
                    return

        # 유사한 케이스 없으면 새로 추가
        print(f"[Memory] Saving new trajectory for task: {task[:50]}... (score={feedback_score:.2f})")
        self.trajectories.append({
            "task": task,
            "plan": plan,
            "result": result,
            "score": feedback_score,
            "lessons": lessons or [],
            "embedding": new_embedding
        })
        self._save_memory()

    def retrieve_similar(self, current_task: str, top_k: int = 3) -> List[Dict[str, Any]]:
        if not self.trajectories:
            return []

        query_embedding = np.array(self._get_embedding(current_task))

        scores = []
        for traj in self.trajectories:
            traj_embedding = np.array(traj.get("embedding", []))
            if traj_embedding.size == 0:
                continue

            similarity = np.dot(query_embedding, traj_embedding) / (
                np.linalg.norm(query_embedding) * np.linalg.norm(traj_embedding) + 1e-9
            )
            # 유사도와 품질 점수를 결합한 최종 랭킹 점수 (7:3 비율)
            combined_score = 0.7 * similarity + 0.3 * traj.get("score", 0)
            scores.append((combined_score, traj))

        scores.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in scores[:top_k]]


class SemanticMemory:
    """
    Stores generalized knowledge extracted from past episodes by the Reflector.
    Unlike EpisodicMemory (specific trajectories), each entry is a single
    abstract lesson that can transfer across different tasks.
    """
    def __init__(self, storage_file: str = "semantic_memory.json"):
        self.storage_file = storage_file
        self.knowledge: List[Dict[str, Any]] = []
        self._load()

    def _load(self):
        if os.path.exists(self.storage_file):
            with open(self.storage_file, 'r', encoding='utf-8') as f:
                try:
                    self.knowledge = json.load(f)
                except json.JSONDecodeError:
                    self.knowledge = []
        else:
            self.knowledge = []

    def _save(self):
        with open(self.storage_file, 'w', encoding='utf-8') as f:
            json.dump(self.knowledge, f, ensure_ascii=False, indent=2)

    def _get_embedding(self, text: str) -> List[float]:
        if MOCK_MODE:
            np.random.seed(hash(text) % (2**32))
            return np.random.rand(256).tolist()
        text = text.replace("\n", " ")
        if LLM_PROVIDER == "openai":
            client = OpenAI()
            return client.embeddings.create(
                input=[text],
                model="text-embedding-3-small"
            ).data[0].embedding
        else:
            try:
                import google.generativeai as _genai
                gemini_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
                if gemini_key:
                    _genai.configure(api_key=gemini_key)
                result = _genai.embed_content(
                    model="models/text-embedding-004",
                    content=text,
                    task_type="retrieval_document"
                )
                return result['embedding']
            except Exception:
                np.random.seed(hash(text) % (2**32))
                return np.random.rand(768).tolist()

    def save_knowledge(self, lesson: str, source_task: str):
        """Store a generalized lesson. Skips exact duplicates."""
        if any(entry.get("lesson") == lesson for entry in self.knowledge):
            return
        entry = {
            "lesson": lesson,
            "source_task": source_task,
            "embedding": self._get_embedding(lesson)
        }
        self.knowledge.append(entry)
        self._save()
        print(f"[SemanticMemory] Stored: {lesson[:80]}")

    def retrieve_relevant(self, current_task: str, top_k: int = 5) -> List[str]:
        """Retrieve lessons most relevant to the current task by embedding similarity."""
        if not self.knowledge:
            return []
        query_embedding = np.array(self._get_embedding(current_task))
        scores = []
        for entry in self.knowledge:
            emb = np.array(entry.get("embedding", []))
            if emb.size == 0:
                continue
            similarity = np.dot(query_embedding, emb) / (
                np.linalg.norm(query_embedding) * np.linalg.norm(emb) + 1e-9
            )
            scores.append((similarity, entry["lesson"]))
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

