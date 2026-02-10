import streamlit as st
import pandas as pd
from datetime import datetime
from google.cloud import firestore
from google.oauth2 import service_account

# ==========================================
# 1. 核心视觉样式
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
        background: white; border: 4px solid #ff6e40; border-radius: 20px; padding: 30px;
        text-align: center; box-shadow: 0 10px 30px rgba(255,110,64,0.1); margin: 20px 0;
    }
    .comment-box { background: white; padding: 15px; border-radius: 10px; margin-bottom: 12px; border-left: 5px solid #1e3d59; }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 数据库与数据加载 (Firebase)
# ==========================================
@st.cache_resource
def get_db():
    try:
        key_dict = st.secrets["firestore"]
        creds = service_account.Credentials.from_service_account_info(key_dict)
        return firestore.Client(credentials=creds, project=key_dict["project_id"])
    except: return None

db = get_db()

def load_comments(book_title):
    if not db: return []
    try:
        docs = db.collection("comments").where("book", "==", book_title).stream()
        res = [{"id": d.id, **d.to_dict()} for d in docs]
        return sorted(res, key=lambda x: x.get('time', ''), reverse=True)
    except: return []

def save_comment(book_title, text, user_info):
    if not db: return
    db.collection("comments").add({
        "book": book_title, "text": text,
        "author": user_info['name'], "email": user_info['email'],
        "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "timestamp": firestore.SERVER_TIMESTAMP
    })

CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTTIN0pxN-TYH1-_Exm6dfsUdo7SbnqVnWvdP_kqe63PkSL8ni7bH6r6c86MLUtf_q58r0gI2Ft2460/pub?output=csv"

@st.cache_data(ttl=600)
def load_data():
    try:
        df = pd.read_csv(CSV_URL)
        # 列索引对齐：il(1), rec(2), title(3), author(4), ar(5), quiz(7), word(8), en(10), cn(12), fnf(14), topic(15), series(16)
        c = {"title": 3, "author": 4, "il": 1, "ar": 5, "quiz": 7, "word": 8, "en": 10, "cn": 12, "fnf": 14, "topic": 15, "series": 16, "rec": 2}
        df.iloc[:, c['ar']] = pd.to_numeric(df.iloc[:, c['ar']].astype(str).str.extract(r'(\d+\.?\d*)')[0], errors='coerce').fillna(0.0)
        df.iloc[:, c['word']] = pd.to_numeric(df.iloc[:, c['word']], errors='coerce').fillna(0).astype(int)
        return df.fillna(" "), c
    except: return pd.DataFrame(), {}

df, idx = load_data()

# ==========================================
# 3. Session 状态
# ==========================================
if 'role' not in st.session_state: st.session_state.role = "Reader"
if 'user' not in st.session_state: st.session_state.user = None
if 'bk_focus' not in st.session_state: st.session_state.bk_focus = None
if 'blind_pick' not in st.session_state: st.session_state.blind_pick = None
if 'voted' not in st.session_state: st.session_state.voted = set()

# ==========================================
# 4. 左侧检索栏 (彻底补全版)
# ==========================================
with st.sidebar:
    st.markdown("### 🔐 身份管理")
    with st.expander("管理人员/用户登记"):
        if st.session_state.user:
            st.write(f"当前用户：{st.session_state.user['name']}")
            if st.button("注销"): st.session_state.user = None; st.session_state.role = "Reader"; st.rerun()
        else:
            pwd = st.text_input("管理密码", type="password")
            if pwd == st.secrets.get("owner_password"): st.session_state.role = "Owner"
            elif pwd == st.secrets.get("admin_password"): st.session_state.role = "Admin"

    st.write("---")
    st.markdown("### 🔍 全维度检索")
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
# 5. 详情页与留言板
# ==========================================
if st.session_state.bk_focus is not None:
    row = df.iloc[int(st.session_state.bk_focus)]
    title_key = str(row.iloc[idx['title']])
    if st.button("⬅️ 返回图书墙"): st.session_state.bk_focus = None; st.rerun()
    
    st.title(f"《{title_key}》")
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

    # 留言板功能
    st.write("---")
    st.subheader("💬 读者感悟留言板")
    cms = load_comments(title_key)
    for c in cms:
        ct, cd = st.columns([9, 1])
        with ct: st.markdown(f'<div class="comment-box"><small>{c["time"]}</small><br>{c["text"]}<br><span style="color:#ff6e40;font-weight:bold;">—— {c["author"]}</span></div>', unsafe_allow_html=True)
        with cd:
            if st.session_state.role in ["Owner", "Admin"]:
                if st.button("🗑️", key=f"del_{c['id']}"):
                    db.collection("comments").document(c['id']).delete(); st.rerun()

    if st.session_state.user is None and st.session_state.role == "Reader":
        with st.expander("📩 登记信息后即可发表留言"):
            with st.form("reg"):
                un = st.text_input("昵称"); um = st.text_input("邮箱")
                if st.form_submit_button("完成登记"):
                    if un and "@" in um: st.session_state.user = {"name": un, "email": um}; st.rerun()
    else:
        with st.form("msg", clear_on_submit=True):
            user_label = st.session_state.user['name'] if st.session_state.user else st.session_state.role
            txt = st.text_area(f"✍️ 以 {user_label} 身份发布：")
            if st.form_submit_button("发布感悟"):
                if txt.strip():
                    save_comment(title_key, txt, st.session_state.user or {"name": st.session_state.role, "email": "admin@sys"})
                    st.rerun()

# ==========================================
# 6. 主视图 (气球盲盒 + 点赞卡片)
# ==========================================
else:
    tab1, tab2, tab3 = st.tabs(["📚 图书海报墙", "📊 数据分布", "🏆 收藏清单"])
    
    with tab1:
        if st.button("🎁 开启选书盲盒", use_container_width=True):
            if not f_df.empty:
                st.session_state.blind_pick = f_df.sample(1).index[0]
                st.balloons() # 气球特效出现！
        
        if st.session_state.blind_pick is not None:
            b_row = df.iloc[st.session_state.blind_pick]
            st.markdown(f"""
            <div class="blind-box-card">
                <h3>🎈 气球盲盒抽中：《{b_row.iloc[idx['title']]}》</h3>
                <p>作者：{b_row.iloc[idx['author']]} | AR Quiz Number：{b_row.iloc[idx['quiz']]}</p>
            </div>
            """, unsafe_allow_html=True)
            bc1, bc2, bc3 = st.columns(3)
            if bc1.button("🔄 换一个"): st.session_state.blind_pick = f_df.sample(1).index[0]; st.rerun()
            if bc2.button("📖 进详情页", type="primary"): st.session_state.bk_focus = st.session_state.blind_pick; st.rerun()
            if bc3.button("❌ 关闭"): st.session_state.blind_pick = None; st.rerun()

        st.write("---")
        cols = st.columns(3)
        for i, (orig_idx, row) in enumerate(f_df.iterrows()):
            with cols[i % 3]:
                t = row.iloc[idx['title']]
                voted = t in st.session_state.voted
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
                
                cl, cr = st.columns([1, 4])
                if cl.button("❤️" if voted else "🤍", key=f"vote_{orig_idx}"):
                    if voted: st.session_state.voted.remove(t)
                    else: st.session_state.voted.add(t)
                    st.rerun()
                if cr.button("详情", key=f"det_{orig_idx}", use_container_width=True):
                    st.session_state.bk_focus = orig_idx; st.rerun()

    with tab3:
        st.subheader("❤️ 我点赞收藏的书籍")
        if st.session_state.voted:
            for item in st.session_state.voted: st.write(f"📖 {item}")
        else: st.info("还没有点赞过的书。")
