"""
Memento Agent에서 사용하는 SQLite 데이터베이스 모듈.

이 모듈은 다음과 같은 정보를 한 곳에서 관리합니다.
- 섹터(sector) 및 티커(ticker) 메타데이터
- Driver Memory: 종목별 가격 변동 요인(드라이버) 기록
- Procedural Memory: 도구(tool) 실행 이력
- Settings: 에이전트/대시보드 설정 값
"""
import sqlite3
import json
import os
from typing import Dict, List, Optional, Any
from datetime import datetime
from contextlib import contextmanager

# Database path
DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'memento.db')
DB_PATH = os.path.normpath(DB_PATH)


@contextmanager
def get_connection():
    """
    SQLite 데이터베이스 커넥션을 열고 자동으로 커밋/롤백을 처리하는 컨텍스트 매니저입니다.
    
    with get_connection() as conn:
        ... 쿼리 실행 ...
    블록이 정상 종료되면 commit, 예외가 발생하면 rollback 후 커넥션을 닫습니다.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """
    데이터베이스 파일이 없을 경우 필요한 모든 테이블과 인덱스를 생성합니다.
    기존 DB가 있을 경우에는 테이블이 없을 때만 생성합니다.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Sectors table: 업종/섹터 기본 정보
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sectors (
                id TEXT PRIMARY KEY,
                name_kr TEXT,
                name_en TEXT
            )
        ''')
        
        # Tickers table: 개별 종목 정보 (섹터, 시장 구분 포함)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tickers (
                ticker TEXT PRIMARY KEY,
                name TEXT,
                sector_id TEXT,
                market TEXT,
                FOREIGN KEY (sector_id) REFERENCES sectors(id)
            )
        ''')
        
        # Sector competitors: 동일 섹터 내 경쟁 관계(또는 대표 peer) 저장
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sector_competitors (
                ticker TEXT,
                competitor_ticker TEXT,
                PRIMARY KEY (ticker, competitor_ticker)
            )
        ''')
        
        # Driver memory: 변동성 드라이버(키워드, 이벤트 등) 저장
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS driver_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT,
                name TEXT,
                driver_type TEXT,
                description TEXT,
                impact_direction TEXT,
                confidence REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Procedural memory: 도구 실행 이력 저장
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS procedural_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tool_name TEXT,
                args_json TEXT,
                result_summary TEXT,
                success INTEGER,
                execution_time_ms INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Settings table: 대시보드/에이전트 동작 설정 값 저장
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                description TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create indexes: 자주 조회되는 컬럼에 인덱스를 생성
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_tickers_sector ON tickers(sector_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_driver_ticker ON driver_memory(ticker)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_proc_tool ON procedural_memory(tool_name)')
        
        print("Database가 성공적으로 초기화되었습니다.")


# ============================================================
# SETTINGS OPERATIONS
# ============================================================

def get_setting(key: str, default: str = "") -> str:
    """
    설정 키(key)에 해당하는 값을 조회합니다.
    값이 없으면 default를 반환합니다.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
        row = cursor.fetchone()
        return row['value'] if row else default

def set_setting(key: str, value: str, description: str = ""):
    """
    설정 값을 저장하거나 업데이트합니다.
    
    Args:
        key: 설정 키 값 (예: "risk_tolerance")
        value: 실제 설정 값 (문자열)
        description: 설정에 대한 한국어/영문 설명
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO settings (key, value, description, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ''', (key, value, description))

def get_all_settings() -> List[Dict[str, Any]]:
    """모든 설정 값을 리스트 형태로 반환합니다."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM settings ORDER BY key')
        return [dict(row) for row in cursor.fetchall()]



# ============================================================
# SECTOR & TICKER OPERATIONS
# ============================================================

def get_sector_competitors(ticker: str) -> List[str]:
    """
    특정 티커에 대한 경쟁사(같은 섹터 내 비교 대상 티커) 목록을 반환합니다.
    우선 sector_competitors 테이블을 조회하고, 없으면 같은 섹터에 속한 다른 티커들을 반환합니다.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # First try direct competitor mapping
        cursor.execute('''
            SELECT competitor_ticker FROM sector_competitors WHERE ticker = ?
        ''', (ticker,))
        
        results = cursor.fetchall()
        if results:
            return [row['competitor_ticker'] for row in results]
        
        # Fallback: get all tickers in the same sector
        cursor.execute('''
            SELECT t2.ticker FROM tickers t1
            JOIN tickers t2 ON t1.sector_id = t2.sector_id
            WHERE t1.ticker = ? AND t2.ticker != ?
        ''', (ticker, ticker))
        
        return [row['ticker'] for row in cursor.fetchall()]


def get_ticker_info(ticker: str) -> Optional[Dict[str, Any]]:
    """
    티커에 대한 상세 정보를 조회합니다.
    섹터 한글명/영문명까지 조인하여 함께 반환합니다.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT t.*, s.name_kr as sector_name_kr, s.name_en as sector_name_en
            FROM tickers t
            LEFT JOIN sectors s ON t.sector_id = s.id
            WHERE t.ticker = ?
        ''', (ticker,))
        
        row = cursor.fetchone()
        return dict(row) if row else None


def add_ticker(ticker: str, name: str, sector_id: str, market: str):
    """
    티커 정보를 추가하거나 업데이트합니다.
    존재하는 primary key(ticker)에 대해서는 REPLACE 동작을 수행합니다.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO tickers (ticker, name, sector_id, market)
            VALUES (?, ?, ?, ?)
        ''', (ticker, name, sector_id, market))


def get_all_sectors() -> List[Dict[str, Any]]:
    """
    모든 섹터 정보와 각 섹터에 속한 티커 목록을 함께 조회합니다.
    Dashboard에서 트리 구조로 표시할 때 사용됩니다.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM sectors')
        sectors = [dict(row) for row in cursor.fetchall()]
        
        for sector in sectors:
            cursor.execute('SELECT ticker, name FROM tickers WHERE sector_id = ?', (sector['id'],))
            sector['tickers'] = [dict(row) for row in cursor.fetchall()]
        
        return sectors


# ============================================================
# DRIVER MEMORY OPERATIONS
# ============================================================

def add_driver(ticker: str, name: str, driver_type: str, 
               description: str, impact_direction: str, confidence: float = 0.8):
    """
    Driver Memory에 새로운 드라이버 레코드를 추가합니다.
    
    Args:
        ticker: 종목 티커
        name: 종목명
        driver_type: 드라이버 유형 (예: "keyword", "event")
        description: 드라이버를 설명하는 텍스트(키워드 등)
        impact_direction: 영향 방향 (예: "positive", "negative", "neutral")
        confidence: 신뢰도 점수 (0.0 ~ 1.0)
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO driver_memory (ticker, name, driver_type, description, impact_direction, confidence)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (ticker, name, driver_type, description, impact_direction, confidence))
        return cursor.lastrowid


def get_drivers(ticker: str, limit: int = 10) -> List[Dict[str, Any]]:
    """특정 티커에 대해 최신 순으로 제한 개수만큼 드라이버 레코드를 반환합니다."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM driver_memory 
            WHERE ticker = ?
            ORDER BY created_at DESC
            LIMIT ?
        ''', (ticker, limit))
        return [dict(row) for row in cursor.fetchall()]


def get_top_drivers(ticker: str, driver_type: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    특정 티커의 드라이버를 유형별로 집계하여 상위 드라이버들을 반환합니다.
    driver_type가 지정되면 해당 유형에 대해서만 집계합니다.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        
        if driver_type:
            cursor.execute('''
                SELECT driver_type, description, impact_direction, 
                       AVG(confidence) as avg_confidence, COUNT(*) as count
                FROM driver_memory 
                WHERE ticker = ? AND driver_type = ?
                GROUP BY description
                ORDER BY avg_confidence DESC
                LIMIT 5
            ''', (ticker, driver_type))
        else:
            cursor.execute('''
                SELECT driver_type, description, impact_direction,
                       AVG(confidence) as avg_confidence, COUNT(*) as count
                FROM driver_memory 
                WHERE ticker = ?
                GROUP BY driver_type, description
                ORDER BY avg_confidence DESC
                LIMIT 10
            ''', (ticker,))
        
        return [dict(row) for row in cursor.fetchall()]


# ============================================================
# PROCEDURAL MEMORY OPERATIONS
# ============================================================

def log_tool_execution(tool_name: str, args: Dict, result_summary: str, 
                       success: bool, execution_time_ms: int = 0):
    """
    도구 실행 이력을 procedural_memory 테이블에 한 줄로 저장합니다.
    
    Args:
        tool_name: 도구 이름 (예: "stock_price")
        args: 도구 실행에 사용된 인자 딕셔너리
        result_summary: 결과 요약 텍스트 (상세 내용은 외부에 저장 가능)
        success: 실행 성공 여부
        execution_time_ms: 실행 시간(ms) (선택)
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO procedural_memory (tool_name, args_json, result_summary, success, execution_time_ms)
            VALUES (?, ?, ?, ?, ?)
        ''', (tool_name, json.dumps(args, ensure_ascii=False), result_summary, int(success), execution_time_ms))
        return cursor.lastrowid


def get_tool_history(tool_name: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
    """
    도구 실행 이력을 최근 순으로 조회합니다.
    tool_name이 지정되면 해당 도구에 대해서만 필터링합니다.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        
        if tool_name:
            cursor.execute('''
                SELECT * FROM procedural_memory 
                WHERE tool_name = ?
                ORDER BY created_at DESC
                LIMIT ?
            ''', (tool_name, limit))
        else:
            cursor.execute('''
                SELECT * FROM procedural_memory 
                ORDER BY created_at DESC
                LIMIT ?
            ''', (limit,))
        
        results = []
        for row in cursor.fetchall():
            item = dict(row)
            item['args'] = json.loads(item['args_json']) if item['args_json'] else {}
            results.append(item)
        
        return results


def get_tool_stats() -> List[Dict[str, Any]]:
    """
    도구별 실행 횟수, 성공 횟수, 평균 실행 시간을 집계한 통계를 반환합니다.
    대시보드에서 도구 사용량을 시각화할 때 사용됩니다.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT tool_name, 
                   COUNT(*) as total_calls,
                   SUM(success) as success_count,
                   AVG(execution_time_ms) as avg_time_ms
            FROM procedural_memory
            GROUP BY tool_name
            ORDER BY total_calls DESC
        ''')
        return [dict(row) for row in cursor.fetchall()]


# ============================================================
# MIGRATION FROM JSON
# ============================================================

def migrate_from_json():
    """
    기존 JSON 파일(`sector_competitors.json`, `driver_memory.json`, `procedural_memory.json`)에
    저장되어 있던 데이터를 SQLite 데이터베이스로 마이그레이션합니다.
    이미 마이그레이션된 경우에도 INSERT OR REPLACE / IGNORE 전략으로 중복을 방지합니다.
    """
    base_path = os.path.join(os.path.dirname(__file__), '..', 'data')
    
    # 1. Migrate sector_competitors.json
    sector_json_path = os.path.join(base_path, 'sector_competitors.json')
    if os.path.exists(sector_json_path):
        print("sector_competitors.json 데이터를 SQLite로 마이그레이션합니다...")
        with open(sector_json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        with get_connection() as conn:
            cursor = conn.cursor()
            
            # Insert sectors
            for sector_id, sector_data in data.get('sectors', {}).items():
                cursor.execute('''
                    INSERT OR REPLACE INTO sectors (id, name_kr, name_en)
                    VALUES (?, ?, ?)
                ''', (sector_id, sector_data.get('name_kr', ''), sector_id))
            
            # Insert tickers
            ticker_to_sector = data.get('ticker_to_sector', {})
            ticker_names = data.get('ticker_names', {})
            
            for ticker, sector_id in ticker_to_sector.items():
                market = 'KR' if '.KS' in ticker else 'US'
                name = ticker_names.get(ticker, ticker)
                cursor.execute('''
                    INSERT OR REPLACE INTO tickers (ticker, name, sector_id, market)
                    VALUES (?, ?, ?, ?)
                ''', (ticker, name, sector_id, market))
            
            # Insert competitors (same sector = competitors)
            for sector_id, sector_data in data.get('sectors', {}).items():
                tickers = sector_data.get('tickers', [])
                for ticker in tickers:
                    for competitor in tickers:
                        if ticker != competitor:
                            cursor.execute('''
                                INSERT OR IGNORE INTO sector_competitors (ticker, competitor_ticker)
                                VALUES (?, ?)
                            ''', (ticker, competitor))
        
        print(f"   티커 {len(ticker_to_sector)}개, 섹터 {len(data.get('sectors', {}))}개를 마이그레이션했습니다.")
    
    # 2. Migrate driver_memory.json
    driver_json_path = os.path.join(base_path, 'driver_memory.json')
    if os.path.exists(driver_json_path):
        print("driver_memory.json 데이터를 SQLite로 마이그레이션합니다...")
        with open(driver_json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        count = 0
        with get_connection() as conn:
            cursor = conn.cursor()
            
            for ticker, ticker_data in data.items():
                name = ticker_data.get('name', ticker)
                for driver in ticker_data.get('drivers', []):
                    # Handle both string (legacy) and dict formats
                    if isinstance(driver, str):
                        driver_type = 'keyword'
                        description = driver
                        impact = 'neutral'
                        confidence = 0.8
                    else:
                        driver_type = driver.get('type', 'unknown')
                        description = driver.get('description', '')
                        impact = driver.get('impact', 'neutral')
                        confidence = driver.get('confidence', 0.8)
                        
                    cursor.execute('''
                        INSERT INTO driver_memory (ticker, name, driver_type, description, impact_direction, confidence)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (ticker, name, driver_type, description, impact, confidence))
                    count += 1
        
        print(f"   드라이버 레코드 {count}건을 마이그레이션했습니다.")
    
    # 3. Migrate procedural_memory.json
    proc_json_path = os.path.join(base_path, 'procedural_memory.json')
    if os.path.exists(proc_json_path):
        print("procedural_memory.json 데이터를 SQLite로 마이그레이션합니다...")
        with open(proc_json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        count = 0
        with get_connection() as conn:
            cursor = conn.cursor()
            
            for entry in data if isinstance(data, list) else []:
                cursor.execute('''
                    INSERT INTO procedural_memory (tool_name, args_json, result_summary, success)
                    VALUES (?, ?, ?, ?)
                ''', (entry.get('tool', 'unknown'),
                      json.dumps(entry.get('args', {}), ensure_ascii=False),
                      entry.get('result', ''),
                      1 if entry.get('success', True) else 0))
                count += 1
        
        print(f"   Procedural 메모리 레코드 {count}건을 마이그레이션했습니다.")
    
    print("\nJSON 데이터 마이그레이션이 완료되었습니다.")


# Initialize DB on import (create tables if they don't exist)
if not os.path.exists(DB_PATH):
    init_db()
