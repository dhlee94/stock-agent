import streamlit as st
import pandas as pd
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from database import get_connection

st.set_page_config(page_title="메모리 뷰어", page_icon="🧠", layout="wide")
st.title("🧠 메모리 뷰어")

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
            st.caption("최근 도구 활동 내역")
            fig = px.bar(activity, x='date', y='count', color='tool_name')
            fig.update_layout(margin=dict(t=0, b=0, l=0, r=0), height=300)
            st.plotly_chart(fig, use_container_width=True)
    except Exception:
        pass

tab1, tab2 = st.tabs(["드라이버 메모리", "절차 메모리"])

with tab1:
    st.subheader("드라이버 인사이트 (변동성 요인)")
    
    search_term = st.text_input("티커 또는 키워드 검색", "")
    
    with get_connection() as conn:
        query = "SELECT * FROM driver_memory ORDER BY created_at DESC"
        if search_term:
            query = f"SELECT * FROM driver_memory WHERE ticker LIKE '%{search_term}%' OR description LIKE '%{search_term}%' ORDER BY created_at DESC"
            
        df = pd.read_sql(query, conn)
        st.dataframe(df, use_container_width=True)

with tab2:
    st.subheader("도구 실행 이력")
    
    with get_connection() as conn:
        df = pd.read_sql("SELECT * FROM procedural_memory ORDER BY created_at DESC LIMIT 100", conn)
        st.dataframe(df, use_container_width=True)
