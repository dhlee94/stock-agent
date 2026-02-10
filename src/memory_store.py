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
            print(f"[Memory] API 키가 없어 MOCK 모드로 실행합니다 (프로바이더: {LLM_PROVIDER}).")
            self.client = None
        elif LLM_PROVIDER == "openai":
            self.client = OpenAI()
            print("[Memory] OpenAI 임베딩 모델을 사용합니다.")
        else:
            self.client = None
            print("[Memory] Gemini 임베딩 모델을 사용합니다.")

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
        print(f"[Memory] 작업을 메모리에 저장합니다 (task 미리보기: {task[:50]}...)")
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


class ProceduralMemory:
    """
    Executor를 위한 Procedural Memory.
    도구 실행 이력을 SQLite에 저장하여, 과거 도구 사용 패턴을 참조할 수 있게 합니다.
    """
    def __init__(self, storage_file: str = "procedural_memory.json"):
        # Storage file is no longer used, kept for compatibility
        self.storage_file = storage_file
        print("[ProceduralMemory] SQLite 데이터베이스 기반으로 초기화되었습니다.")

    def _load_memory(self):
        """더 이상 사용되지 않습니다. 관련 로직은 database.py로 이전되었습니다."""
        pass

    def _save_memory(self):
        """더 이상 사용되지 않습니다. 관련 로직은 database.py로 이전되었습니다."""
        pass

    def save_tool_execution(self, tool_name: str, args: Dict, success: bool, output_summary: str):
        """도구 실행 결과를 DB에 한 줄 요약과 함께 저장합니다."""
        from database import log_tool_execution
        
        log_tool_execution(
            tool_name=tool_name,
            args=args,
            result_summary=output_summary[:500],  # 저장 공간을 위해 500자까지만 저장
            success=success,
        )

    def get_tool_tips(self, tool_name: str, top_k: int = 3) -> List[Dict]:
        """특정 도구에 대해 성공적으로 실행되었던 과거 이력을 조회합니다."""
        from database import get_tool_history
        
        history = get_tool_history(tool_name, limit=top_k * 2)
        # 성공한 실행만 필터링하여 상위 top_k개만 반환
        successful = [h for h in history if h.get('success')]
        return successful[:top_k]


if __name__ == "__main__":
    mem = MemoryStore()
    print("MemoryStore가 정상적으로 초기화되었습니다.")

