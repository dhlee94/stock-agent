"""
Stock Expert Web Server - FastAPI
"""
import sys
import os
import uuid

# Add src directory to path
SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SRC_DIR)

from fastapi import FastAPI, Request, Form, Header, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn
import json
import asyncio
from typing import Dict

# WEB_API_KEY가 .env에 설정된 경우 모든 /api/* 요청에 X-API-Key 헤더 필요.
_WEB_API_KEY = os.environ.get("WEB_API_KEY", "").strip()


async def _require_api_key(x_api_key: str = Header(default="")) -> None:
    if _WEB_API_KEY and x_api_key != _WEB_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key header")

# Import agent
from agent_client import MementoAgent

# Import stock tools
from tools.stock import (
    get_stock_price,
    get_financials,
    get_market_news,
    technical_analysis,
)

app = FastAPI(title="Stock Expert AI", description="AI 주식 전문가")

# Setup templates and static files
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")

# Initialize agent (singleton)
agent = MementoAgent()

# In-memory job store: job_id → {status, response?, error?}
_jobs: Dict[str, dict] = {}


async def _run_chat_job(job_id: str, message: str):
    """Background task that runs the agent and stores the result."""
    try:
        result = await asyncio.wait_for(agent.run_for_web(message), timeout=600)
        _jobs[job_id] = {"status": "done", "response": result}
    except (asyncio.TimeoutError, TimeoutError):
        _jobs[job_id] = {
            "status": "error",
            "error": "분석 시간이 초과되었습니다 (10분).",
        }
    except asyncio.CancelledError:
        _jobs[job_id] = {"status": "error", "error": "요청이 취소되었습니다."}
    except Exception as e:
        _jobs[job_id] = {"status": "error", "error": str(e)}

    if len(_jobs) > 100:
        done_keys = [k for k, v in _jobs.items() if v["status"] != "running"]
        for k in done_keys[:max(0, len(_jobs) - 100)]:
            _jobs.pop(k, None)


# =========================================================
# Web Pages
# =========================================================

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request, "index.html")


# =========================================================
# API Endpoints
# =========================================================

@app.get("/api/price/{ticker}")
async def api_price(ticker: str, market: str = "KR", _: None = Depends(_require_api_key)):
    try:
        result = get_stock_price(ticker, market)
        return JSONResponse(content=json.loads(result))
    except Exception as e:
        return JSONResponse(content={"status": "error", "error": str(e)}, status_code=500)


@app.get("/api/technical/{ticker}")
async def api_technical(ticker: str, period: str = "6mo", _: None = Depends(_require_api_key)):
    try:
        result = technical_analysis(ticker, period)
        return JSONResponse(content=json.loads(result))
    except Exception as e:
        return JSONResponse(content={"status": "error", "error": str(e)}, status_code=500)


@app.get("/api/news/{ticker}")
async def api_news(ticker: str, _: None = Depends(_require_api_key)):
    try:
        result = get_market_news(ticker=ticker, limit=5)
        return JSONResponse(content=json.loads(result))
    except Exception as e:
        return JSONResponse(content={"status": "error", "error": str(e)}, status_code=500)


@app.get("/api/financials/{ticker}")
async def api_financials(ticker: str, _: None = Depends(_require_api_key)):
    try:
        result = get_financials(ticker)
        return JSONResponse(content=json.loads(result))
    except Exception as e:
        return JSONResponse(content={"status": "error", "error": str(e)}, status_code=500)


@app.post("/api/analyze")
async def api_analyze(ticker: str = Form(...), name: str = Form(...),
                      market: str = Form("KR"),
                      _: None = Depends(_require_api_key)):
    """Full AI analysis"""
    try:
        price_data = json.loads(get_stock_price(ticker, market))
        tech_data = json.loads(technical_analysis(ticker))

        try:
            news_data = json.loads(get_market_news(ticker, query=name, limit=5))
        except Exception:
            news_data = {"status": "error", "news": []}

        response = {
            "status": "success",
            "ticker": ticker,
            "name": name,
            "price": price_data,
            "technical": tech_data,
            "news": news_data,
        }

        return JSONResponse(content=response)
    except Exception as e:
        return JSONResponse(content={"status": "error", "error": str(e)})


@app.post("/api/chat")
async def api_chat(message: str = Form(...), _: None = Depends(_require_api_key)):
    job_id = uuid.uuid4().hex[:12]
    _jobs[job_id] = {"status": "running"}
    asyncio.create_task(_run_chat_job(job_id, message))
    return JSONResponse({"job_id": job_id})


@app.get("/api/job/{job_id}")
async def api_job_status(job_id: str, _: None = Depends(_require_api_key)):
    job = _jobs.get(job_id)
    if not job:
        return JSONResponse({"status": "not_found"}, status_code=404)
    return JSONResponse(job)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
