"""
SQLite Database Module for Memento Agent

Centralized data management for:
- Sector/Ticker information
- Driver Memory (price impact factors)
- Procedural Memory (tool execution history)
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
    # Add timeout to handle 'database is locked' during concurrent writes
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    # Enable WAL mode for better concurrency
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
        
        # Sector competitors (for quick lookup)
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
        
        # Settings table for dashboard configuration
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                description TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Episodic memory (trajectories)
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
        
        # Semantic memory (generalized lessons)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS semantic_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lesson TEXT UNIQUE,
                source_task TEXT,
                embedding_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Prediction log — 5-day direction forecast tracking for Planner feedback
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS prediction_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                market TEXT NOT NULL,
                context_period TEXT,
                forecast_steps INTEGER,
                predicted_at TEXT NOT NULL,
                target_date TEXT NOT NULL,
                current_price REAL,
                predicted_direction TEXT,
                predicted_pct REAL,
                actual_price REAL,
                actual_direction TEXT,
                correct INTEGER,
                evaluated_at TEXT,
                model TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_pred_ticker ON prediction_log(ticker)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_pred_target ON prediction_log(target_date)')

        # Create indexes
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_tickers_sector ON tickers(sector_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_driver_ticker ON driver_memory(ticker)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_proc_tool ON procedural_memory(tool_name)')

        print("✅ Database initialized successfully", file=__import__("sys").stderr)


# ============================================================
# SETTINGS OPERATIONS
# ============================================================

def get_setting(key: str, default: str = "") -> str:
    """Get a setting value."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
        row = cursor.fetchone()
        return row['value'] if row else default

def set_setting(key: str, value: str, description: str = ""):
    """Set a setting value."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO settings (key, value, description, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ''', (key, value, description))

def get_all_settings() -> List[Dict[str, Any]]:
    """Get all settings."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM settings ORDER BY key')
        return [dict(row) for row in cursor.fetchall()]



# ============================================================
# SECTOR & TICKER OPERATIONS
# ============================================================

def get_sector_competitors(ticker: str) -> List[str]:
    """Get competitors for a ticker."""
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
    """Get ticker information."""
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
    """Add or update a ticker."""
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
    """Add a driver memory entry."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO driver_memory (ticker, name, driver_type, description, impact_direction, confidence)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (ticker, name, driver_type, description, impact_direction, confidence))
        return cursor.lastrowid


def get_drivers(ticker: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Get driver memory for a ticker."""
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
    """Get top drivers grouped by type."""
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
    """Log a tool execution."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO procedural_memory (tool_name, args_json, result_summary, success, execution_time_ms)
            VALUES (?, ?, ?, ?, ?)
        ''', (tool_name, json.dumps(args, ensure_ascii=False), result_summary, int(success), execution_time_ms))
        return cursor.lastrowid


def get_tool_history(tool_name: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
    """Get tool execution history."""
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
    """Get tool execution statistics."""
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
# PREDICTION LOG OPERATIONS
# ============================================================

def save_prediction(ticker: str, market: str, context_period: str,
                    forecast_steps: int, predicted_at: str, target_date: str,
                    current_price: float, predicted_direction: str,
                    predicted_pct: float, model: str) -> int:
    """Save a forecast prediction for later evaluation."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO prediction_log
              (ticker, market, context_period, forecast_steps,
               predicted_at, target_date, current_price,
               predicted_direction, predicted_pct, model)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (ticker, market, context_period, forecast_steps,
              predicted_at, target_date, current_price,
              predicted_direction, predicted_pct, model))
        return cursor.lastrowid


def get_pending_predictions(as_of_date: str) -> List[Dict[str, Any]]:
    """Return predictions whose target_date has passed and haven't been evaluated."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM prediction_log
            WHERE target_date <= ? AND evaluated_at IS NULL
            ORDER BY target_date ASC
        ''', (as_of_date,))
        return [dict(r) for r in cursor.fetchall()]


def evaluate_prediction(pred_id: int, actual_price: float,
                        actual_direction: str, evaluated_at: str):
    """Fill in actual price / direction and set correct flag."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE prediction_log
            SET actual_price = ?,
                actual_direction = ?,
                correct = (CASE WHEN predicted_direction = ? THEN 1 ELSE 0 END),
                evaluated_at = ?
            WHERE id = ?
        ''', (actual_price, actual_direction, actual_direction, evaluated_at, pred_id))


def get_forecast_accuracy(ticker: str, min_samples: int = 3) -> List[Dict[str, Any]]:
    """Return direction accuracy grouped by context_period for a ticker."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT context_period,
                   COUNT(correct) AS total,
                   SUM(correct) AS hits,
                   ROUND(AVG(correct) * 100, 1) AS accuracy_pct
            FROM prediction_log
            WHERE ticker = ? AND evaluated_at IS NOT NULL AND correct IS NOT NULL
            GROUP BY context_period
            HAVING total >= ?
            ORDER BY accuracy_pct DESC
        ''', (ticker, min_samples))
        return [dict(r) for r in cursor.fetchall()]


def get_global_accuracy_summary(min_samples: int = 5) -> List[Dict[str, Any]]:
    """Return accuracy grouped by (market, context_period) across all tickers."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT market, context_period,
                   COUNT(correct) AS total,
                   ROUND(AVG(correct) * 100, 1) AS accuracy_pct
            FROM prediction_log
            WHERE evaluated_at IS NOT NULL AND correct IS NOT NULL
            GROUP BY market, context_period
            HAVING total >= ?
            ORDER BY market, accuracy_pct DESC
        ''', (min_samples,))
        return [dict(r) for r in cursor.fetchall()]

# Always run init_db on import — CREATE TABLE IF NOT EXISTS is idempotent,
# so existing DBs are safe; new tables added in upgrades get created too.
init_db()


def reembed_if_model_changed(new_model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2") -> int:
    """Re-embed episodic/semantic memory rows when the embedding model changes.

    Stores the active model name in a settings row. If it differs from
    new_model_name, all embedding_json fields are regenerated. Returns the
    number of rows re-embedded (0 when nothing changed).
    """
    current = get_setting("embedding_model", "")
    if current == new_model_name:
        return 0

    print(f"🔄 [DB] Embedding model changed ({current or 'none'} → {new_model_name}). Re-embedding memory...")

    try:
        import sys, os
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from memory_store import MemoryStore
        ms = MemoryStore()

        # Probe which model actually works — Gemini may rate-limit on batch calls
        probe = ms._get_embedding("probe")
        actual_dim = len(probe)
        # Infer actual model from embedding dimension
        _GEMINI_DIM  = 3072
        _OPENAI_DIM  = 1536
        _LOCAL_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
        if actual_dim == _GEMINI_DIM:
            actual_model = new_model_name          # Gemini worked
        elif actual_dim == _OPENAI_DIM:
            actual_model = new_model_name          # OpenAI worked
        else:
            actual_model = _LOCAL_MODEL            # fell back to local

        if actual_model != new_model_name:
            print(f"   ⚠️  {new_model_name} unavailable (dim={actual_dim}) — using {actual_model}")
            if actual_model == current:
                # 의도한 모델도 실패하고 이전과 동일한 폴백 모델이 사용됨.
                # 재임베딩 불필요 — 다음 시작 때 다시 시도.
                print(f"   ℹ️  Effective model unchanged ({actual_model}) — skipping re-embed")
                return 0

        count = 0
        with get_connection() as conn:
            read_cur = conn.cursor()
            write_cur = conn.cursor()

            read_cur.execute("SELECT id, task FROM episodic_memory")
            for row_id, task in read_cur.fetchall():
                write_cur.execute("UPDATE episodic_memory SET embedding_json=? WHERE id=?",
                                  (json.dumps(ms._get_embedding(task)), row_id))
                count += 1

            read_cur.execute("SELECT id, lesson FROM semantic_memory")
            for row_id, lesson in read_cur.fetchall():
                write_cur.execute("UPDATE semantic_memory SET embedding_json=? WHERE id=?",
                                  (json.dumps(ms._get_embedding(lesson)), row_id))
                count += 1

        set_setting("embedding_model", actual_model)
        print(f"   ✅ Re-embedded {count} rows with {actual_model}")
        return count

    except Exception as e:
        print(f"   ❌ Re-embedding failed: {e}")
        return 0
