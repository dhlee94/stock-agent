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
from datetime import datetime

# Add src directory to path
SRC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
sys.path.insert(0, SRC_DIR)
sys.path.insert(0, os.path.join(SRC_DIR, "tools", "stock"))

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
    # STEP 0: Market Detection (NEW!)
    # =========================================================
    from market_utils import detect_market, get_company_name, get_english_name
    
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
        "sk하이닉스": "000660.KS",
        "마이크로소프트": "MSFT",
        "microsoft": "MSFT",
    }
    
    for name, tk in ticker_map.items():
        if name.lower() in query.lower():
            ticker = tk
            break
    
    if not ticker:
        ticker = "005930.KS"  # Default to Samsung
        log("MARKET", "⚠️", f"Could not detect ticker, defaulting to {ticker}", Colors.YELLOW)
    
    # Detect market
    market = detect_market(ticker)
    company_name = get_company_name(ticker)
    english_name = get_english_name(ticker)
    
    log("MARKET", "🌍", f"Detected: {Colors.BOLD}{ticker}{Colors.END} → {Colors.BOLD}{market}{Colors.END}", Colors.CYAN)
    print(f"         Company: {company_name}")
    if market == "US":
        print(f"         English: {english_name}")
        print(f"         🌐 Will search English news + Korean summary")
    print()
    
    # =========================================================
    # STEP 1: Check Driver Memory
    # =========================================================
    log("MEMORY", "🧠", "Checking DriverMemory...", Colors.BLUE)
    
    from driver_memory import DriverMemory
    dm = DriverMemory()
    
    # Check cache
    cached_drivers = dm.get_drivers(ticker)
    if cached_drivers:
        log("MEMORY", "✅", f"Found cached drivers for {ticker}:", Colors.GREEN)
        print(f"         Keywords: {Colors.BOLD}{cached_drivers.get('drivers', [])}{Colors.END}")
        print(f"         Last Updated: {cached_drivers.get('last_updated', 'N/A')}")
    else:
        log("MEMORY", "❌", f"No cached drivers for {ticker}", Colors.YELLOW)
        log("MEMORY", "🔄", "Triggering analyze_historical_drivers()...", Colors.YELLOW)
        
        time.sleep(0.5)
        
        try:
            result = dm.analyze_historical_drivers(ticker)
            if "error" not in result:
                log("MEMORY", "✅", "Analysis complete!", Colors.GREEN)
                print(f"         New Keywords: {Colors.BOLD}{result.get('drivers', [])}{Colors.END}")
                cached_drivers = result
            else:
                log("MEMORY", "⚠️", f"Analysis failed: {result.get('error')}", Colors.RED)
        except Exception as e:
            log("MEMORY", "❌", f"Error: {e}", Colors.RED)
    
    print()
    
    # =========================================================
    # STEP 2: Simulate Planner (Market-Aware)
    # =========================================================
    log("PLANNER", "🤔", f"Generating execution plan for {Colors.BOLD}{market}{Colors.END} market...", Colors.CYAN)
    
    drivers = cached_drivers.get('drivers', []) if cached_drivers else ["실적발표", "기술개발"]
    
    mock_plan = [
        {"step": 1, "tool": "analyze_drivers", "args": {"ticker": ticker}, "reason": "Get historical drivers"},
        {"step": 2, "tool": "stock_price", "args": {"ticker": ticker, "market": market}, "reason": "Get current price"},
        {"step": 3, "tool": "stock_news", "args": {"ticker": ticker, "query": f"{company_name} {drivers[0] if drivers else ''}"}, "reason": f"Search {'English' if market == 'US' else 'Korean'} news"},
        {"step": 4, "tool": "stock_technical", "args": {"ticker": ticker}, "reason": "Technical analysis"},
        {"step": 5, "tool": "analyze_peers", "args": {"ticker": ticker}, "reason": "STL Trend correlation with sector peers"},
        {"step": 6, "tool": "calculate_risk", "args": {"ticker": ticker, "market": market}, "reason": "Calculate Target/Stop-loss"},
    ]
    
    log("PLANNER", "✅", f"Plan created with {len(mock_plan)} steps:", Colors.GREEN)
    for step in mock_plan:
        print(f"         {step['step']}. {Colors.BOLD}{step['tool']}{Colors.END} - {step['reason']}")
    
    print()
    
    # =========================================================
    # STEP 3: Execute Tools
    # =========================================================
    log("EXECUTOR", "🛠️", "Executing tools...", Colors.YELLOW)
    
    from tools.stock import get_stock_price, technical_analysis, get_market_news, analyze_peer_group
    from risk_manager import calculate_risk_levels
    
    tech_data = None
    current_price = 0
    peer_context = None  # Store Reference Proxy for Reflector verification
    risk_result = None
    
    for step in mock_plan:
        tool_name = step["tool"]
        args = step["args"]
        
        log("EXECUTOR", "⚡", f"Step {step['step']}: {tool_name}", Colors.YELLOW)
        print(f"         Args: {args}")
        
        time.sleep(0.3)
        
        try:
            if tool_name == "stock_price":
                result = get_stock_price(args.get("ticker"), args.get("market", "KR"))
                result_data = json.loads(result)
                current_price = result_data.get('current_price', 0)
                log("EXECUTOR", "📊", f"Price: {current_price:,.0f} ({result_data.get('change_percent', 'N/A'):+.2f}%)", Colors.GREEN)
                
            elif tool_name == "stock_technical":
                result = technical_analysis(args.get("ticker"))
                tech_data = json.loads(result)
                log("EXECUTOR", "📈", f"Signal: {tech_data.get('recommendation', 'N/A')}", Colors.GREEN)
                
            elif tool_name == "stock_news":
                result = get_market_news(ticker=args.get("ticker"), query=args.get("query"), limit=3)
                result_data = json.loads(result)
                news_count = result_data.get("count", 0)
                detected_market = result_data.get("market", "KR")
                log("EXECUTOR", "📰", f"Found {news_count} articles (Market: {detected_market})", Colors.GREEN)
                
                # Show Korean summary for US stocks
                if result_data.get("global_news_summary_kr"):
                    log("EXECUTOR", "🌐", "Korean Summary:", Colors.CYAN)
                    print(f"         {result_data['global_news_summary_kr'][:100]}...")
                
            elif tool_name == "analyze_drivers":
                log("EXECUTOR", "🧠", "Using cached drivers", Colors.GREEN)
            
            elif tool_name == "analyze_peers":
                result = analyze_peer_group(args.get("ticker"))
                result_data = json.loads(result)
                peers_found = result_data.get("entity_mining", {}).get("found_peers", 0)
                similarities = result_data.get("similarity_analysis", [])
                reference_proxy = result_data.get("reference_proxy")
                synthesis = result_data.get("synthesis", "")
                
                # Store for Reflector verification
                peer_context = {
                    "peers_found": peers_found,
                    "similarities": similarities,
                    "reference_proxy": reference_proxy,
                    "synthesis": synthesis,
                    "has_high_correlation": reference_proxy is not None
                }
                
                if peers_found > 0 and similarities:
                    top_peer = similarities[0]
                    log("EXECUTOR", "📊", f"[STL Trend] Found {peers_found} peers", Colors.GREEN)
                    log("EXECUTOR", "🔗", f"Top correlation: {top_peer['name']} ({top_peer['trend_correlation']:.2f})", Colors.CYAN)
                    
                    if reference_proxy:
                        proxy_trend = reference_proxy.get("momentum", {}).get("trend", "unknown")
                        log("EXECUTOR", "✅", f"Reference Proxy: {reference_proxy['name']} ({proxy_trend})", Colors.GREEN)
                    else:
                        log("EXECUTOR", "⚠️", "No Reference Proxy (correlation < 0.7)", Colors.YELLOW)
                else:
                    log("EXECUTOR", "⚠️", "No correlated peers found in same market", Colors.YELLOW)
                
            elif tool_name == "calculate_risk":
                if tech_data and current_price > 0:
                    risk_result = calculate_risk_levels(current_price, tech_data)
                    log("RISK", "🎯", f"Target: {risk_result['target_price']:,.0f} ({risk_result['target_percent']:+.1f}%)", Colors.GREEN)
                    log("RISK", "🛑", f"Stop-loss: {risk_result['stop_loss']:,.0f} ({risk_result['stop_loss_percent']:.1f}%)", Colors.RED)
                    log("RISK", "⚖️", f"Risk/Reward: {risk_result['risk_reward_ratio']}:1 ({risk_result['entry_rating']})", Colors.CYAN)
                else:
                    log("RISK", "⚠️", "Skipped - missing price or technical data", Colors.YELLOW)
                
            else:
                log("EXECUTOR", "⏭️", f"Skipping {tool_name}", Colors.YELLOW)
                
        except Exception as e:
            log("EXECUTOR", "❌", f"Error: {str(e)[:80]}", Colors.RED)
        
        print()
    
    # =========================================================
    # STEP 4: Reflector - Self-Verification with Reference Proxy
    # =========================================================
    log("REFLECTOR", "🔍", "Self-reflection & Reference Proxy Verification...", Colors.CYAN)
    print(f"         Market Detection: ✅ ({market})")
    print(f"         Risk Calculated: ✅" if risk_result else "         Risk Calculated: ⚠️")
    print(f"         Multi-lang News: ✅" if market == "US" else "         Multi-lang News: N/A (KR)")
    
    # Reference Proxy Verification
    confidence_level = "Medium"
    verification_notes = []
    
    if peer_context:
        if peer_context.get("has_high_correlation") and peer_context.get("reference_proxy"):
            proxy = peer_context["reference_proxy"]
            proxy_name = proxy.get("name", "Unknown")
            proxy_trend = proxy.get("momentum", {}).get("trend", "unknown")
            proxy_corr = proxy.get("trend_correlation", 0)
            
            # Check if our analysis aligns with proxy trend
            if tech_data:
                our_signal = tech_data.get("recommendation", "HOLD")
                
                # Alignment check
                proxy_bullish = proxy_trend == "bullish"
                our_bullish = our_signal in ["BUY", "STRONG_BUY"]
                our_bearish = our_signal in ["SELL", "STRONG_SELL"]
                
                if (proxy_bullish and our_bullish) or (not proxy_bullish and our_bearish):
                    confidence_level = "High"
                    verification_notes.append(f"✅ Aligned with {proxy_name} ({proxy_trend})")
                elif proxy_bullish and our_bearish:
                    confidence_level = "Low"
                    verification_notes.append(f"⚠️ Divergent: {proxy_name} is {proxy_trend} but signal is {our_signal}")
                elif not proxy_bullish and our_bullish:
                    confidence_level = "Low"
                    verification_notes.append(f"⚠️ Divergent: {proxy_name} is {proxy_trend} but signal is {our_signal}")
                else:
                    verification_notes.append(f"📊 Reference: {proxy_name} ({proxy_trend}, corr={proxy_corr:.2f})")
            
            log("REFLECTOR", "🔗", f"Reference Proxy Verified: {proxy_name} (Trend: {proxy_trend})", Colors.CYAN)
        else:
            verification_notes.append("⚠️ No high-correlation proxy found - independent analysis only")
            log("REFLECTOR", "⚠️", "No Reference Proxy - relying on independent signals", Colors.YELLOW)
    else:
        verification_notes.append("⚠️ Peer analysis not available")
    
    # Show verification result
    print()
    log("REFLECTOR", "📋", f"Confidence Level: {Colors.BOLD}{confidence_level}{Colors.END}", 
        Colors.GREEN if confidence_level == "High" else (Colors.YELLOW if confidence_level == "Medium" else Colors.RED))
    
    for note in verification_notes:
        print(f"         {note}")
    
    print()
    print(f"{Colors.BOLD}{'='*60}{Colors.END}")
    log("RESULT", "🎯", f"Analysis Complete for {Colors.BOLD}{company_name}{Colors.END} (Confidence: {confidence_level})", Colors.GREEN)
    print(f"{Colors.BOLD}{'='*60}{Colors.END}")
    print()
    
    print(f"{Colors.CYAN}💡 Try different markets:{Colors.END}")
    print(f"   python test_agent_flow.py \"삼성전자 분석\"   # KR stock")
    print(f"   python test_agent_flow.py \"NVIDIA 분석\"    # US stock")
    print()


if __name__ == "__main__":
    main()

