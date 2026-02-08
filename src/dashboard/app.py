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

st.title("🧠 Memento Agent Dashboard")

st.markdown("""
Welcome to the Memento Agent control center.
Use the sidebar to navigate between different management modules.
""")

# Quick Stats
col1, col2, col3 = st.columns(3)

with get_connection() as conn:
    # Ticker Count
    count = conn.execute("SELECT COUNT(*) FROM tickers").fetchone()[0]
    col1.metric("Tracked Tickers", count)
    
    # Driver Insights
    count = conn.execute("SELECT COUNT(*) FROM driver_memory").fetchone()[0]
    col2.metric("Driver Insights", count)
    
    # Tool Executions
    count = conn.execute("SELECT COUNT(*) FROM procedural_memory").fetchone()[0]
    col3.metric("Tool Executions", count)

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
