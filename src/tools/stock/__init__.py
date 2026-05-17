"""
Stock Tools Package - Professional Stock Analysis Tools
"""
import sys
import os

# Ensure stock tools directory is in path
STOCK_DIR = os.path.dirname(os.path.abspath(__file__))
TOOLS_DIR = os.path.dirname(STOCK_DIR)
SRC_DIR = os.path.dirname(TOOLS_DIR)

for path in [STOCK_DIR, TOOLS_DIR, SRC_DIR]:
    if path not in sys.path:
        sys.path.insert(0, path)

from price import get_stock_price
from chart import get_stock_chart
from financials import get_financials
from news import get_market_news
from technical import technical_analysis
from compare import compare_stocks
from sector import get_sector_analysis
from predictor import news_sentiment, price_forecast
from peer_analysis import analyze_peer_group

__all__ = [
    'get_stock_price',
    'get_stock_chart',
    'get_financials',
    'get_market_news',
    'technical_analysis',
    'compare_stocks',
    'get_sector_analysis',
    'news_sentiment',
    'price_forecast',
    'analyze_peer_group',
]
