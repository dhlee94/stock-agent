import streamlit as st
import pandas as pd
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from database import get_connection, set_setting, get_all_settings

st.set_page_config(page_title="설정", page_icon="⚙️", layout="wide")
st.title("⚙️ 에이전트 설정")

st.markdown("에이전트의 동작 파라미터를 여기에서 조정할 수 있습니다. 변경 사항은 다음 실행부터 적용됩니다.")

# Fetch current settings
settings = get_all_settings()
# Convert to dict for easier access
current_config = {item['key']: item for item in settings}

# Form for standard settings
with st.form("settings_form"):
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("일반 설정")
        
        # Risk Tolerance
        risk_val = current_config.get('risk_tolerance', {}).get('value', 'Medium')
        new_risk = st.selectbox(
            "리스크 허용도",
            ["Low", "Medium", "High"],
            index=["Low", "Medium", "High"].index(risk_val) if risk_val in ["Low", "Medium", "High"] else 1,
        )
        
        # Search Depth
        depth_val = current_config.get('search_depth', {}).get('value', '3')
        new_depth = st.number_input(
            "검색 깊이 (1-10단계)",
            min_value=1,
            max_value=10,
            value=int(depth_val) if depth_val.isdigit() else 3,
        )
        
    with col2:
        st.subheader("분석 설정")
        # Target Market
        market_val = current_config.get('default_market', {}).get('value', 'KR')
        new_market = st.selectbox(
            "기본 시장",
            ["KR", "US"],
            index=0 if market_val == 'KR' else 1,
        )
        
        # Data Window
        window_val = current_config.get('analysis_window_days', {}).get('value', '30')
        new_window = st.number_input(
            "분석 기간 (일)",
            min_value=7,
            max_value=365,
            value=int(window_val) if window_val.isdigit() else 30,
        )

    submitted = st.form_submit_button("설정 저장")
    if submitted:
        set_setting('risk_tolerance', new_risk, "포트폴리오 제안 시 기준이 되는 리스크 허용도")
        set_setting('search_depth', str(new_depth), "플래너가 탐색하는 단계 수")
        set_setting('default_market', new_market, "기본 분석 대상 시장")
        set_setting('analysis_window_days', str(new_window), "기술적 분석에 사용하는 과거 데이터 일수")
        
        st.success("설정이 성공적으로 저장되었습니다.")
        st.snow()

# Advanced: Raw Settings Editor
st.divider()
st.subheader("고급 설정 (Raw 편집기)")

with get_connection() as conn:
    df = pd.read_sql("SELECT * FROM settings", conn)
    edited_df = st.data_editor(df, num_rows="dynamic", key="settings_editor", use_container_width=True)
    
    if st.button("Raw 변경 사항 저장"):
        try:
             for index, row in edited_df.iterrows():
                 conn.execute(
                     "INSERT OR REPLACE INTO settings (key, value, description, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
                     (row['key'], row['value'], row['description'])
                 )
             conn.commit()
             st.success("고급 설정이 성공적으로 저장되었습니다.")
        except Exception as e:
            st.error(f"저장 중 오류가 발생했습니다: {e}")
