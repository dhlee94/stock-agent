import streamlit as st
import sys
import os
import pandas as pd

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database import get_connection, get_tool_stats

st.set_page_config(
    page_title="Memento 에이전트 대시보드",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }
    
    .stApp {
        background-color: #0e1117;
    }
    
    /* Metrics Card Styling */
    .metric-card {
        background-color: #262730;
        border: 1px solid #464b5f;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        text-align: center;
        transition: all 0.3s ease;
    }
    .metric-card:hover {
        transform: translateY(-5px);
        box-shadow: 0 8px 15px rgba(0,0,0,0.2);
        border-color: #ff4b4b;
    }
    .metric-label {
        font-size: 14px;
        font-weight: 600;
        color: #babcbf;
        margin-bottom: 8px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .metric-value {
        font-size: 36px;
        font-weight: 700;
        color: #ffffff;
        margin-bottom: 4px;
    }
    .metric-icon {
        font-size: 20px;
        margin-top: 10px;
        opacity: 0.8;
    }
    
    /* DataFrame Styling */
    .stDataFrame {
        border: 1px solid #464b5f;
        border-radius: 5px;
        overflow: hidden;
    }

    /* Mobile Responsiveness */
    @media (max-width: 768px) {
        .metric-card {
            padding: 15px;
            margin-bottom: 10px;
        }
        .metric-value {
            font-size: 28px;
        }
        .metric-label {
            font-size: 12px;
        }
        h1 {
            font-size: 24px !important;
        }
    }
</style>
""", unsafe_allow_html=True)

st.title("🧠 Memento 에이전트 대시보드")

st.markdown("""
**Memento 에이전트** 제어 센터입니다.  
사이드바에서 데이터 관리, 메모리 조회, 설정 화면으로 이동할 수 있습니다.
""")

st.markdown("---")

# Quick Stats
col1, col2, col3 = st.columns(3)

with get_connection() as conn:
    # Ticker Count
    ticker_count = conn.execute("SELECT COUNT(*) FROM tickers").fetchone()[0]
    col1.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">추적 중인 종목 수</div>
        <div class="metric-value">{ticker_count}</div>
        <div>📈 종목</div>
    </div>
    """, unsafe_allow_html=True)
    
    # Driver Insights
    driver_count = conn.execute("SELECT COUNT(*) FROM driver_memory").fetchone()[0]
    col2.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">드라이버 인사이트</div>
        <div class="metric-value">{driver_count}</div>
        <div>💡 지식 포인트</div>
    </div>
    """, unsafe_allow_html=True)
    
    # Tool Executions
    tool_count = conn.execute("SELECT COUNT(*) FROM procedural_memory").fetchone()[0]
    col3.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">도구 실행 횟수</div>
        <div class="metric-value">{tool_count}</div>
        <div>⚙️ 실행된 액션</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("---")

# Tool Usage Overview
st.subheader("도구 사용 통계")
stats = get_tool_stats()
if stats:
    df_stats = pd.DataFrame(stats)
    st.dataframe(df_stats, use_container_width=True)
else:
    st.info("아직 도구 사용 이력이 없습니다.")

st.markdown("---")
st.caption("v1.0.0 | 모바일 대응 | SQLite 기반 백엔드")
