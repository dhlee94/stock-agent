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
            result = genai.embed_content(
                model="models/text-embedding-004",
                content=text,
                task_type="retrieval_document"
            )
            return result['embedding']

    def save_trajectory(self, task: str, plan: str, result: str, feedback_score: float):
        print(f"[Memory] Saving trajectory for task: {task[:50]}...")
        trajectory = {
            "task": task,
            "plan": plan,
            "result": result,
            "score": feedback_score,
            "embedding": self._get_embedding(task)
        }
        self.trajectories.append(trajectory)
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
            
            score = np.dot(query_embedding, traj_embedding) / (
                np.linalg.norm(query_embedding) * np.linalg.norm(traj_embedding) + 1e-9
            )
            scores.append((score, traj))
        
        scores.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in scores[:top_k]]

if __name__ == "__main__":
    mem = MemoryStore()
    print("MemoryStore initialized.")
