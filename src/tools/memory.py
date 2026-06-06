"""
Memory Tool - Trajectory saving for Memento architecture
"""
import json
import sys
import os

# Add parent directories to path
TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(TOOLS_DIR)
sys.path.insert(0, SRC_DIR)

from memory_store import MemoryStore

# Shared memory store instance
_memory_store = None


def get_memory_store():
    global _memory_store
    if _memory_store is None:
        _memory_store = MemoryStore()
    return _memory_store


def save_feedback(task: str, plan: str, result: str, feedback_score: float) -> str:
    """
    Save the task execution result to memory for future reference.
    Args:
        task: The original task description.
        plan: The plan that was executed.
        result: The final output or summary of the execution.
        feedback_score: A score from 0.0 to 1.0 indicating success.
    """
    feedback_score = max(0.0, min(1.0, float(feedback_score)))
    print(f"🧠 [Memory] Saving trajectory for task: {task[:50]}...")
    try:
        memory_store = get_memory_store()
        memory_store.save_trajectory(task, plan, result, feedback_score)
        return json.dumps({"status": "success", "message": "Trajectory saved to memory."})
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})
