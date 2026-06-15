"""
SQLite Database Module for Memento Agent

Centralized data management for:
- Sector/Ticker information
- Driver Memory (price impact factors)
- Procedural Memory (tool execution history)
- Episodic & Semantic Memory
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
    """Context manager for database connections."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Initialize database with all tables."""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Sectors table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sectors (
                id TEXT PRIMARY KEY,
                name_kr TEXT,
                name_en TEXT
            )
        ''')
        
        # Tickers table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tickers (
                ticker TEXT PRIMARY KEY,
                name TEXT,
                sector_id TEXT,
                market TEXT,
                FOREIGN KEY (sector_id) REFERENCES sectors(id)
            )
        ''')
        
        # Sector competitors
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sector_competitors (
                ticker TEXT,
                competitor_ticker TEXT,
                PRIMARY KEY (ticker, competitor_ticker)
            )
        ''')
        
        # Driver memory
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
        
        # Procedural memory
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
        
        # Settings table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                description TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Episodic memory
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS episodic_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task TEXT,
                plan_json TEXT,
                result TEXT,
                score REAL,
                lessons_json TEXT,
                embedding_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Semantic memory
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS semantic_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lesson TEXT UNIQUE,
                source_task TEXT,
                embedding_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                compression_level TEXT DEFAULT 'raw',
                period_key TEXT,
                source_count INTEGER DEFAULT 1
            )
        ''')
        
        # Clean up legacy prediction log table if user wants to keep the code light.
        # However, it's safer to just stop using it than to drop it unprompted.
        # We will keep the table definition here but remove the operations later.

        # Create indexes
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_tickers_sector ON tickers(sector_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_driver_ticker ON driver_memory(ticker)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_proc_tool ON procedural_memory(tool_name)')

        print("✅ Database initialized successfully", file=__import__("sys").stderr)


# ============================================================
# SETTINGS OPERATIONS
# ============================================================

def get_setting(key: str, default: str = "") -> str:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
        row = cursor.fetchone()
        return row['value'] if row else default

def set_setting(key: str, value: str, description: str = ""):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO settings (key, value, description, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ''', (key, value, description))

def get_all_settings() -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM settings ORDER BY key')
        return [dict(row) for row in cursor.fetchall()]


# ============================================================
# SECTOR & TICKER OPERATIONS
# ============================================================

def get_ticker_info(ticker: str) -> Optional[Dict[str, Any]]:
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
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO tickers (ticker, name, sector_id, market)
            VALUES (?, ?, ?, ?)
        ''', (ticker, name, sector_id, market))


# ============================================================
# DRIVER MEMORY OPERATIONS
# ============================================================

def add_driver(ticker: str, name: str, driver_type: str, 
               description: str, impact_direction: str, confidence: float = 0.8):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO driver_memory (ticker, name, driver_type, description, impact_direction, confidence)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (ticker, name, driver_type, description, impact_direction, confidence))
        return cursor.lastrowid


def get_drivers(ticker: str, limit: int = 10) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM driver_memory 
            WHERE ticker = ?
            ORDER BY created_at DESC
            LIMIT ?
        ''', (ticker, limit))
        return [dict(row) for row in cursor.fetchall()]


# ============================================================
# PROCEDURAL MEMORY OPERATIONS
# ============================================================

def log_tool_execution(tool_name: str, args: Dict, result_summary: str, 
                       success: bool, execution_time_ms: int = 0):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO procedural_memory (tool_name, args_json, result_summary, success, execution_time_ms)
            VALUES (?, ?, ?, ?, ?)
        ''', (tool_name, json.dumps(args, ensure_ascii=False), result_summary, int(success), execution_time_ms))
        return cursor.lastrowid


def get_tool_history(tool_name: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        if tool_name:
            cursor.execute('SELECT * FROM procedural_memory WHERE tool_name = ? ORDER BY created_at DESC LIMIT ?', (tool_name, limit))
        else:
            cursor.execute('SELECT * FROM procedural_memory ORDER BY created_at DESC LIMIT ?', (limit,))
        
        results = []
        for row in cursor.fetchall():
            item = dict(row)
            item['args'] = json.loads(item['args_json']) if item['args_json'] else {}
            results.append(item)
        return results


# ============================================================
# LEGACY PREDICTION OPERATIONS (Disabled)
# ============================================================

def save_prediction(*args, **kwargs):
    """Legacy: predictions disabled."""
    return -1

def get_pending_predictions(*args, **kwargs):
    """Legacy: predictions disabled."""
    return []

def evaluate_prediction(*args, **kwargs):
    """Legacy: predictions disabled."""
    pass

def get_forecast_accuracy(ticker: str, min_samples: int = 3) -> List[Dict[str, Any]]:
    """Legacy: predictions disabled. Returns empty list."""
    return []

def get_global_accuracy_summary(min_samples: int = 5) -> List[Dict[str, Any]]:
    """Legacy: predictions disabled. Returns empty list."""
    return []


# ============================================================
# SEMANTIC MEMORY OPERATIONS
# ============================================================

def get_semantic_lessons_by_level(level: str) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, lesson, embedding_json, period_key, created_at FROM semantic_memory WHERE compression_level=?", (level,))
        return [dict(r) for r in cursor.fetchall()]


def save_compressed_lesson(lesson: str, embedding: list, level: str, period_key: str, source_count: int) -> bool:
    with get_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO semantic_memory (lesson, source_task, embedding_json, compression_level, period_key, source_count) VALUES (?, ?, ?, ?, ?, ?)",
                (lesson, f"compressed:{period_key}", json.dumps(embedding), level, period_key, source_count)
            )
            return True
        except Exception:
            return False


def delete_semantic_lessons_by_ids(ids: List[int]):
    if not ids: return
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.executemany("DELETE FROM semantic_memory WHERE id=?", [(i,) for i in ids])


init_db()


def reembed_if_model_changed(new_model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2") -> int:
    current = get_setting("embedding_model", "")
    if current == new_model_name: return 0
    print(f"🔄 [DB] Embedding model changed. Re-embedding memory...")
    try:
        from memory_store import MemoryStore
        ms = MemoryStore()
        count = 0
        with get_connection() as conn:
            read_cur = conn.cursor()
            write_cur = conn.cursor()
            read_cur.execute("SELECT id, task FROM episodic_memory")
            for row_id, task in read_cur.fetchall():
                write_cur.execute("UPDATE episodic_memory SET embedding_json=? WHERE id=?", (json.dumps(ms._get_embedding(task)), row_id))
                count += 1
            read_cur.execute("SELECT id, lesson FROM semantic_memory")
            for row_id, lesson in read_cur.fetchall():
                write_cur.execute("UPDATE semantic_memory SET embedding_json=? WHERE id=?", (json.dumps(ms._get_embedding(lesson)), row_id))
                count += 1
        set_setting("embedding_model", new_model_name)
        return count
    except Exception as e:
        print(f"   ❌ Re-embedding failed: {e}")
        return 0
