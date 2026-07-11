import streamlit as st
import pandas as pd
import io
import calendar
from datetime import datetime
import base64
import requests
import json
from ortools.sat.python import cp_model

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
            df = pd.DataFrame(columns=["名前", "運転可否", "希望休", "暗証番号"])
        else:
            df = pd.DataFrame(data)
            
        if "希望休" not in df.columns: df["希望休"] = ""
        if "暗証番号" not in df.columns: df["暗証番号"] = "0000"
            
        df["希望休"] = df["希望休"].fillna("").astype(str).replace('nan', '')
        df["暗証番号"] = df["暗証番号"].fillna("0000").astype(str).replace('nan', '0000').apply(lambda x: str(x).split('.')[0])
        return df
    except Exception as e:
        return pd.DataFrame(columns=["名前", "運転可否", "希望休", "暗証番号"])

def save_staff(df):
    """API経由でスタッフデータを保存"""
    data = df.to_dict(orient="records")
    requests.post(f"{API_URL}?sheet=staff", json=data)

def load_pair():
    """API経由でペア設定を読み込む"""
    try:
        response = requests.get(f"{API_URL}?sheet=pair_rules")
        data = response.json()
        if not data or isinstance(data, dict) and "error" in data:
            return pd.DataFrame(columns=["スタッフ1", "スタッフ2", "種類"])
        return pd.DataFrame(data)
    except:
        return pd.DataFrame(columns=["スタッフ1", "スタッフ2", "種類"])

def save_pair(df):
    """API経由でペア設定を保存"""
    data = df.to_dict(orient="records")
    requests.post(f"{API_URL}?sheet=pair_rules", json=data)

# ==========================================
# 表をイラスト(SVG画像)に変換する関数
# ==========================================
def create_svg_table(df):
    cell_w = 40
    cell_h = 30
    header_w = 120
    cols = df.columns.tolist()
    rows = df.values.tolist()
    
    width = header_w + len(cols[1:]) * cell_w
    height = (len(rows) + 1) * cell_h
    
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" height="100%">'
    svg += '<style>text { font-family: sans-serif; font-size: 14px; } .header { font-weight: bold; fill: #555; } .name { font-weight: bold; fill: #333; } .wk { fill: #d9534f; font-weight: bold; } .off { fill: #5bc0de; } .driver { font-size: 10px; fill: #5cb85c; font-weight: bold; } line { stroke: #ccc; stroke-width: 1; }</style>'
    
    svg += f'<rect width="{width}" height="{height}" fill="#ffffff" />'
    
    for i in range(len(rows) + 2):
        y = i * cell_h
        svg += f'<line x1="0" y1="{y}" x2="{width}" y2="{y}" />'
    for i in range(len(cols)):
        x = header_w if i == 0 else header_w + i * cell_w
        svg += f'<line x1="{x}" y1="0" x2="{x}" y2="{height}" />'
    svg += f'<line x1="0" y1="0" x2="0" y2="{height}" />'
    svg += f'<line x1="{width}" y1="0" x2="{width}" y2="{height}" />'
    
    svg += f'<rect x="0" y="0" width="{width}" height="{cell_h}" fill="#f8f9fa" />'
    for i, col in enumerate(cols):
        x = header_w / 2 if i == 0 else header_w + (i - 1) * cell_w + cell_w / 2
        svg += f'<text x="{x}" y="{cell_h / 2 + 5}" text-anchor="middle" class="header">{col}</text>'
        
    for r_idx, row in enumerate(rows):
        y = (r_idx + 1) * cell_h
        for c_idx, val in enumerate(row):
            x = header_w / 2 if c_idx == 0 else header_w + (c_idx - 1) * cell_w + cell_w / 2
            val_str = str(val) if pd.notna(val) else ""
            
            if c_idx == 0:
                svg += f'<text x="{x}" y="{y + cell_h / 2 + 5}" text-anchor="middle" class="name">{val_str}</text>'
            elif "休" in val_str:
                svg += f'<text x="{x}" y="{y + cell_h / 2 + 5}" text-anchor="middle" class="off">{val_str}</text>'
            elif "日" in val_str or "早" in val_str or "遅" in val_str:
                if "(運)" in val_str:
                    shift_type = val_str.replace("(運)", "")
                    svg += f'<text x="{x}" y="{y + cell_h / 2}" text-anchor="middle" class="wk">{shift_type}</text>'
                    svg += f'<text x="{x}" y="{y + cell_h - 2}" text-anchor="middle" class="driver">(運)</text>'
                else:
                    svg += f'<text x="{x}" y="{y + cell_h / 2 + 5}" text-anchor="middle" class="wk">{val_str}</text>'
            else:
                svg += f'<text x="{x}" y="{y + cell_h / 2 + 5}" text-anchor="middle">{val_str}</text>'
                
    svg += '</svg>'
    return svg

# ==========================================
# シフト自動作成 (AIエンジン: Google OR-Tools)
# ==========================================
def generate_shift(staff_data, pair_data, year, month, min_staff, min_driver):
    num_days = calendar.monthrange(year, month)[1]
    staff_list = staff_data["名前"].tolist()
    num_staff = len(staff_list)
    
    can_drive = [1 if str(x) == "可" else 0 for x in staff_data["運転可否"]]
    
    requests_dict = {}
    for i, req in enumerate(staff_data["希望休"]):
        days = []
        if pd.notna(req) and str(req).strip() != "":
            req_str = str(req).translate(str.maketrans('０１２３４５６７８９，、', '0123456789,,'))
            for x in req_str.split(','):
                x = x.strip()
                if x.isdigit():
                    d = int(x)
                    if 1 <= d <= num_days:
                        days.append(d - 1)
        requests_dict[i] = days

    model = cp_model.CpModel()
    shifts = {}
    shift_types = 4 
    for n in range(num_staff):
        for d in range(num_days):
            for s in range(shift_types):
                shifts[(n, d, s)] = model.NewBoolVar(f'shift_n{n}_d{d}_s{s}')

    for n in range(num_staff):
        for d in range(num_days):
            model.AddExactlyOne(shifts[(n, d, s)] for s in range(shift_types))

    for n, req_days in requests_dict.items():
        for d in req_days:
            model.Add(shifts[(n, d, 3)] == 1)

    for d in range(num_days):
        working_staff = []
        for n in range(num_staff):
            working_staff.append(shifts[(n, d, 0)])
            working_staff.append(shifts[(n, d, 1)])
            working_staff.append(shifts[(n, d, 2)])
        model.Add(sum(working_staff) >= min_staff)

    for d in range(num_days):
        working_drivers = []
        for n in range(num_staff):
            if can_drive[n] == 1:
                working_drivers.append(shifts[(n, d, 0)])
                working_drivers.append(shifts[(n, d, 1)])
                working_drivers.append(shifts[(n, d, 2)])
        model.Add(sum(working_drivers) >= min_driver)

    for n in range(num_staff):
        for d in range(num_days - 4):
            model.Add(sum(shifts[(n, d+i, 3)] for i in range(5)) >= 1)
            
    for n in range(num_staff):
        for d in range(num_days - 1):
            model.AddImplication(shifts[(n, d, 2)], shifts[(n, d+1, 1)].Not())

    if not pair_data.empty:
        for idx, row in pair_data.iterrows():
            s1_name, s2_name, p_type = row["スタッフ1"], row["スタッフ2"], row["種類"]
            if s1_name in staff_list and s2_name in staff_list:
                n1 = staff_list.index(s1_name)
                n2 = staff_list.index(s2_name)
                for d in range(num_days):
                    w1 = sum(shifts[(n1, d, s)] for s in range(3))
                    w2 = sum(shifts[(n2, d, s)] for s in range(3))
                    if p_type == "NG":
                        model.Add(w1 + w2 <= 1)
                    elif p_type == "相性◎":
                        model.Add(w1 == w2)

    target_off_days = num_days - (num_days * (min_staff + 1) // num_staff) 
    off_diffs = []
    for n in range(num_staff):
        total_off = sum(shifts[(n, d, 3)] for d in range(num_days))
        diff = model.NewIntVar(-num_days, num_days, f'diff_{n}')
        model.Add(diff == total_off - target_off_days)
        abs_diff = model.NewIntVar(0, num_days, f'abs_diff_{n}')
        model.AddAbsEquality(abs_diff, diff)
        off_diffs.append(abs_diff)
        
    model.Minimize(sum(off_diffs))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 10.0 
    status = solver.Solve(model)

    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        shift_result = []
        shift_marks = {0: "日勤", 1: "早出", 2: "遅出", 3: "休"}
        
        for n in range(num_staff):
            staff_row = {"名前": staff_list[n]}
            for d in range(num_days):
                for s in range(shift_types):
                    if solver.Value(shifts[(n, d, s)]) == 1:
                        mark = shift_marks[s]
                        if s != 3 and can_drive[n] == 1:
                            mark += "(運)"
                        staff_row[f"{d+1}日"] = mark
            shift_result.append(staff_row)
        return pd.DataFrame(shift_result), None
    else:
        return None, "条件が厳しすぎます。最低人数を減らすか、希望休を調整してください。"

# ==========================================
# 画面UIの設定
# ==========================================
st.set_page_config(page_title="シフト自動作成アプリ", page_icon="🧩", layout="wide")

st.title("🧩 介護施設 シフト自動作成システム")
st.markdown("AIが複雑な条件を考慮して、最適なシフトを数秒で作成します。（完全クラウド連携版）")

if st.button("🔄 データをスプレッドシートから最新化する"):
    st.session_state.staff_data = load_staff()
    st.session_state.pair_data = load_pair()
    st.success("最新のデータを読み込みました！")

if 'staff_data' not in st.session_state:
    st.session_state.staff_data = load_staff()
if 'pair_data' not in st.session_state:
    st.session_state.pair_data = load_pair()

tab1, tab2, tab3 = st.tabs(["🗓️ シフト作成", "👥 スタッフマスタ管理", "🔗 NG・相性ペア設定"])

with tab1:
    col1, col2 = st.columns([1, 3])
    
    with col1:
        st.header("⚙️ 作成条件")
        now = datetime.now()
        default_y = now.year + 1 if now.month == 12 else now.year
        default_m = 1 if now.month == 12 else now.month + 1
        
        target_year = st.number_input("年", min_value=2024, max_value=2030, value=default_y)
        target_month = st.number_input("月", min_value=1, max_value=12, value=default_m)
        min_staff = st.number_input("毎日の最低出勤人数", min_value=1, max_value=20, value=8)
        min_driver = st.number_input("毎日の最低運転手人数", min_value=0, max_value=10, value=2)
        
        st.markdown("---")
        generate_btn = st.button("✨ シフトを自動計算する", type="primary", use_container_width=True)

    with col2:
        st.header("📝 現在の希望休状況")
        st.info("※職員用アプリから入力された希望休がスプレッドシート経由で反映されます。")
        
        edited_staff = st.data_editor(
            st.session_state.staff_data,
            column_config={
                "名前": st.column_config.TextColumn("名前", disabled=True),
                "運転可否": st.column_config.TextColumn("運転", disabled=True),
                "希望休": st.column_config.TextColumn("希望休 (カンマ区切り)"),
                "暗証番号": None
            },
            hide_index=True,
            use_container_width=True
        )
        
        if st.button("💾 手修正した希望休をスプレッドシートへ保存"):
            save_staff(edited_staff)
            st.session_state.staff_data = edited_staff
            st.success("希望休をクラウドに更新しました！")

        if generate_btn:
            if st.session_state.staff_data.empty:
                st.warning("スタッフが登録されていません。マスタ管理から登録してください。")
            else:
                with st.spinner('AIが数億通りの組み合わせから最適なシフトを計算中...'):
                    result_df, error_msg = generate_shift(
                        st.session_state.staff_data, 
                        st.session_state.pair_data,
                        target_year, target_month, min_staff, min_driver
                    )
                    
                    if error_msg:
                        st.error(error_msg)
                    else:
                        st.success("🎉 シフトの作成が完了しました！")
                        st.session_state.result_df = result_df

        if 'result_df' in st.session_state:
            st.markdown("### 📊 完成したシフト表")
            st.dataframe(st.session_state.result_df, hide_index=True)
            
            dl_col1, dl_col2 = st.columns(2)
            with dl_col1:
                csv = st.session_state.result_df.to_csv(index=False).encode('utf-8-sig')
                st.download_button("📥 Excel(CSV)でダウンロード", csv, f"shift_{target_year}_{target_month}.csv", "text/csv", use_container_width=True)
                
            with dl_col2:
                svg_data = create_svg_table(st.session_state.result_df)
                b64 = base64.b64encode(svg_data.encode('utf-8')).decode('utf-8')
                href = f'<a href="data:image/svg+xml;base64,{b64}" download="shift_{target_year}_{target_month}.svg" style="display:inline-block; padding:0.5rem 1rem; background-color:#ff4b4b; color:white; text-decoration:none; border-radius:4px; text-align:center; width:100%;">🖼️ 画像(SVG)でダウンロード</a>'
                st.markdown(href, unsafe_allow_html=True)

with tab2:
    st.header("👥 スタッフマスタ管理")
    st.write("スタッフの追加、削除、運転可否の設定、およびログイン用暗証番号の管理を行います。")
    
    edited_staff_master = st.data_editor(
        st.session_state.staff_data,
        num_rows="dynamic",
        column_config={
            "名前": st.column_config.TextColumn("名前", required=True),
            "運転可否": st.column_config.SelectboxColumn("運転可否", options=["可", "不可"], required=True),
            "暗証番号": st.column_config.TextColumn("暗証番号 (4桁)", required=True, default="0000"),
            "希望休": None
        },
        hide_index=True,
        use_container_width=True
    )
    
    if st.button("💾 マスタを保存してクラウド(スプレッドシート)に反映", type="primary"):
        edited_staff_master = edited_staff_master.dropna(subset=["名前"])
        if "希望休" not in edited_staff_master.columns:
            edited_staff_master["希望休"] = ""
        if "暗証番号" not in edited_staff_master.columns:
            edited_staff_master["暗証番号"] = "0000"
        edited_staff_master["暗証番号"] = edited_staff_master["暗証番号"].fillna("0000").astype(str).apply(lambda x: x.split('.')[0])
        
        save_staff(edited_staff_master)
        st.session_state.staff_data = edited_staff_master
        st.success("スタッフマスタをスプレッドシートに保存しました！職員用アプリにも即座に反映されます。")

with tab3:
    st.header("🔗 NG・相性ペア設定")
    st.write("「一緒にシフトに入れない（NG）」「必ず一緒に入れる（相性◎）」のペアを設定します。")
    
    staff_names = st.session_state.staff_data["名前"].dropna().tolist()
    
    if len(staff_names) < 2:
        st.warning("ペアを設定するには、スタッフを2名以上登録してください。")
    else:
        edited_pair = st.data_editor(
            st.session_state.pair_data,
            num_rows="dynamic",
            column_config={
                "スタッフ1": st.column_config.SelectboxColumn("スタッフ1", options=staff_names, required=True),
                "スタッフ2": st.column_config.SelectboxColumn("スタッフ2", options=staff_names, required=True),
                "種類": st.column_config.SelectboxColumn("種類", options=["NG", "相性◎"], required=True),
            },
            hide_index=True,
            use_container_width=True
        )
        
        if st.button("💾 ペア設定をスプレッドシートに保存"):
            save_pair(edited_pair)
            st.session_state.pair_data = edited_pair
            st.success("ペア設定をスプレッドシートに保存しました！")