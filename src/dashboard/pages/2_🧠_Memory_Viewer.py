import streamlit as st
import pandas as pd
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from database import get_connection

st.set_page_config(page_title="Memory Viewer", page_icon="🧠", layout="wide")
st.title("🧠 Memory Viewer")

import plotly.express as px

# Activity Chart
with get_connection() as conn:
    try:
        activity = pd.read_sql("""
            SELECT date(created_at) as date, tool_name, COUNT(*) as count 
            FROM procedural_memory 
            GROUP BY date, tool_name
            ORDER BY date DESC
            LIMIT 50
        """, conn)
        
        if not activity.empty:
            st.caption("Recent Tool Activity")
            fig = px.bar(activity, x='date', y='count', color='tool_name')
            fig.update_layout(margin=dict(t=0, b=0, l=0, r=0), height=300)
            st.plotly_chart(fig, use_container_width=True)
    except Exception:
        pass

tab1, tab2 = st.tabs(["Driver Memory", "Procedural Memory"])

with tab1:
    st.subheader("Driver Insights (Volatility Factors)")
    
    search_term = st.text_input("Search Ticker or Keyword", "")
    
    with get_connection() as conn:
        query = "SELECT * FROM driver_memory ORDER BY created_at DESC"
        if search_term:
            query = f"SELECT * FROM driver_memory WHERE ticker LIKE '%{search_term}%' OR description LIKE '%{search_term}%' ORDER BY created_at DESC"
            
        df = pd.read_sql(query, conn)
        st.dataframe(df, use_container_width=True)

with tab2:
    st.subheader("Tool Execution History")
    
    with get_connection() as conn:
        df = pd.read_sql("SELECT * FROM procedural_memory ORDER BY created_at DESC LIMIT 100", conn)
        st.dataframe(df, use_container_width=True)
