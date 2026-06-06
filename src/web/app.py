"""
Stock Expert Web Server - FastAPI
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
    news_sentiment,
    price_forecast,
    price_forecast_moirai,
)

MOIRAI_ENABLED  = os.environ.get("MOIRAI_ENABLED",  "true").lower()  == "true"
CHRONOS_ENABLED = os.environ.get("CHRONOS_ENABLED", "false").lower() == "true"

app = FastAPI(title="Stock Expert AI", description="AI 주식 전문가")

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
    try:
        result = get_stock_price(ticker, market)
        return JSONResponse(content=json.loads(result))
    except Exception as e:
        return JSONResponse(content={"status": "error", "error": str(e)}, status_code=500)


@app.get("/api/technical/{ticker}")
async def api_technical(ticker: str, period: str = "6mo"):
    """Get technical analysis"""
    try:
        result = technical_analysis(ticker, period)
        return JSONResponse(content=json.loads(result))
    except Exception as e:
        return JSONResponse(content={"status": "error", "error": str(e)}, status_code=500)


@app.get("/api/news/{ticker}")
async def api_news(ticker: str):
    """Get stock news"""
    try:
        result = get_market_news(ticker=ticker, limit=5)
        return JSONResponse(content=json.loads(result))
    except Exception as e:
        return JSONResponse(content={"status": "error", "error": str(e)}, status_code=500)


@app.get("/api/financials/{ticker}")
async def api_financials(ticker: str):
    """Get financial data"""
    try:
        result = get_financials(ticker)
        return JSONResponse(content=json.loads(result))
    except Exception as e:
        return JSONResponse(content={"status": "error", "error": str(e)}, status_code=500)


@app.post("/api/analyze")
async def api_analyze(ticker: str = Form(...), name: str = Form(...),
                      market: str = Form("KR"), forecast_steps: int = Form(5),
                      context_period: str = Form(None)):
    """Full AI analysis"""
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
        
        # Independent signals: news sentiment + price forecast
        try:
            sentiment_data = json.loads(news_sentiment(ticker, name, market))
        except Exception:
            sentiment_data = {"status": "unavailable"}
        forecast_data = None
        if CHRONOS_ENABLED:
            try:
                forecast_data = json.loads(price_forecast(ticker, name, market, forecast_steps, context_period))
            except Exception:
                forecast_data = {"status": "unavailable"}

        moirai_data = None
        if MOIRAI_ENABLED:
            try:
                moirai_data = json.loads(price_forecast_moirai(ticker, name, market, forecast_steps, context_period))
            except Exception:
                moirai_data = {"status": "unavailable"}

        response = {
            "status": "success",
            "ticker": ticker,
            "name": name,
            "price": price_data,
            "technical": tech_data,
            "news": news_data,
            "news_sentiment": sentiment_data,
        }
        if forecast_data is not None:
            response["price_forecast"] = forecast_data
        if moirai_data is not None:
            response["moirai_forecast"] = moirai_data

        return JSONResponse(content=response)
    except Exception as e:
        return JSONResponse(content={"status": "error", "error": str(e)})


@app.post("/api/chat")
async def api_chat(message: str = Form(...)):
    """Natural language chat with AI agent"""
    try:
        result = await asyncio.wait_for(agent.run_for_web(message), timeout=600)
        return JSONResponse(content={
            "status": "success",
            "response": result
        })
    except (asyncio.TimeoutError, TimeoutError):
        return JSONResponse(content={
            "status": "error",
            "error": "분석 시간이 초과되었습니다 (10분). 더 구체적인 종목명을 입력하시거나 다시 시도해주세요."
        })
    except asyncio.CancelledError:
        return JSONResponse(content={
            "status": "error",
            "error": "요청이 취소되었습니다. 다시 시도해주세요."
        })
    except Exception as e:
        return JSONResponse(content={
            "status": "error",
            "error": str(e)
        })


# =========================================================
# Run Server
# =========================================================

if __name__ == "__main__":
    print("🚀 Stock Expert Web Server Starting...")
    print("   Open: http://localhost:8000")
    print("   Mobile: http://<your-ip>:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
