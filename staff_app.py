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
API_URL = "https://docs.google.com/spreadsheets/d/1Znp7UMU0FM-I4ekq5rN34w_c0IFI10438xxXjWSE5IU/edit?gid=345720078#gid=345720078"

def load_staff():
    """API経由でスプレッドシートからスタッフデータを読み込む"""
    try:
        response = requests.get(f"{API_URL}?sheet=staff")
        data = response.json()
        
        if not data or isinstance(data, dict) and "error" in data:
            df = pd.DataFrame(columns=["名前", "表示名", "運転可否", "希望休", "暗証番号"])
        else:
            df = pd.DataFrame(data)
            
        if "表示名" not in df.columns: df["表示名"] = df["名前"]
        if "希望休" not in df.columns: df["希望休"] = ""
        if "暗証番号" not in df.columns: df["暗証番号"] = "0000"
            
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
st.set_page_config(page_title="希望休 入力フォーム", page_icon="📅", layout="centered")

# --- 余計なメニューやアイコンを消すCSS ---
hide_streamlit_style = """
<style>
#MainMenu {visibility: hidden;}
header {visibility: hidden;}
footer {visibility: hidden;}
</style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

st.title("📅 希望休 入力フォーム")
st.markdown("---")

# --- データの読み込み ---
if 'staff_data' not in st.session_state:
    st.session_state.staff_data = load_staff()

# ★リストに出すのは「表示名（偽名・イニシャル等）」のみ
staff_display_list = st.session_state.staff_data["表示名"].dropna().tolist()

if not staff_display_list:
    st.warning("現在、登録されているスタッフがいません。管理画面から登録してください。")
    st.stop()

# ログイン状態の管理
if 'logged_in_staff' not in st.session_state:
    st.session_state.logged_in_staff = None

# ==========================================
# ログイン画面
# ==========================================
if st.session_state.logged_in_staff is None:
    st.subheader("🔑 ログイン")
    st.write("リストからあなたのアカウント名を選択し、暗証番号を入力してください。")
    
    with st.container(border=True):
        # ★選択させるのは「表示名」
        selected_display_name = st.selectbox("アカウント名 (表示名)", staff_display_list)
        entered_pin = st.text_input("暗証番号", type="password", help="初期パスワードは 0000 です")
        
        if st.button("ログインする", type="primary", use_container_width=True):
            # 表示名から該当する行を探す
            staff_row = st.session_state.staff_data[st.session_state.staff_data["表示名"] == selected_display_name].iloc[0]
            correct_pin = str(staff_row.get("暗証番号", "0000")).strip()
            
            if entered_pin.strip() == correct_pin:
                # ログイン成功時は「本名」をセッションに保持しておく（裏側の処理用）
                st.session_state.logged_in_staff = staff_row["名前"]
                st.success("ログインしました！")
                st.rerun()
            else:
                st.error("❌ 暗証番号が違います。")
    st.stop()

# ==========================================
# メインの入力エリア (ログイン成功後)
# ==========================================
# 処理には本名とインデックスを使う
selected_staff_name = st.session_state.logged_in_staff
selected_staff_idx = st.session_state.staff_data[st.session_state.staff_data["名前"] == selected_staff_name].index[0]
# 画面に表示するのは表示名
display_name = st.session_state.staff_data.at[selected_staff_idx, "表示名"]

col_user, col_logout = st.columns([3, 1])
with col_user:
    st.write(f"👤 **{display_name}** さん、お疲れ様です。")
with col_logout:
    if st.button("ログアウト", use_container_width=True):
        st.session_state.logged_in_staff = None
        st.rerun()

# --- 暗証番号変更機能 ---
with st.expander("🔑 暗証番号の変更はこちら"):
    st.write("セキュリティのため、初期パスワード(0000)から自分専用の番号に変更してください。")
    new_pin = st.text_input("新しい暗証番号", type="password")
    new_pin_confirm = st.text_input("新しい暗証番号 (確認用)", type="password")
    if st.button("暗証番号を更新する", use_container_width=True):
        if new_pin and new_pin == new_pin_confirm:
            st.session_state.staff_data.at[selected_staff_idx, "暗証番号"] = str(new_pin)
            save_staff(st.session_state.staff_data)
            st.success("✅ 暗証番号を変更しました！次回から新しい番号をご利用ください。")
        elif new_pin != new_pin_confirm:
            st.error("❌ 確認用の番号が一致しません。")
        else:
            st.warning("⚠️ 新しい暗証番号を入力してください。")

st.markdown("<br>", unsafe_allow_html=True)
st.write("来月のシフトの希望休を入力してください。")

# 対象月を選ぶ
st.subheader("1. 対象の年月を確認")
now = datetime.now()
default_y = now.year + 1 if now.month == 12 else now.year
default_m = 1 if now.month == 12 else now.month + 1

col_y, col_m = st.columns(2)
with col_y:
    target_year = st.number_input("年", min_value=2024, max_value=2030, value=default_y)
with col_m:
    target_month = st.number_input("月", min_value=1, max_value=12, value=default_m)

st.markdown("<br>", unsafe_allow_html=True)

st.subheader("2. 休みたい日をチェック")
st.info(f"💡 {target_month}月の希望休にチェックを入れてください。")

first_weekday, num_days = calendar.monthrange(target_year, target_month)

def toggle_leave(staff_idx, day, widget_key):
    is_active = st.session_state[widget_key]
    existing_req = str(st.session_state.staff_data.at[staff_idx, "希望休"])
    days = []
    if existing_req and existing_req != "nan":
        req_str = existing_req.translate(str.maketrans('０１２３４５６７８９，、', '0123456789,,'))
        days = [int(x.strip()) for x in req_str.split(",") if x.strip().isdigit()]
    
    if is_active and day not in days:
        days.append(day)
    elif not is_active and day in days:
        days.remove(day)
        
    days.sort()
    st.session_state.staff_data.at[staff_idx, "希望休"] = ",".join(map(str, days))

existing_req = str(st.session_state.staff_data.at[selected_staff_idx, "希望休"])
selected_days = []
if existing_req and existing_req != "nan":
    req_str = existing_req.translate(str.maketrans('０１２３４５６７８９，、', '0123456789,,'))
    selected_days = [int(x.strip()) for x in req_str.split(",") if x.strip().isdigit()]

st.markdown("<div style='background-color:#ffffff; padding:15px; border-radius:10px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);'>", unsafe_allow_html=True)
weekdays = ["月", "火", "水", "木", "金", "土", "日"]
header_cols = st.columns(7)
for i, w in enumerate(weekdays):
    color = "red" if i == 6 else "blue" if i == 5 else "black"
    header_cols[i].markdown(f"<div style='text-align: center; color: {color}; font-weight: bold; font-size: 14px;'>{w}</div>", unsafe_allow_html=True)

st.markdown("<hr style='margin: 10px 0;'>", unsafe_allow_html=True)

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
            is_checked = day_counter in selected_days
            w_key = f"staff_cal_{selected_staff_idx}_{target_year}_{target_month}_{day_counter}"
            cal_cols[i].checkbox(f"{day_counter}", value=is_checked, key=w_key, on_change=toggle_leave, args=(selected_staff_idx, day_counter, w_key))
            day_counter += 1
    st.markdown("<hr style='margin: 5px 0; border: none; border-bottom: 1px dashed #eee;'>", unsafe_allow_html=True)
st.markdown("</div>", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ==========================================
# 保存ボタン
# ==========================================
st.subheader("3. 最後に送信ボタンを押す")

if st.button("📤 希望休を確定して送信する", type="primary", use_container_width=True):
    with st.spinner('データベース(スプレッドシート)へ保存中...'):
        save_staff(st.session_state.staff_data)
        st.success(f"✅ {display_name} さんの希望休を送信しました！お疲れ様でした。")
        st.balloons()
