import streamlit as st
import pandas as pd
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from database import get_connection, set_setting, get_all_settings

st.set_page_config(page_title="Settings", page_icon="⚙️", layout="wide")
st.title("⚙️ Agent Configuration")

st.markdown("Adjust the agent's behavior parameters here. Changes take effect on the next agent run.")

# Fetch current settings
settings = get_all_settings()
# Convert to dict for easier access
current_config = {item['key']: item for item in settings}

# Form for standard settings
with st.form("settings_form"):
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("General Parameters")
        
        # Risk Tolerance
        risk_val = current_config.get('risk_tolerance', {}).get('value', 'Medium')
        new_risk = st.selectbox("Risk Tolerance", ["Low", "Medium", "High"], index=["Low", "Medium", "High"].index(risk_val) if risk_val in ["Low", "Medium", "High"] else 1)
        
        # Search Depth
        depth_val = current_config.get('search_depth', {}).get('value', '3')
        new_depth = st.number_input("Search Depth (1-10)", min_value=1, max_value=10, value=int(depth_val) if depth_val.isdigit() else 3)
        
    with col2:
        st.subheader("Analysis Parameters")
        # Target Market
        market_val = current_config.get('default_market', {}).get('value', 'KR')
        new_market = st.selectbox("Default Market", ["KR", "US"], index=0 if market_val == 'KR' else 1)
        
        # Data Window
        window_val = current_config.get('analysis_window_days', {}).get('value', '30')
        new_window = st.number_input("Analysis Window (Days)", min_value=7, max_value=365, value=int(window_val) if window_val.isdigit() else 30)

    submitted = st.form_submit_button("Save Settings")
    if submitted:
        set_setting('risk_tolerance', new_risk, "Risk tolerance level for portfolio suggestions")
        set_setting('search_depth', str(new_depth), "Depth of search steps in planner")
        set_setting('default_market', new_market, "Default target market for analysis")
        set_setting('analysis_window_days', str(new_window), "Lookback period for technical analysis")
        
        st.success("Settings saved successfully!")
        st.snow()

# Advanced: Raw Settings Editor
st.divider()
st.subheader("Advanced Configuration (Raw Editor)")

with get_connection() as conn:
    df = pd.read_sql("SELECT * FROM settings", conn)
    edited_df = st.data_editor(df, num_rows="dynamic", key="settings_editor", use_container_width=True)
    
    if st.button("Save Raw Changes"):
        try:
             for index, row in edited_df.iterrows():
                 conn.execute(
                     "INSERT OR REPLACE INTO settings (key, value, description, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
                     (row['key'], row['value'], row['description'])
                 )
             conn.commit()
             st.success("Advanced settings updated!")
        except Exception as e:
            st.error(f"Error saving: {e}")
