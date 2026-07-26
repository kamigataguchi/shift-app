import streamlit as st
import pandas as pd
import calendar
from datetime import datetime
import requests

# ==========================================
# データベース (Google Apps Script API) の設定
# ==========================================
# ※ app.py と同じURLを設定してください
API_URL = "https://script.google.com/macros/s/AKfycbyAxc9_7fBomIZz49IGI2kwCVokqHTZ2DtNt8HVeTR2SHbJwt2jszDdYLPAPltxfYLn/exec"

def api_request(sheet_name, method="GET", data=None, year=None, month=None):
    """Google Apps Script APIとの通信を行う関数 (年月キー対応)"""
    url = f"{API_URL}?sheet={sheet_name}"
    if year is not None and month is not None:
        url += f"&year={year}&month={month}"
        
    try:
        if method == "GET":
            res = requests.get(url)
            return res.json()
        elif method == "POST":
            payload = {
                "sheet": sheet_name,
                "data": data
            }
            if year is not None and month is not None:
                payload["year"] = year
                payload["month"] = month
            requests.post(API_URL, json=payload)
            return True
    except Exception as e:
        return None

def load_staff():
    """スタッフ情報の読み込み"""
    data = api_request("staff")
    if not data or (isinstance(data, dict) and "error" in data):
        df = pd.DataFrame(columns=["名前", "表示名", "暗証番号"])
    else:
        df = pd.DataFrame(data)
        
    if "表示名" not in df.columns: df["表示名"] = df.get("名前", "")
    if "暗証番号" not in df.columns: df["暗証番号"] = "0000"
    df["暗証番号"] = df["暗証番号"].fillna("0000").astype(str).replace(['nan', 'None'], '0000').apply(lambda x: str(x).split('.')[0])
    return df

def save_staff(df):
    """スタッフ情報の保存（希望休や暗証番号の更新）"""
    df_to_save = df.copy().fillna("")
    api_request("staff", method="POST", data=df_to_save.to_dict(orient="records"))

def load_shift_names():
    """管理者アプリ(app.py)のシフト種類を取得"""
    data = api_request("shift_type")
    if data and not (isinstance(data, dict) and "error" in data):
        return [row["シフト名"] for row in data if "シフト名" in row and str(row["シフト名"]).strip() != ""]
    # 取得失敗時はデイサービス向けのデフォルト値を利用
    return ["日勤", "午前半休", "午後半休", "公休"]

# --- UI設定 ---
st.set_page_config(page_title="スマホアプリ - シフト希望", layout="centered")
st.markdown("""
<style>
    .stButton > button { border-radius: 8px; font-weight: bold; }
    div[data-testid="stDialog"] { border-radius: 12px; }
</style>
""", unsafe_allow_html=True)

st.title("📱 職員用 シフトアプリ")

# --- 初期データロード ---
if 'staff_data' not in st.session_state: 
    st.session_state.staff_data = load_staff()
if 'shift_names' not in st.session_state: 
    st.session_state.shift_names = load_shift_names()
if 'logged_in_staff' not in st.session_state: 
    st.session_state.logged_in_staff = None

staff_display_list = st.session_state.staff_data["表示名"].dropna().tolist()

if not staff_display_list:
    st.warning("現在登録されているスタッフがいません。管理者に連絡してください。")
    st.stop()

# ==========================================
# ログイン画面
# ==========================================
if st.session_state.logged_in_staff is None:
    st.markdown("### ログイン")
    with st.container(border=True):
        selected_display_name = st.selectbox("アカウント名", staff_display_list)
        entered_pin = st.text_input("暗証番号 (初期設定: 0000)", type="password")
        
        if st.button("ログイン", type="primary", use_container_width=True):
            staff_row = st.session_state.staff_data[st.session_state.staff_data["表示名"] == selected_display_name].iloc[0]
            if entered_pin.strip() == str(staff_row.get("暗証番号", "0000")).strip():
                st.session_state.logged_in_staff = staff_row["名前"]
                st.rerun()
            else:
                st.error("暗証番号が違います。")
    st.stop()

# ==========================================
# ログイン後 メイン画面
# ==========================================
selected_staff_name = st.session_state.logged_in_staff
selected_staff_idx = st.session_state.staff_data[st.session_state.staff_data["名前"] == selected_staff_name].index[0]
display_name = st.session_state.staff_data.at[selected_staff_idx, "表示名"]

col_head1, col_head2 = st.columns([3, 1])
col_head1.write(f"👤 **{display_name}** さん、お疲れ様です。")
if col_head2.button("ログアウト", use_container_width=True):
    st.session_state.logged_in_staff = None
    st.rerun()

tab1, tab2, tab3 = st.tabs(["📅 希望休提出", "👁️ 確定シフト確認", "⚙️ マイページ"])

# ------------------------------
# タブ1: 希望休提出
# ------------------------------
with tab1:
    st.markdown("#### 対象月の選択")
    now = datetime.now()
    col_y, col_m = st.columns(2)
    # デフォルトは翌月
    target_year = col_y.number_input("年", min_value=2024, max_value=2030, value=now.year + 1 if now.month == 12 else now.year)
    target_month = col_m.number_input("月", min_value=1, max_value=12, value=1 if now.month == 12 else now.month + 1)
    
    req_col = f"希望休_{target_year}_{target_month:02d}"
    if req_col not in st.session_state.staff_data.columns:
        st.session_state.staff_data[req_col] = ""

    # 現在保存されている希望データを辞書化 (例: {1: "公休", 15: "午前半休"})
    existing_req = str(st.session_state.staff_data.at[selected_staff_idx, req_col])
    req_dict = {}
    if existing_req and existing_req not in ["nan", "None"]:
        for item in existing_req.split(","):
            if ":" in item:
                d_str, s_name = item.split(":")
                if d_str.strip().isdigit(): 
                    req_dict[int(d_str.strip())] = s_name.strip()

    # ダイアログ（小窓）での希望選択
    @st.dialog("シフト希望の選択")
    def select_shift_dialog(day):
        st.write(f"**{target_month}月 {day}日** の希望を選択してください。")
        current_val = req_dict.get(day, "(希望なし)")
        options = ["(希望なし)"] + st.session_state.shift_names
        idx = options.index(current_val) if current_val in options else 0
        
        selected = st.selectbox("希望シフト種類", options, index=idx)
        
        if st.button("決定", type="primary", use_container_width=True):
            if selected == "(希望なし)":
                if day in req_dict: del req_dict[day]
            else:
                req_dict[day] = selected
                
            new_reqs = [f"{d}:{s}" for d, s in req_dict.items()]
            st.session_state.staff_data.at[selected_staff_idx, req_col] = ",".join(new_reqs)
            st.rerun()

    st.markdown("<br><b>📝 日付をタップして希望を入力してください</b>", unsafe_allow_html=True)
    first_weekday, num_days = calendar.monthrange(target_year, target_month)
    weekdays = ["月", "火", "水", "木", "金", "土", "日"]

    # 曜日ヘッダー
    header_cols = st.columns(7)
    for i, w in enumerate(weekdays):
        color = "#ef4444" if i == 6 else "#3b82f6" if i == 5 else "#64748b"
        header_cols[i].markdown(f"<div style='text-align: center; color: {color}; font-size: 13px; font-weight: bold;'>{w}</div>", unsafe_allow_html=True)

    # カレンダー描画
    day_counter = 1
    for week in range(6):
        if day_counter > num_days: break
        cal_cols = st.columns(7)
        for i in range(7):
            if week == 0 and i < first_weekday or day_counter > num_days:
                cal_cols[i].write("")
            else:
                current_req = req_dict.get(day_counter)
                if current_req:
                    # 希望が入っている場合は文字付きで表示
                    label = f"**{day_counter}**\n{current_req}"
                else:
                    label = f"{day_counter}"
                
                if cal_cols[i].button(label, key=f"btn_{day_counter}", use_container_width=True):
                    select_shift_dialog(day_counter)
                day_counter += 1

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("📤 希望データを保存して送信", type="primary", use_container_width=True):
        with st.spinner('保存中...'):
            save_staff(st.session_state.staff_data)
            st.success("シフト希望を送信しました！管理者の画面に反映されます。")

# ------------------------------
# タブ2: 確定シフト確認
# ------------------------------
with tab2:
    st.markdown("#### 確定シフトの確認")
    st.info("管理者が公開した確定済みシフト表を確認できます。")
    
    c_y, c_m = st.columns(2)
    view_year = c_y.number_input("表示 年", min_value=2024, max_value=2030, value=now.year, key="view_y")
    view_month = c_m.number_input("表示 月", min_value=1, max_value=12, value=now.month, key="view_m")
    
    if st.button("🔄 シフト表を取得", use_container_width=True):
        with st.spinner(f"{view_year}年{view_month}月のシフトを取得中..."):
            # 年月を指定してシフトマトリックスを取得
            shift_data = api_request("shift_matrix", year=view_year, month=view_month)
            
            if not shift_data or (isinstance(shift_data, dict) and "error" in shift_data):
                st.warning(f"{view_year}年{view_month}月の確定シフトはまだ公開されていません。")
            else:
                df_shift = pd.DataFrame(shift_data)
                my_shift = df_shift[df_shift["名前"] == selected_staff_name]
                
                if my_shift.empty:
                    st.warning("あなたのシフトデータが見つかりませんでした。")
                else:
                    st.success(f"✅ {view_month}月のシフトを取得しました！")
                    st.markdown("##### 👩‍⚕️ あなたの勤務スケジュール")
                    
                    my_schedule = []
                    for col in df_shift.columns:
                        if "(" in col:  # 日付カラム(例: "1(月)")の判定
                            val = str(my_shift.iloc[0].get(col, "")).strip()
                            if val:
                                my_schedule.append({"日付": col, "決定シフト": val})
                    
                    if my_schedule:
                        st.dataframe(pd.DataFrame(my_schedule), use_container_width=True, hide_index=True)
                    else:
                        st.info("出勤予定はありません。")
                        
                    with st.expander("👁️ 施設全体のシフト表を見る"):
                        st.dataframe(df_shift, use_container_width=True)

# ------------------------------
# タブ3: マイページ（暗証番号変更）
# ------------------------------
with tab3:
    st.markdown("#### 暗証番号の変更")
    st.write("ログインに使用する暗証番号を変更できます。")
    
    with st.container(border=True):
        new_pin = st.text_input("新しい暗証番号", type="password")
        new_pin_confirm = st.text_input("新しい暗証番号 (確認)", type="password")
        
        if st.button("暗証番号を更新", type="primary", use_container_width=True):
            if new_pin == "":
                st.error("パスワードを空にはできません。")
            elif new_pin != new_pin_confirm:
                st.error("確認用パスワードが一致しません。")
            else:
                st.session_state.staff_data.at[selected_staff_idx, "暗証番号"] = new_pin
                with st.spinner("更新中..."):
                    save_staff(st.session_state.staff_data)
                    st.success("暗証番号を更新しました。次回から新しい暗証番号を使用してください。")
