import streamlit as st
import pandas as pd
import random
from datetime import datetime
from google.cloud import firestore
from google.oauth2 import service_account

# ==========================================
# 1. 核心视觉样式
# ==========================================
st.set_page_config(page_title="YDRC 智慧书库", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #fdf6e3; }
    .book-tile {
        background: white; padding: 25px; border-radius: 12px; border: 1px solid #e2d1b0;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05); min-height: 420px; display: flex; flex-direction: column;
    }
    .tile-title { color: #1e3d59; font-size: 1.2em; font-weight: bold; margin-bottom: 15px; height: 3.2em; overflow: hidden; }
    .tag-container { margin-top: auto; display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 20px; }
    .tag { padding: 4px 10px; border-radius: 6px; font-size: 0.85em; font-weight: bold; color: white; }
    .tag-ar { background: #ff6e40; } .tag-word { background: #1e3d59; } .tag-fnf { background: #2a9d8f; } .tag-quiz { background: #457b9d; }
    .blind-box-card {
        background: white; border: 3px solid #ff6e40; border-radius: 20px; padding: 25px;
        box-shadow: 0 10px 30px rgba(255,110,64,0.1); margin: 20px 0;
    }
    .detail-card { background:white; padding:15px; border-radius:10px; border-left:5px solid #ff6e40; margin-bottom:10px; min-height:80px; }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 数据加载
# ==========================================
CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTTIN0pxN-TYH1-_Exm6dfsUdo7SbnqVnWvdP_kqe63PkSL8ni7bH6r6c86MLUtf_q58r0gI2Ft2460/pub?output=csv"

@st.cache_data(ttl=600)
def load_data():
    try:
        df = pd.read_csv(CSV_URL)
        # 索引对照：il(1), rec(2), title(3), author(4), ar(5), quiz(7), word(8), en(10), cn(12), fnf(14), topic(15), series(16)
        c = {"il": 1, "rec": 2, "title": 3, "author": 4, "ar": 5, "quiz": 7, "word": 8, "en": 10, "cn": 12, "fnf": 14, "topic": 15, "series": 16}
        df.iloc[:, c['ar']] = pd.to_numeric(df.iloc[:, c['ar']].astype(str).str.extract(r'(\d+\.?\d*)')[0], errors='coerce').fillna(0.0)
        df.iloc[:, c['word']] = pd.to_numeric(df.iloc[:, c['word']], errors='coerce').fillna(0).astype(int)
        return df.fillna(" "), c
    except: return pd.DataFrame(), {}

df, idx = load_data()

# ==========================================
# 3. 状态管理
# ==========================================
if 'bk_focus' not in st.session_state: st.session_state.bk_focus = None
if 'lang_mode' not in st.session_state: st.session_state.lang_mode = "EN"
if 'voted' not in st.session_state: st.session_state.voted = {} # {书名: 索引}
if 'blind_pick' not in st.session_state: st.session_state.blind_pick = None
if 'user' not in st.session_state: st.session_state.user = None
if 'do_balloons' not in st.session_state: st.session_state.do_balloons = False

# ==========================================
# 4. 强制气球触发逻辑
# ==========================================
if st.session_state.do_balloons:
    st.balloons()
    st.session_state.do_balloons = False # 喷完立即重置

# ==========================================
# 5. 左侧检索栏 (对齐所有截图项)
# ==========================================
with st.sidebar:
    st.markdown("### 🔍 全能检索栏")
    f_fuzzy = st.text_input("💡 智能模糊搜索")
    f_title = st.text_input("📖 书名 (Title)")
    f_author = st.text_input("👤 作者 (Author)")
    f_topic = st.text_input("🏷️ Topic - Subtopic (手动输入)")
    f_series = st.text_input("📺 Series 系列 (手动输入)")
    f_quiz = st.text_input("🔢 AR Quiz Number (手动输入)")
    f_fnf = st.selectbox("📚 类型", ["全部", "Fiction", "Nonfiction"])
    f_il = st.selectbox("🎯 Interest Level", ["全部", "LG", "MG", "MG+", "UG"])
    f_word_min = st.number_input("📝 最小词数", min_value=0, step=500)
    f_ar = st.slider("📊 ATOS Level 范围", 0.0, 12.0, (0.0, 12.0))

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
# 6. 详情页视图 (中英文理由 + 留言)
# ==========================================
if st.session_state.bk_focus is not None:
    row = df.iloc[int(st.session_state.bk_focus)]
    title_key = str(row.iloc[idx['title']])
    
    if st.button("⬅️ 返回图书墙"): 
        st.session_state.bk_focus = None
        st.rerun()
    
    st.title(f"📖 {title_key}")
    
    # 9宫格
    c1, c2, c3 = st.columns(3)
    details = [
        ("👤 作者", row.iloc[idx['author']]), ("📊 ATOS Level", row.iloc[idx['ar']]), 
        ("📝 词数", f"{row.iloc[idx['word']]:,}"), ("📚 类型", row.iloc[idx['fnf']]),
        ("🔢 AR Quiz Number", row.iloc[idx['quiz']]), ("🙋 推荐人", row.iloc[idx['rec']]),
        ("🎯 Interest Level", row.iloc[idx['il']]), ("📺 系列", row.iloc[idx['series']]),
        ("🏷️ 主题", row.iloc[idx['topic']])
    ]
    for i, (l, v) in enumerate(details):
        with [c1, c2, c3][i % 3]:
            st.markdown(f'<div class="detail-card"><small>{l}</small><br><b>{v}</b></div>', unsafe_allow_html=True)
    
    # 中英文推荐理由
    st.write("---")
    sc1, sc2, _ = st.columns([1,1,4])
    if sc1.button("English Review"): st.session_state.lang_mode = "EN"; st.rerun()
    if sc2.button("中文理由"): st.session_state.lang_mode = "CN"; st.rerun()
    
    content = row.iloc[idx['en']] if st.session_state.lang_mode == "EN" else row.iloc[idx['cn']]
    st.markdown(f'<div style="background:#fffcf5; padding:25px; border-radius:15px; border:1px dashed #ff6e40;">{content}</div>', unsafe_allow_html=True)

# ==========================================
# 7. 主视图 (气球盲盒 + 带详情按钮的收藏夹)
# ==========================================
else:
    tab1, tab2, tab3 = st.tabs(["📚 图书海报墙", "📊 数据分布", "❤️ 收藏清单"])
    
    with tab1:
        # 盲盒区
        if st.button("🎁 开启选书盲盒", use_container_width=True):
            if not f_df.empty:
                st.session_state.blind_pick = random.choice(f_df.index)
                st.session_state.do_balloons = True # 标记触发气球
                st.rerun()

        if st.session_state.blind_pick is not None:
            b_row = df.iloc[st.session_state.blind_pick]
            st.markdown(f"""
            <div class="blind-box-card">
                <h3>🎈 气球盲盒抽中：《{b_row.iloc[idx['title']]}》</h3>
                <p>作者：{b_row.iloc[idx['author']]} | AR Quiz Number：{b_row.iloc[idx['quiz']]}</p>
            </div>
            """, unsafe_allow_html=True)
            bc1, bc2, bc3 = st.columns(3)
            if bc1.button("🔄 换一个"): 
                st.session_state.blind_pick = random.choice(f_df.index)
                st.session_state.do_balloons = True # 换一个也要有气球！
                st.rerun()
            if bc2.button("📖 进入详细页", type="primary"): 
                st.session_state.bk_focus = st.session_state.blind_pick
                st.rerun()
            if bc3.button("❌ 关闭"): 
                st.session_state.blind_pick = None
                st.rerun()

        st.write("---")
        # 海报墙
        cols = st.columns(3)
        for i, (orig_idx, row) in enumerate(f_df.iterrows()):
            with cols[i % 3]:
                t = row.iloc[idx['title']]
                is_fav = t in st.session_state.voted
                st.markdown(f"""
                <div class="book-tile">
                    <div class="tile-title">《{t}》</div>
                    <div class="tag-container">
                        <span class="tag tag-ar">ATOS {row.iloc[idx['ar']]}</span>
                        <span class="tag tag-word">{row.iloc[idx['word']]:,} 字</span>
                        <span class="tag tag-fnf">{row.iloc[idx['fnf']]}</span>
                        <span class="tag tag-quiz">AR Quiz Number {row.iloc[idx['quiz']]}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                cv, cd = st.columns([1,3])
                if cv.button("❤️" if is_fav else "🤍", key=f"v_{orig_idx}"):
                    if is_fav: del st.session_state.voted[t]
                    else: st.session_state.voted[t] = orig_idx
                    st.rerun()
                if cd.button("详情", key=f"d_{orig_idx}", use_container_width=True):
                    st.session_state.bk_focus = orig_idx
                    st.rerun()

    with tab3:
        st.subheader("❤️ 我点赞收藏的书籍")
        if not st.session_state.voted:
            st.info("清单空空如也。")
        else:
            for title, o_idx in st.session_state.voted.items():
                col_t, col_b = st.columns([4,1])
                col_t.markdown(f"📖 **{title}**")
                # 补全：收藏页进入详情的按钮
                if col_b.button("进入详情", key=f"fav_goto_{o_idx}"):
                    st.session_state.bk_focus = o_idx
                    st.rerun()
