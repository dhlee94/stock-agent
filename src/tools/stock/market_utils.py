"""
Market Utilities - Market detection and localization helpers
"""


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
    # Additional US stocks referenced in NAME_TO_TICKER aliases
    'ADBE': 'Adobe',
    'DIS': 'Disney',
    'V': 'Visa',
    'MA': 'Mastercard',
    'PYPL': 'PayPal',
    'KO': 'Coca-Cola',
    'PEP': 'PepsiCo',
    'WMT': 'Walmart',
    'COST': 'Costco',
    'BA': 'Boeing',
    'LMT': 'Lockheed Martin',
    'CVX': 'Chevron',
    'XOM': 'ExxonMobil',
    'JPM': 'JPMorgan Chase',
    'GS': 'Goldman Sachs',
    'BRK.B': 'Berkshire Hathaway',
    'SBUX': 'Starbucks',
    'MCD': "McDonald's",
    'NKE': 'Nike',
    'PLTR': 'Palantir',
    # Korean Energy
    '015760.KS': '한국전력',
    '010950.KS': 'S-Oil',
    '096770.KS': 'SK이노베이션',
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
    "알파벳": "GOOGL",
    "아마존": "AMZN",
    "테슬라": "TSLA",
    "메타": "META",
    "페이스북": "META",
    "인텔": "INTC",
    "퀄컴": "QCOM",
    "마이크론": "MU",
    "애플": "AAPL",
    "엔비디아": "NVDA",
    "마이크로소프트": "MSFT",
    "넷플릭스": "NFLX",
    "브로드컴": "AVGO",
    "어도비": "ADBE",
    "세일즈포스": "CRM",
    "오라클": "ORCL",
    "TSMC": "TSM",
    "AMD": "AMD",
    "디즈니": "DIS",
    "비자": "V",
    "마스터카드": "MA",
    "페이팔": "PYPL",
    "코카콜라": "KO",
    "펩시": "PEP",
    "월마트": "WMT",
    "코스트코": "COST",
    "보잉": "BA",
    "록히드마틴": "LMT",
    "셰브론": "CVX",
    "엑손모빌": "XOM",
    "엑손": "XOM",
    "제이피모건": "JPM",
    "골드만삭스": "GS",
    "버크셔해서웨이": "BRK.B",
    "버크셔": "BRK.B",
    "스타벅스": "SBUX",
    "맥도날드": "MCD",
    "나이키": "NKE",
    "팔란티어": "PLTR",
    "한전": "015760.KS",
    "한국전력": "015760.KS",
    "에스오일": "010950.KS",
    "SK이노": "096770.KS",
})

def get_company_name(ticker: str) -> str:
    """Get company name from ticker.

    Order: curated TICKER_TO_NAME (aliases/overrides) → authoritative exchange
    listing (KRX / US) → bare ticker code. The listing fallback is what keeps the
    long tail (e.g. 두산에너빌리티 034020.KS) from collapsing to a bare code like
    '034020', which would otherwise become a useless news search query."""
    if ticker in TICKER_TO_NAME:
        return TICKER_TO_NAME[ticker]
    if detect_market(ticker) == 'KR':
        from .kr_listing import lookup_kr_name
        name = lookup_kr_name(ticker)
    else:
        from .us_listing import lookup_us_name
        name = lookup_us_name(ticker)
    return name or ticker.split('.')[0]


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
    if ticker in english_names:
        return english_names[ticker]
    if ticker in TICKER_TO_NAME:
        return TICKER_TO_NAME[ticker]
    # US long tail: fall back to the listed (English) company name so the yfinance /
    # Google News query is a real name, not a bare symbol.
    if detect_market(ticker) == 'US':
        from .us_listing import lookup_us_name
        name = lookup_us_name(ticker)
        if name:
            return name
    return ticker
