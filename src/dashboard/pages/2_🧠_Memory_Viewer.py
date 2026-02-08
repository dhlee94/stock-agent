import streamlit as st
import pandas as pd
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from database import get_connection

st.set_page_config(page_title="Memory Viewer", page_icon="🧠", layout="wide")
st.title("🧠 Memory Viewer")

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
