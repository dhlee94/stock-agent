#!/usr/bin/env python3
"""
Memento AI Agent - 메인 진입점
"""
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from src.agent_client import MementoAgent
import asyncio

def main():
    task = "최신 AI 관련 뉴스를 찾아줘"
    if len(sys.argv) > 1:
        task = " ".join(sys.argv[1:])
    
    agent = MementoAgent()
    asyncio.run(agent.run(task))

if __name__ == "__main__":
    main()
