"""
Market Utilities - Market detection and localization helpers
"""
from typing import List, Tuple


def detect_market(ticker: str) -> str:
    """
    Detect market origin based on ticker suffix.
    
    Args:
        ticker: Stock ticker symbol
        
    Returns:
        'KR' for Korean stocks, 'US' for US/international stocks
    """
    if ticker.endswith(('.KS', '.KQ')):
        return 'KR'
    return 'US'


def get_search_language(market: str) -> str:
    """Get primary search language for market."""
    return 'ko' if market == 'KR' else 'en'


def optimize_search_query(ticker: str, name: str, keywords: List[str], market: str) -> Tuple[str, str]:
    """
    Generate optimized search query based on market.
    
    Returns:
        (primary_query, fallback_query) - Primary query and fallback if primary fails
    """
    if market == 'KR':
        # Korean stocks: Use Korean company name + Korean keywords
        primary = f"{name} {' '.join(keywords[:2])}"
        fallback = f"{name} 주가 전망"
    else:
        # US stocks: Use English-optimized queries
        # Convert Korean keywords to English equivalents if possible
        english_keywords = _translate_keywords_to_english(keywords)
        primary = f"{name} {' '.join(english_keywords[:2])} analysis"
        fallback = f"{ticker} stock news outlook"
    
    return primary, fallback


def _translate_keywords_to_english(keywords: List[str]) -> List[str]:
    """
    Translate common Korean financial keywords to English.
    Falls back to original if no translation available.
    """
    translations = {
        # Events
        '실적발표': 'earnings',
        '실적': 'earnings',
        '배당': 'dividend',
        '공급계약': 'supply deal',
        '인수합병': 'M&A',
        '파업': 'strike',
        '유상증자': 'capital raise',
        # Technology
        '반도체': 'semiconductor',
        '2차전지': 'battery',
        'AI': 'AI',
        '신사업': 'new business',
        '기술개발': 'R&D',
        # Competition
        '경쟁사': 'competition',
        '점유율': 'market share',
        # Samsung-specific
        'HBM': 'HBM',
        '파운드리': 'foundry',
        '수율': 'yield',
        # General
        '전망': 'outlook',
        '분석': 'analysis',
    }
    
    result = []
    for kw in keywords:
        translated = translations.get(kw, kw)
        result.append(translated)
    
    return result


# Ticker to Name mapping (Centralized Source)
TICKER_TO_NAME = {
    # Korean Stocks
    '005930.KS': '삼성전자',
    '000660.KS': 'SK하이닉스',
    '035420.KS': 'NAVER',
    '035720.KS': '카카오',
    '005380.KS': '현대차',
    '000270.KS': '기아',
    '051910.KS': 'LG화학',
    '006400.KS': '삼성SDI',
    '003670.KS': '포스코퓨처엠',
    '207940.KS': '삼성바이오로직스',
    '068270.KS': '셀트리온',
    '105560.KS': 'KB금융',
    '055550.KS': '신한지주',
    '066570.KS': 'LG전자',
    '012330.KS': '현대모비스',
    '034730.KS': 'SK',
    '030200.KS': 'KT',
    '017670.KS': 'SK텔레콤',
    '015760.KS': '한국전력',
    '032830.KS': '삼성생명',
    '373220.KS': 'LG에너지솔루션',
    '005490.KS': '포스코홀딩스',
    '012450.KS': '한화에어로스페이스',
    # US Stocks
    'AAPL': 'Apple',
    'MSFT': 'Microsoft',
    'GOOGL': 'Alphabet',
    'GOOG': 'Alphabet',
    'AMZN': 'Amazon',
    'NVDA': 'NVIDIA',
    'META': 'Meta',
    'TSLA': 'Tesla',
    'AMD': 'AMD',
    'INTC': 'Intel',
    'NFLX': 'Netflix',
    'AVGO': 'Broadcom',
    'CRM': 'Salesforce',
    'ORCL': 'Oracle',
    'QCOM': 'Qualcomm',
    'TSM': 'TSMC',
    'MU': 'Micron',
}

# Reverse mapping for entity mining fallback
NAME_TO_TICKER = {v: k for k, v in TICKER_TO_NAME.items()}
# Add some aliases
NAME_TO_TICKER.update({
    "삼성": "005930.KS",
    "하이닉스": "000660.KS",
    "현대자동차": "005380.KS",
    "네이버": "035420.KS",
    "구글": "GOOGL",
    "아마존": "AMZN",
    "테슬라": "TSLA",
    "메타": "META",
    "인텔": "INTC",
    "퀄컴": "QCOM",
    "마이크론": "MU",
    "애플": "AAPL",
    "엔비디아": "NVDA",
    "마이크로소프트": "MSFT",
})

def get_company_name(ticker: str) -> str:
    """Get company name from ticker."""
    return TICKER_TO_NAME.get(ticker, ticker.split('.')[0])


def get_english_name(ticker: str) -> str:
    """Get English company name for search purposes."""
    english_names = {
        '005930.KS': 'Samsung Electronics',
        '000660.KS': 'SK Hynix',
        '035420.KS': 'NAVER',
        '035720.KS': 'Kakao',
        '005380.KS': 'Hyundai Motor',
        '000270.KS': 'Kia',
        '051910.KS': 'LG Chem',
        '006400.KS': 'Samsung SDI',
        '373220.KS': 'LG Energy Solution',
        '005490.KS': 'POSCO Holdings',
    }
    return english_names.get(ticker, TICKER_TO_NAME.get(ticker, ticker))
