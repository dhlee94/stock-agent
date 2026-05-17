"""
Tools Package - Stock Expert Edition
"""
import sys
import os

# Ensure tools directory is in path
TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

# Stock Tools (main focus)
from stock import (
    get_stock_price,
    get_stock_chart,
    get_financials,
    get_market_news,
    technical_analysis,
    compare_stocks,
    get_sector_analysis,
    news_sentiment,
    price_forecast,
)

# Utility Tools
from search import search_web
from crawl import crawl_url
from executor import execute_python
from calc import calculate_math
from document import read_document
from memory import save_feedback

__all__ = [
    # Stock Tools
    'get_stock_price',
    'get_stock_chart',
    'get_financials',
    'get_market_news',
    'technical_analysis',
    'compare_stocks',
    'get_sector_analysis',
    'news_sentiment',
    'price_forecast',
    # Utility Tools
    'search_web',
    'crawl_url',
    'execute_python',
    'calculate_math',
    'read_document',
    'save_feedback',
]
