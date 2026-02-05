#!/usr/bin/env python3
"""
Memento AI Agent - Main Entry Point
"""
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from src.agent_client import MementoAgent
import asyncio

def main():
    task = "Find the latest news about AI"
    if len(sys.argv) > 1:
        task = " ".join(sys.argv[1:])
    
    agent = MementoAgent()
    asyncio.run(agent.run(task))

if __name__ == "__main__":
    main()
