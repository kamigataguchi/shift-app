import streamlit as st
import pandas as pd
import calendar
from datetime import datetime
import requests

# ==========================================
# データベース (Google Apps Script API) の設定
# ==========================================
API_URL = "https://shift-app-l4al6dez6gehirrv7y9dc3.streamlit.app/"

def api_request(sheet_name, method="GET", data=None):
    try:
        if method == "GET":
            res = requests.get(f"{API_URL}?sheet={sheet_name}")
            return res.json()
        elif method == "POST":
            requests.post(f"{API_URL}?sheet={sheet_name}", json=data)
            return True
    except:
        return None

def load_staff():
    data = api_request("staff")
    if not data or isinstance(data, dict) and "error" in data:
        df = pd.DataFrame(columns=["名前", "表示名", "暗証番号"])
    else:
        df = pd.DataFrame(data)
    if "表示名" not in df.columns: df["表示名"] = df["名前"]
    if "暗証番号" not in df.columns: df["暗証番号"] = "0000"
    df["暗証番号"] = df["暗証番号"].fillna("0000").astype(str).replace('nan', '0000').apply(lambda x: str(x).split('.')[0])
    return df

def save_staff(df): api_request("staff", "POST", df.to_dict(orient="records"))

def load_shift_names():
    data = api_request("shift_types")
    if data and not (isinstance(data, dict) and "error" in data):
        return [row["シフト名"] for row in data if "シフト名" in row]
    return ["日勤", "早出", "遅出", "午前半休", "午後半休", "全休"]

# --- UI設定 ---
st.set_page_config(page_title="シフト希望 入力", layout="centered")
st.markdown("""
<style>
    #MainMenu {visibility: hidden;} header {visibility: hidden;} footer {visibility: hidden;}
    .stButton > button { border-radius: 8px; font-family: 'Helvetica Neue', Arial, sans-serif; }
</style>
""", unsafe_allow_html=True)

st.title("シフト希望 入力フォーム")
st.markdown("---")

if 'staff_data' not in st.session_state: st.session_state.staff_data = load_staff()
if 'shift_names' not in st.session_state: st.session_state.shift_names = load_shift_names()

staff_display_list = st.session_state.staff_data["表示名"].dropna().tolist()

if not staff_display_list:
    st.warning("現在登録されているスタッフがいません。")
    st.stop()

if 'logged_in_staff' not in st.session_state: st.session_state.logged_in_staff = None

# --- ログイン ---
if st.session_state.logged_in_staff is None:
    st.write("アカウントを選択し、暗証番号を入力してください。")
    with st.container(border=True):
        selected_display_name = st.selectbox("アカウント名", staff_display_list)
        entered_pin = st.text_input("暗証番号 (初期: 0000)", type="password")
        if st.button("ログイン", type="primary", use_container_width=True):
            staff_row = st.session_state.staff_data[st.session_state.staff_data["表示名"] == selected_display_name].iloc[0]
            if entered_pin.strip() == str(staff_row.get("暗証番号", "0000")).strip():
                st.session_state.logged_in_staff = staff_row["名前"]
                st.rerun()
            else: st.error("暗証番号が違います。")
    st.stop()

# --- メイン画面 ---
selected_staff_name = st.session_state.logged_in_staff
selected_staff_idx = st.session_state.staff_data[st.session_state.staff_data["名前"] == selected_staff_name].index[0]
display_name = st.session_state.staff_data.at[selected_staff_idx, "表示名"]

col1, col2 = st.columns([3, 1])
col1.write(f"**{display_name}** さん、お疲れ様です。")
if col2.button("ログアウト", use_container_width=True):
    st.session_state.logged_in_staff = None
    st.rerun()

# 対象月の決定
now = datetime.now()
target_year = st.number_input("年", min_value=2024, max_value=2030, value=now.year + 1 if now.month == 12 else now.year)
target_month = st.number_input("月", min_value=1, max_value=12, value=1 if now.month == 12 else now.month + 1)
req_col = f"希望休_{target_year}_{target_month:02d}"

if req_col not in st.session_state.staff_data.columns:
    st.session_state.staff_data[req_col] = ""

# 現在の希望データを辞書にパース (書式: "1:全休, 2:早出")
existing_req = str(st.session_state.staff_data.at[selected_staff_idx, req_col])
req_dict = {}
if existing_req and existing_req != "nan":
    for item in existing_req.split(","):
        if ":" in item:
            d_str, s_name = item.split(":")
            if d_str.strip().isdigit(): req_dict[int(d_str.strip())] = s_name.strip()

# --- ダイアログ関数 (小窓) ---
@st.dialog("シフト希望の選択")
def select_shift_dialog(day):
    st.write(f"**{target_month}月 {day}日** の希望を選択してください。")
    current_val = req_dict.get(day, "(希望なし)")
    options = ["(希望なし)"] + st.session_state.shift_names
    idx = options.index(current_val) if current_val in options else 0
    
    selected = st.selectbox("シフト種類", options, index=idx)
    
    if st.button("決定する", type="primary", use_container_width=True):
        if selected == "(希望なし)":
            if day in req_dict: del req_dict[day]
        else:
            req_dict[day] = selected
            
        new_reqs = [f"{d}:{s}" for d, s in req_dict.items()]
        st.session_state.staff_data.at[selected_staff_idx, req_col] = ",".join(new_reqs)
        st.rerun()

# --- カレンダー描画 ---
st.markdown("<br><b>日付をタップして希望を選択してください。</b>", unsafe_allow_html=True)
first_weekday, num_days = calendar.monthrange(target_year, target_month)
weekdays = ["月", "火", "水", "木", "金", "土", "日"]

header_cols = st.columns(7)
for i, w in enumerate(weekdays):
    color = "#ef4444" if i == 6 else "#3b82f6" if i == 5 else "#64748b"
    header_cols[i].markdown(f"<div style='text-align: center; color: {color}; font-weight: bold; font-size: 14px;'>{w}</div>", unsafe_allow_html=True)

day_counter = 1
for week in range(6):
    if day_counter > num_days: break
    cal_cols = st.columns(7)
    for i in range(7):
        if week == 0 and i < first_weekday or day_counter > num_days:
            cal_cols[i].write("")
        else:
            current_req = req_dict.get(day_counter)
            label = f"{day_counter} ({current_req})" if current_req else str(day_counter)
            
            if cal_cols[i].button(label, key=f"btn_{day_counter}", use_container_width=True):
                select_shift_dialog(day_counter)
                
            day_counter += 1

st.markdown("<br>", unsafe_allow_html=True)
if st.button("希望データを保存して送信する", type="primary", use_container_width=True):
    with st.spinner('保存しています...'):
        save_staff(st.session_state.staff_data)
        st.success(f"{display_name} さんの希望を送信しました！")
