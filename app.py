import streamlit as st
import pandas as pd
from datetime import datetime
from google.cloud import firestore
from google.oauth2 import service_account

# ==========================================
# 1. 核心视觉样式 (严格对齐 UI)
# ==========================================
st.set_page_config(page_title="智慧书库·旗舰版", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #fdf6e3; }
    .book-tile {
        background: white; padding: 25px; border-radius: 12px; border: 1px solid #e2d1b0;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05); min-height: 420px; display: flex; flex-direction: column;
    }
    .tile-title { color: #1e3d59; font-size: 1.2em; font-weight: bold; margin-bottom: 15px; height: 3.2em; overflow: hidden; }
    .tag-container { margin-top: auto; display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 20px; }
    .tag { padding: 6px 12px; border-radius: 6px; font-size: 0.8em; font-weight: bold; color: white; }
    .tag-ar { background: #ff6e40; } .tag-word { background: #1e3d59; } .tag-fnf { background: #2a9d8f; } .tag-quiz { background: #457b9d; }
    .blind-box-card {
        background: white; border: 3px solid #ff6e40; border-radius: 20px; padding: 30px;
        text-align: center; box-shadow: 0 10px 30px rgba(255,110,64,0.1); margin: 20px 0;
    }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 数据处理引擎
# ==========================================
CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTTIN0pxN-TYH1-_Exm6dfsUdo7SbnqVnWvdP_kqe63PkSL8ni7bH6r6c86MLUtf_q58r0gI2Ft2460/pub?output=csv"

@st.cache_data(ttl=600)
def load_data():
    try:
        df = pd.read_csv(CSV_URL)
        # 字段映射：il(1), rec(2), title(3), author(4), ar(5), quiz(7), word(8), en(10), cn(12), fnf(14), topic(15), series(16)
        c = {"title": 3, "author": 4, "il": 1, "ar": 5, "quiz": 7, "word": 8, "en": 10, "cn": 12, "fnf": 14, "topic": 15, "series": 16, "rec": 2}
        df.iloc[:, c['ar']] = pd.to_numeric(df.iloc[:, c['ar']].astype(str).str.extract(r'(\d+\.?\d*)')[0], errors='coerce').fillna(0.0)
        df.iloc[:, c['word']] = pd.to_numeric(df.iloc[:, c['word']], errors='coerce').fillna(0).astype(int)
        return df.fillna(" "), c
    except: return pd.DataFrame(), {}

df, idx = load_data()

# ==========================================
# 3. Session 状态
# ==========================================
if 'bk_focus' not in st.session_state: st.session_state.bk_focus = None
if 'blind_pick' not in st.session_state: st.session_state.blind_pick = None
if 'lang_mode' not in st.session_state: st.session_state.lang_mode = "EN"

# ==========================================
# 4. 左侧检索栏：严格对齐图片，确保一项不缺
# ==========================================
with st.sidebar:
    st.markdown("### 🔐 身份与管理")
    with st.expander("管理人员/已登记用户"):
        st.info("点击此处登录或管理权限")
    
    st.write("---")
    st.markdown("### 🔍 综合搜索")
    f_fuzzy = st.text_input("💡 智能模糊搜索", placeholder="输入任何关键词...")
    f_title = st.text_input("📖 书名 (Title)")
    f_author = st.text_input("👤 作者 (Author)")
    f_topic = st.text_input("🏷️ Topic - Subtopic (手动输入)")
    f_series = st.text_input("📺 Series (手动输入)")
    
    f_fnf = st.selectbox("📚 类型", ["全部", "Fiction", "Nonfiction"])
    f_il = st.selectbox("🎯 Interest Level", ["全部", "LG", "MG", "MG+", "UG"])
    f_word_min = st.number_input("📝 最小词数", min_value=0, step=100)
    f_quiz = st.text_input("🔢 AR Quiz Number (手动输入)")
    f_ar = st.slider("📊 ATOS Book Level 范围", 0.0, 12.0, (0.0, 12.0))

# 过滤逻辑
f_df = df.copy()
if f_fuzzy: f_df = f_df[f_df.apply(lambda r: f_fuzzy.lower() in str(r.values).lower(), axis=1)]
if f_title: f_df = f_df[f_df.iloc[:, idx['title']].astype(str).str.contains(f_title, case=False)]
if f_author: f_df = f_df[f_df.iloc[:, idx['author']].astype(str).str.contains(f_author, case=False)]
if f_topic: f_df = f_df[f_df.iloc[:, idx['topic']].astype(str).str.contains(f_topic, case=False)]
if f_series: f_df = f_df[f_df.iloc[:, idx['series']].astype(str).str.contains(f_series, case=False)]
if f_quiz: f_df = f_df[f_df.iloc[:, idx['quiz']].astype(str).str.contains(f_quiz)]
if f_fnf != "全部": f_df = f_df[f_df.iloc[:, idx['fnf']] == f_fnf]
if f_il != "全部": f_df = f_df[f_df.iloc[:, idx['il']] == f_il]
f_df = f_df[f_df.iloc[:, idx['word']] >= f_word_min]
f_df = f_df[(f_df.iloc[:, idx['ar']] >= f_ar[0]) & (f_df.iloc[:, idx['ar']] <= f_ar[1])]

# ==========================================
# 5. 详情页视图 (全字段展示)
# ==========================================
if st.session_state.bk_focus is not None:
    row = df.iloc[int(st.session_state.bk_focus)]
    if st.button("⬅️ 返回列表墙"): st.session_state.bk_focus = None; st.rerun()
    
    st.title(f"📖 {row.iloc[idx['title']]}")
    
    c1, c2, c3 = st.columns(3)
    details = [
        ("👤 作者", row.iloc[idx['author']]), ("📊 ATOS Level", row.iloc[idx['ar']]), 
        ("📝 词数", f"{row.iloc[idx['word']]:,}"), ("📚 类型", row.iloc[idx['fnf']]),
        ("🔢 AR Quiz Number", row.iloc[idx['quiz']]), ("🙋 推荐人", row.iloc[idx['rec']]),
        ("📺 系列", row.iloc[idx['series']]), ("🏷️ 主题", row.iloc[idx['topic']]),
        ("🎯 Interest Level", row.iloc[idx['il']])
    ]
    for i, (l, v) in enumerate(details):
        with [c1, c2, c3][i % 3]:
            st.markdown(f'<div style="background:white;padding:12px;border-radius:10px;border-left:5px solid #ff6e40;margin-bottom:10px;"><small>{l}</small><br><b>{v}</b></div>', unsafe_allow_html=True)
    
    st.write("---")
    st.subheader("🌟 推荐详情")
    l1, l2, _ = st.columns([1,1,2])
    if l1.button("US English"): st.session_state.lang_mode = "EN"; st.rerun()
    if l2.button("CN 中文理由"): st.session_state.lang_mode = "CN"; st.rerun()
    
    txt = row.iloc[idx['en']] if st.session_state.lang_mode == "EN" else row.iloc[idx['cn']]
    st.markdown(f'<div style="background:#fffcf5; padding:20px; border-radius:15px; border:1px solid #e2d1b0;">{txt}</div>', unsafe_allow_html=True)

# ==========================================
# 6. 主视图 (盲盒预览卡 + 海报墙)
# ==========================================
else:
    tab1, tab2, tab3 = st.tabs(["📚 图书海报墙", "📊 数据分布", "🏆 收藏清单"])
    
    with tab1:
        # 盲盒：抽中后在页面显示一张卡片预览
        if st.button("🎁 开启选书盲盒", use_container_width=True):
            if not f_df.empty:
                st.session_state.blind_pick = f_df.sample(1).index[0]
            else: st.warning("没有符合条件的书籍")

        if st.session_state.blind_pick is not None:
            b_row = df.iloc[st.session_state.blind_pick]
            st.markdown(f"""
            <div class="blind-box-card">
                <h3>🎉 盲盒抽中：《{b_row.iloc[idx['title']]}》</h3>
                <p>作者：{b_row.iloc[idx['author']]} | ATOS：{b_row.iloc[idx['ar']]} | AR Quiz Number：{b_row.iloc[idx['quiz']]}</p>
            </div>
            """, unsafe_allow_html=True)
            bc1, bc2, bc3 = st.columns([1,1,1])
            if bc1.button("🔄 换一个", use_container_width=True):
                st.session_state.blind_pick = f_df.sample(1).index[0]; st.rerun()
            if bc2.button("📖 进入详细页", type="primary", use_container_width=True):
                st.session_state.bk_focus = st.session_state.blind_pick; st.rerun()
            if bc3.button("❌ 关闭盲盒", use_container_width=True):
                st.session_state.blind_pick = None; st.rerun()

        # 海报墙：完整文字标签
        st.write("---")
        cols = st.columns(3)
        for i, (orig_idx, row) in enumerate(f_df.iterrows()):
            with cols[i % 3]:
                st.markdown(f"""
                <div class="book-tile">
                    <div class="tile-title">《{row.iloc[idx['title']]}》</div>
                    <div class="tag-container">
                        <span class="tag tag-ar">ATOS {row.iloc[idx['ar']]}</span>
                        <span class="tag tag-word">{row.iloc[idx['word']]:,} 字</span>
                        <span class="tag tag-fnf">{row.iloc[idx['fnf']]}</span>
                        <span class="tag tag-quiz">AR Quiz Number {row.iloc[idx['quiz']]}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                if st.button("详情", key=f"d_{orig_idx}", use_container_width=True):
                    st.session_state.bk_focus = orig_idx; st.rerun()
