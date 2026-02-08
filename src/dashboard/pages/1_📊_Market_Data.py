import streamlit as st
import pandas as pd
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from database import get_connection

st.set_page_config(page_title="Market Data", page_icon="📊", layout="wide")
st.title("📊 Market Data Management")

import plotly.express as px

# Overview Chart
with get_connection() as conn:
    try:
        sector_counts = pd.read_sql("""
            SELECT s.name_kr, COUNT(t.ticker) as count 
            FROM sectors s 
            LEFT JOIN tickers t ON s.id = t.sector_id 
            GROUP BY s.name_kr
        """, conn)
        
        if not sector_counts.empty:
            st.caption("Sector Distribution")
            fig = px.pie(sector_counts, values='count', names='name_kr', hole=0.4)
            fig.update_layout(margin=dict(t=0, b=0, l=0, r=0), height=300)
            st.plotly_chart(fig, use_container_width=True)
    except Exception:
        pass

tab1, tab2, tab3 = st.tabs(["Tickers", "Sectors", "Competitors"])

with tab1:
    st.subheader("Manage Tickers")
    with get_connection() as conn:
        df = pd.read_sql("SELECT * FROM tickers", conn)
        
        edited_df = st.data_editor(
            df,
            num_rows="dynamic",
            key="ticker_editor",
            use_container_width=True
        )
        
        if st.button("Save Changes", key="save_tickers"):
            # Update changes to DB (Simplistic approach: deleteAll + insertAll for small data, or handle delta)
            # For robustness in this demo, accessing connection directly
            try:
                # Basic sync for updated rows
                 for index, row in edited_df.iterrows():
                     conn.execute(
                         "INSERT OR REPLACE INTO tickers (ticker, name, sector_id, market) VALUES (?, ?, ?, ?)",
                         (row['ticker'], row['name'], row['sector_id'], row['market'])
                     )
                 conn.commit()
                 st.success("Tickers updated successfully!")
            except Exception as e:
                st.error(f"Error saving: {e}")

with tab2:
    st.subheader("Manage Sectors")
    with get_connection() as conn:
        df = pd.read_sql("SELECT * FROM sectors", conn)
        edited_df = st.data_editor(df, num_rows="dynamic", key="sector_editor")
        
        if st.button("Save Changes", key="save_sectors"):
            try:
                 for index, row in edited_df.iterrows():
                     conn.execute(
                         "INSERT OR REPLACE INTO sectors (id, name_kr, name_en) VALUES (?, ?, ?)",
                         (row['id'], row['name_kr'], row['name_en'])
                     )
                 conn.commit()
                 st.success("Sectors updated successfully!")
            except Exception as e:
                st.error(f"Error saving: {e}")

with tab3:
    st.subheader("Competitor Relations")
    with get_connection() as conn:
        df = pd.read_sql("SELECT * FROM sector_competitors", conn)
        edited_df = st.data_editor(df, num_rows="dynamic", key="comp_editor")
        
        if st.button("Save Changes", key="save_comps"):
             try:
                 # It's cleaner to truncate and reload if full replace, but sticking to upsert
                 curr = conn.cursor()
                 for index, row in edited_df.iterrows():
                     curr.execute(
                         "INSERT OR IGNORE INTO sector_competitors (ticker, competitor_ticker) VALUES (?, ?)",
                         (row['ticker'], row['competitor_ticker'])
                     )
                 conn.commit()
                 st.success("Competitors updated successfully!")
             except Exception as e:
                st.error(f"Error saving: {e}")
