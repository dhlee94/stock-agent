"""
주식 전문가 웹 서버 - FastAPI
"""
import sys
import os

# Add src directory to path
SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SRC_DIR)

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn
import json
import asyncio

# Import agent
from agent_client import MementoAgent

# Import stock tools
from tools.stock import (
    get_stock_price,
    get_stock_chart,
    get_financials,
    get_market_news,
    technical_analysis,
    analyze_stock_ai,
)

app = FastAPI(title="주식 전문가 AI", description="AI 기반 주식 분석 전문가")

# Setup templates and static files
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")

# Initialize agent (singleton)
agent = MementoAgent()


# =========================================================
# Web Pages
# =========================================================

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Main page"""
    return templates.TemplateResponse("index.html", {"request": request})


# =========================================================
# API Endpoints
# =========================================================

@app.get("/api/price/{ticker}")
async def api_price(ticker: str, market: str = "KR"):
    """Get real-time stock price"""
    result = get_stock_price(ticker, market)
    return JSONResponse(content=json.loads(result))


@app.get("/api/technical/{ticker}")
async def api_technical(ticker: str, period: str = "6mo"):
    """Get technical analysis"""
    result = technical_analysis(ticker, period)
    return JSONResponse(content=json.loads(result))


@app.get("/api/news/{ticker}")
async def api_news(ticker: str):
    """Get stock news"""
    result = get_market_news(ticker=ticker, limit=5)
    return JSONResponse(content=json.loads(result))


@app.get("/api/financials/{ticker}")
async def api_financials(ticker: str):
    """Get financial data"""
    result = get_financials(ticker)
    return JSONResponse(content=json.loads(result))


@app.post("/api/analyze")
async def api_analyze(ticker: str = Form(...), name: str = Form(...), market: str = Form("KR")):
    """종합 AI 주식 분석"""
    try:
        # Get all data
        price_data = json.loads(get_stock_price(ticker, market))
        tech_data = json.loads(technical_analysis(ticker))
        
        # Get market news
        try:
            # Pass name as query fallback if ticker has no news
            news_data = json.loads(get_market_news(ticker, query=name, limit=5))
        except Exception:
            news_data = {"status": "error", "news": []}
        
        # Try AI prediction (may fail if model not loaded)
        try:
            ai_data = json.loads(analyze_stock_ai(ticker, name, market))
        except Exception:
            ai_data = {"status": "unavailable", "message": "AI 모델이 로드되지 않았습니다."}
        
        return JSONResponse(
            content={
                "status": "success",
                "ticker": ticker,
                "name": name,
                "price": price_data,
                "technical": tech_data,
                "news": news_data,
                "ai_prediction": ai_data,
            }
        )
    except Exception as e:
        return JSONResponse(
            content={
                "status": "error",
                "error": f"분석 중 오류가 발생했습니다: {str(e)}",
            }
        )


@app.post("/api/chat")
async def api_chat(message: str = Form(...)):
    """자연어로 AI 에이전트에게 질문"""
    try:
        result = await agent.run_for_web(message)
        return JSONResponse(
            content={
                "status": "success",
                "response": result,
            }
        )
    except Exception as e:
        return JSONResponse(
            content={
                "status": "error",
                "error": f"채팅 처리 중 오류가 발생했습니다: {str(e)}",
            }
        )


# =========================================================
# Run Server
# =========================================================

if __name__ == "__main__":
    print("🚀 주식 전문가 웹 서버를 시작합니다...")
    print("   접속: http://localhost:8000")
    print("   모바일: http://<PC-아이피>:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
