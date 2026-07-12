import streamlit as st
import pandas as pd
import calendar
from datetime import datetime
import requests
import json

# ==========================================
# データベース (Google Apps Script API) の設定
# ==========================================
# ★ここに先ほどコピーしたウェブアプリのURLを貼り付けてください★
API_URL = "https://script.google.com/macros/s/AKfycbyAxc9_7fBomIZz49IGI2kwCVokqHTZ2DtNt8HVeTR2SHbJwt2jszDdYLPAPltxfYLn/exec"

def load_staff():
    """API経由でスプレッドシートからスタッフデータを読み込む"""
    try:
        response = requests.get(f"{API_URL}?sheet=staff")
        data = response.json()
        
        if not data or isinstance(data, dict) and "error" in data:
            df = pd.DataFrame(columns=["名前", "表示名", "運転可否", "希望休", "暗証番号", "雇用形態", "基本勤務"])
        else:
            df = pd.DataFrame(data)
            
        if "表示名" not in df.columns: df["表示名"] = df["名前"]
        if "希望休" not in df.columns: df["希望休"] = ""
        if "暗証番号" not in df.columns: df["暗証番号"] = "0000"
        if "雇用形態" not in df.columns: df["雇用形態"] = "常勤"
        if "基本勤務" not in df.columns: df["基本勤務"] = "通常"
            
        df["希望休"] = df["希望休"].fillna("").astype(str).replace('nan', '')
        df["暗証番号"] = df["暗証番号"].fillna("0000").astype(str).replace('nan', '0000').apply(lambda x: str(x).split('.')[0])
        
        return df
    except Exception as e:
        st.error("データの読み込みに失敗しました。URLが正しいか確認してください。")
        return pd.DataFrame(columns=["名前", "表示名", "運転可否", "希望休", "暗証番号"])

def save_staff(df):
    """API経由でスプレッドシートにスタッフデータを保存（上書き）する"""
    try:
        data = df.to_dict(orient="records")
        requests.post(f"{API_URL}?sheet=staff", json=data)
    except Exception as e:
        st.error("データの保存に失敗しました。")

# ==========================================
# 画面UIの設定
# ==========================================
st.set_page_config(page_title="希望休 入力フォーム", layout="centered")

# --- 最小限のCSS (余計なメニュー非表示のみ。色はシステムに任せる) ---
hide_menu_css = """
<style>
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    footer {visibility: hidden;}
</style>
"""
st.markdown(hide_menu_css, unsafe_allow_html=True)

st.title("希望休 入力フォーム")
st.markdown("---")

# --- データの読み込み ---
if 'staff_data' not in st.session_state:
    st.session_state.staff_data = load_staff()

staff_display_list = st.session_state.staff_data["表示名"].dropna().tolist()

if not staff_display_list:
    st.warning("現在、登録されているスタッフがいません。管理画面から登録してください。")
    st.stop()

if 'logged_in_staff' not in st.session_state:
    st.session_state.logged_in_staff = None

# ==========================================
# ログイン画面
# ==========================================
if st.session_state.logged_in_staff is None:
    st.subheader("ログイン")
    st.write("リストからアカウント名を選択し、暗証番号を入力してください。")
    
    with st.container(border=True):
        selected_display_name = st.selectbox("アカウント名 (表示名)", staff_display_list)
        entered_pin = st.text_input("暗証番号", type="password", help="初期パスワードは 0000 です")
        
        if st.button("ログインする", type="primary", use_container_width=True):
            staff_row = st.session_state.staff_data[st.session_state.staff_data["表示名"] == selected_display_name].iloc[0]
            correct_pin = str(staff_row.get("暗証番号", "0000")).strip()
            
            if entered_pin.strip() == correct_pin:
                st.session_state.logged_in_staff = staff_row["名前"]
                st.success("ログインしました。")
                st.rerun()
            else:
                st.error("暗証番号が違います。")
    st.stop()

# ==========================================
# メインの入力エリア (ログイン成功後)
# ==========================================
selected_staff_name = st.session_state.logged_in_staff
selected_staff_idx = st.session_state.staff_data[st.session_state.staff_data["名前"] == selected_staff_name].index[0]
display_name = st.session_state.staff_data.at[selected_staff_idx, "表示名"]

col_user, col_logout = st.columns([3, 1])
with col_user:
    st.write(f"**{display_name}** さん、お疲れ様です。")
with col_logout:
    if st.button("ログアウト", use_container_width=True):
        st.session_state.logged_in_staff = None
        st.rerun()

with st.expander("暗証番号の変更はこちら"):
    st.write("セキュリティのため、初期パスワード(0000)から自分専用の番号に変更してください。")
    new_pin = st.text_input("新しい暗証番号", type="password")
    new_pin_confirm = st.text_input("新しい暗証番号 (確認用)", type="password")
    if st.button("暗証番号を更新する", use_container_width=True):
        if new_pin and new_pin == new_pin_confirm:
            st.session_state.staff_data.at[selected_staff_idx, "暗証番号"] = str(new_pin)
            save_staff(st.session_state.staff_data)
            st.success("暗証番号を変更しました。次回から新しい番号をご利用ください。")
        elif new_pin != new_pin_confirm:
            st.error("確認用の番号が一致しません。")
        else:
            st.warning("新しい暗証番号を入力してください。")

st.markdown("<br>", unsafe_allow_html=True)
st.write("来月のシフトの希望休を入力してください。")

st.subheader("1. 対象の年月を確認")
now = datetime.now()
default_y = now.year + 1 if now.month == 12 else now.year
default_m = 1 if now.month == 12 else now.month + 1

col_y, col_m = st.columns(2)
with col_y:
    target_year = st.number_input("年", min_value=2024, max_value=2030, value=default_y)
with col_m:
    target_month = st.number_input("月", min_value=1, max_value=12, value=default_m)

req_col = f"希望休_{target_year}_{target_month:02d}"
if req_col not in st.session_state.staff_data.columns:
    st.session_state.staff_data[req_col] = ""

st.markdown("<br>", unsafe_allow_html=True)

st.subheader("2. 休みたい日を選択")
st.info(f"{target_month}月の希望休を選んでください。ボタンをタップするたびに「全休」→「半休」→「取消」と切り替わります。")

first_weekday, num_days = calendar.monthrange(target_year, target_month)

def toggle_leave(staff_idx, day, req_col):
    existing_req = str(st.session_state.staff_data.at[staff_idx, req_col])
    req_dict = {}
    if existing_req and existing_req != "nan":
        for item in existing_req.split(","):
            item = item.strip()
            if item:
                num = ''.join(filter(str.isdigit, item))
                typ = '半' if '半' in item else '全'
                if num: req_dict[int(num)] = typ
                
    current_state = req_dict.get(day)
    if current_state is None:
        req_dict[day] = '全'
    elif current_state == '全':
        req_dict[day] = '半'
    else:
        del req_dict[day]
        
    new_reqs = []
    for d in sorted(req_dict.keys()):
        new_reqs.append(f"{d}{req_dict[d]}")
    st.session_state.staff_data.at[staff_idx, req_col] = ",".join(new_reqs)

existing_req = str(st.session_state.staff_data.at[selected_staff_idx, req_col])
req_dict = {}
if existing_req and existing_req != "nan":
    for item in existing_req.split(","):
        item = item.strip()
        if item:
            num = ''.join(filter(str.isdigit, item))
            typ = '半' if '半' in item else '全'
            if num: req_dict[int(num)] = typ

weekdays = ["月", "火", "水", "木", "金", "土", "日"]
header_cols = st.columns(7)
for i, w in enumerate(weekdays):
    color = "#ef4444" if i == 6 else "#3b82f6" if i == 5 else "#888888"
    header_cols[i].markdown(f"<div style='text-align: center; color: {color}; font-weight: bold;'>{w}</div>", unsafe_allow_html=True)

st.markdown("<hr style='margin: 12px 0;'>", unsafe_allow_html=True)

day_counter = 1
for week in range(6):
    if day_counter > num_days:
        break
    cal_cols = st.columns(7)
    for i in range(7):
        if week == 0 and i < first_weekday:
            cal_cols[i].write("") 
        elif day_counter > num_days:
            cal_cols[i].write("") 
        else:
            current_state = req_dict.get(day_counter)
            if current_state == '全':
                btn_label = f"{day_counter} (全休)"
                btn_type = "primary"
            elif current_state == '半':
                btn_label = f"{day_counter} (半休)"
                btn_type = "primary"
            else:
                btn_label = f"{day_counter}"
                btn_type = "secondary"
                
            cal_cols[i].button(btn_label, key=f"btn_{day_counter}", type=btn_type, on_click=toggle_leave, args=(selected_staff_idx, day_counter, req_col), use_container_width=True)
            day_counter += 1
    st.markdown("<hr style='margin: 8px 0;'>", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

st.subheader("3. データの送信")

if st.button("希望休を確定して送信する", type="primary", use_container_width=True):
    with st.spinner('データを保存しています...'):
        save_staff(st.session_state.staff_data)
        st.success(f"{display_name} さんの希望休を送信しました。")
