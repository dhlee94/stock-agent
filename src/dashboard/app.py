import streamlit as st
import sys
import os
import pandas as pd

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database import get_connection, get_tool_stats

st.set_page_config(
    page_title="Memento Agent Dashboard",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS
st.markdown("""
<style>
    .stApp {
        background-color: #0e1117;
    }
    .metric-card {
        background-color: #262730;
        border: 1px solid #464b5f;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 2px 2px 10px rgba(0,0,0,0.3);
        text-align: center;
        transition: transform 0.2s;
    }
    .metric-card:hover {
        transform: translateY(-5px);
        border-color: #ff4b4b;
    }
    .metric-label {
        font-size: 14px;
        color: #babcbf;
        margin-bottom: 5px;
    }
    .metric-value {
        font-size: 32px;
        font-weight: bold;
        color: #ffffff;
    }
    .stDataFrame {
        border: 1px solid #464b5f;
        border-radius: 5px;
    }
</style>
""", unsafe_allow_html=True)

st.title("🧠 Memento Agent Dashboard")

st.markdown("""
Welcome to the **Memento Agent** control center.
Use the sidebar to navigate between data management, memory inspection, and configuration.
""")

st.markdown("---")

# Quick Stats
col1, col2, col3 = st.columns(3)

with get_connection() as conn:
    # Ticker Count
    ticker_count = conn.execute("SELECT COUNT(*) FROM tickers").fetchone()[0]
    col1.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">Tracked Tickers</div>
        <div class="metric-value">{ticker_count}</div>
        <div>📈 Stocks</div>
    </div>
    """, unsafe_allow_html=True)
    
    # Driver Insights
    driver_count = conn.execute("SELECT COUNT(*) FROM driver_memory").fetchone()[0]
    col2.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">Driver Insights</div>
        <div class="metric-value">{driver_count}</div>
        <div>💡 Knowledge Points</div>
    </div>
    """, unsafe_allow_html=True)
    
    # Tool Executions
    tool_count = conn.execute("SELECT COUNT(*) FROM procedural_memory").fetchone()[0]
    col3.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">Tool Executions</div>
        <div class="metric-value">{tool_count}</div>
        <div>⚙️ Actions Taken</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("---")

# Tool Usage Overview
st.subheader("Tool Usage Statistics")
stats = get_tool_stats()
if stats:
    df_stats = pd.DataFrame(stats)
    st.dataframe(df_stats, use_container_width=True)
else:
    st.info("No tool usage data available yet.")

st.markdown("---")
st.caption("v1.0.0 | Mobile Friendly | SQLite Backend")
