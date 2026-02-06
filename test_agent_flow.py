#!/usr/bin/env python3
"""
Verbose Debug Script for Memento Agent
=======================================
Shows internal thoughts at every step for debugging without wasting Groq tokens.

Usage:
    python test_agent_flow.py
    python test_agent_flow.py "NVIDIA 분석해줘"
"""
import os
import sys
import json
import time
import asyncio
from datetime import datetime

# Add src directory to path
SRC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
sys.path.insert(0, SRC_DIR)

# ANSI Colors for terminal output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    END = '\033[0m'

def log(tag: str, emoji: str, message: str, color: str = Colors.END):
    """Formatted log output."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"{Colors.BOLD}[{timestamp}]{Colors.END} {color}[{tag}]{Colors.END} {emoji} {message}")

def log_json(data: dict, indent: int = 2):
    """Pretty print JSON data."""
    print(json.dumps(data, ensure_ascii=False, indent=indent))

def main():
    print(f"\n{Colors.BOLD}{'='*60}{Colors.END}")
    print(f"{Colors.BOLD}🧪 Memento Agent - Verbose Debug Mode{Colors.END}")
    print(f"{Colors.BOLD}{'='*60}{Colors.END}\n")
    
    # Get test query
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
    else:
        query = "삼성전자 향후 주가 예측해줘"
    
    log("INPUT", "📝", f"Query: {Colors.BOLD}{query}{Colors.END}", Colors.CYAN)
    print()
    
    # =========================================================
    # STEP 1: Check Driver Memory
    # =========================================================
    log("MEMORY", "🧠", "Checking DriverMemory...", Colors.BLUE)
    
    from driver_memory import DriverMemory
    dm = DriverMemory()
    
    # Extract ticker from query (simple heuristic)
    ticker = None
    ticker_map = {
        "삼성전자": "005930.KS",
        "samsung": "005930.KS",
        "nvidia": "NVDA",
        "엔비디아": "NVDA",
        "애플": "AAPL",
        "apple": "AAPL",
        "테슬라": "TSLA",
        "tesla": "TSLA",
    }
    
    for name, tk in ticker_map.items():
        if name.lower() in query.lower():
            ticker = tk
            break
    
    if not ticker:
        ticker = "005930.KS"  # Default to Samsung
        log("MEMORY", "⚠️", f"Could not detect ticker, defaulting to {ticker}", Colors.YELLOW)
    
    # Check cache
    cached_drivers = dm.get_drivers(ticker)
    if cached_drivers:
        log("MEMORY", "✅", f"Found cached drivers for {ticker}:", Colors.GREEN)
        print(f"         Keywords: {Colors.BOLD}{cached_drivers.get('drivers', [])}{Colors.END}")
        print(f"         Last Updated: {cached_drivers.get('last_updated', 'N/A')}")
    else:
        log("MEMORY", "❌", f"No cached drivers for {ticker}", Colors.YELLOW)
        log("MEMORY", "🔄", "Triggering analyze_historical_drivers()...", Colors.YELLOW)
        
        # Rate limit protection
        time.sleep(0.5)
        
        try:
            result = dm.analyze_historical_drivers(ticker)
            if "error" not in result:
                log("MEMORY", "✅", f"Analysis complete!", Colors.GREEN)
                print(f"         New Keywords: {Colors.BOLD}{result.get('drivers', [])}{Colors.END}")
                print(f"         Volatility Dates: {result.get('volatility_dates', [])}")
            else:
                log("MEMORY", "⚠️", f"Analysis failed: {result.get('error')}", Colors.RED)
        except Exception as e:
            log("MEMORY", "❌", f"Error: {e}", Colors.RED)
    
    print()
    
    # =========================================================
    # STEP 2: Simulate Planner
    # =========================================================
    log("PLANNER", "🤔", "Generating execution plan...", Colors.CYAN)
    
    # Mock plan based on driver keywords
    drivers = cached_drivers.get('drivers', []) if cached_drivers else ["실적발표", "기술개발"]
    company_name = cached_drivers.get('name', '삼성전자') if cached_drivers else '삼성전자'
    
    mock_plan = [
        {"step": 1, "tool": "analyze_drivers", "args": {"ticker": ticker}, "reason": "Get historical drivers"},
        {"step": 2, "tool": "stock_price", "args": {"ticker": ticker}, "reason": "Get current price"},
        {"step": 3, "tool": "stock_news", "args": {"query": f"{company_name} {drivers[0]}"}, "reason": f"Search for {drivers[0]} news"},
        {"step": 4, "tool": "stock_technical", "args": {"ticker": ticker}, "reason": "Technical analysis"},
        {"step": 5, "tool": "stock_ai_predict", "args": {"ticker": ticker}, "reason": "AI prediction"},
    ]
    
    log("PLANNER", "✅", f"Plan created with {len(mock_plan)} steps:", Colors.GREEN)
    for step in mock_plan:
        print(f"         {step['step']}. {Colors.BOLD}{step['tool']}{Colors.END} - {step['reason']}")
    
    print()
    
    # =========================================================
    # STEP 3: Execute Tools (Dry Run)
    # =========================================================
    log("EXECUTOR", "🛠️", "Executing tools (dry run)...", Colors.YELLOW)
    
    from tools.stock import get_stock_price, technical_analysis, get_market_news
    
    for step in mock_plan:
        tool_name = step["tool"]
        args = step["args"]
        
        log("EXECUTOR", "⚡", f"Step {step['step']}: {tool_name}", Colors.YELLOW)
        print(f"         Args: {args}")
        
        # Rate limit protection
        time.sleep(0.3)
        
        try:
            if tool_name == "stock_price":
                result = get_stock_price(args.get("ticker"), args.get("market", "KR"))
                # Parse and show key info
                result_data = json.loads(result)
                log("EXECUTOR", "📊", f"Price: {result_data.get('price', 'N/A')} ({result_data.get('change_percent', 'N/A')}%)", Colors.GREEN)
                
            elif tool_name == "stock_technical":
                result = technical_analysis(args.get("ticker"))
                result_data = json.loads(result)
                log("EXECUTOR", "📈", f"Signal: {result_data.get('overall_signal', 'N/A')}", Colors.GREEN)
                
            elif tool_name == "stock_news":
                result = get_market_news(query=args.get("query"), limit=3)
                result_data = json.loads(result)
                news_count = len(result_data.get("articles", []))
                log("EXECUTOR", "📰", f"Found {news_count} articles", Colors.GREEN)
                
            elif tool_name == "analyze_drivers":
                log("EXECUTOR", "🧠", "Using cached drivers", Colors.GREEN)
                
            elif tool_name == "stock_ai_predict":
                log("CHRONOS", "🤖", "Running AI prediction...", Colors.CYAN)
                # Skip actual model run for speed
                log("CHRONOS", "📈", "Predicted: +2.1% (mock)", Colors.GREEN)
                
            else:
                log("EXECUTOR", "⏭️", f"Skipping {tool_name} (not implemented in dry run)", Colors.YELLOW)
                
        except Exception as e:
            log("EXECUTOR", "❌", f"Error: {str(e)[:50]}...", Colors.RED)
        
        print()
    
    # =========================================================
    # STEP 4: Ensemble
    # =========================================================
    log("ENSEMBLE", "⚖️", "Combining signals...", Colors.CYAN)
    print(f"         Technical: {Colors.YELLOW}NEUTRAL{Colors.END}")
    print(f"         AI Prediction: {Colors.GREEN}+2.1%{Colors.END}")
    print(f"         News Sentiment: {Colors.YELLOW}MIXED{Colors.END}")
    print()
    
    log("REFLECTOR", "🔍", "Self-reflection check...", Colors.CYAN)
    print(f"         Logic consistency: ✅")
    print(f"         Completeness: ✅")
    print()
    
    # =========================================================
    # FINAL
    # =========================================================
    print(f"{Colors.BOLD}{'='*60}{Colors.END}")
    log("RESULT", "🎯", f"Final Recommendation: {Colors.BOLD}HOLD{Colors.END}", Colors.GREEN)
    print(f"{Colors.BOLD}{'='*60}{Colors.END}")
    print()
    
    print(f"{Colors.CYAN}💡 Tip: Run with custom query:{Colors.END}")
    print(f"   python test_agent_flow.py \"NVIDIA 분석해줘\"")
    print()


if __name__ == "__main__":
    main()
