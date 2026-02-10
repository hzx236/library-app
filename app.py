import streamlit as st
import pandas as pd
from datetime import datetime
from google.cloud import firestore
from google.oauth2 import service_account
import json
import re

# ==========================================
# 1. 样式与视觉配置 (旗舰版样式)
# ==========================================
st.set_page_config(page_title="智慧书库·全能管理版", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #fdf6e3; }
    [data-testid="stSidebar"] { background-color: #f0f2f6; border-right: 1px solid #e6e9ef; }
    .sidebar-title { color: #1e3d59; font-size: 1.5em; font-weight: bold; border-bottom: 2px solid #1e3d59; margin-bottom: 15px; }
    .book-tile {
        background: white; padding: 20px; border-radius: 12px; border: 1px solid #e2d1b0;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05); min-height: 330px; display: flex; flex-direction: column;
    }
    .tile-title { color: #1e3d59; font-size: 1.1em; font-weight: bold; margin-bottom: 5px; height: 2.8em; overflow: hidden; }
    .tag-container { margin-top: auto; display: flex; flex-wrap: wrap; gap: 5px; margin-bottom: 15px; }
    .tag { padding: 3px 8px; border-radius: 4px; font-size: 0.75em; font-weight: bold; color: white; }
    .tag-ar { background: #ff6e40; } .tag-word { background: #1e3d59; } .tag-fnf { background: #2a9d8f; } .tag-quiz { background: #6d597a; }
    .comment-box { background: white; padding: 15px; border-radius: 10px; margin-bottom: 12px; border-left: 5px solid #1e3d59; }
    .author-tag { color: #ff6e40; font-weight: bold; font-size: 0.85em; }
    .blind-box-container {
        background: white; border: 4px solid #ff6e40; border-radius: 20px; padding: 30px;
        text-align: center; box-shadow: 0 10px 25px rgba(255,110,64,0.15); margin: 15px 0;
    }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 数据库与数据引擎
# ==========================================
@st.cache_resource
def get_db():
    try:
        key_dict = st.secrets["firestore"]
        creds = service_account.Credentials.from_service_account_info(key_dict)
        return firestore.Client(credentials=creds, project=key_dict["project_id"])
    except: return None

db = get_db()

def load_db_comments(book_title):
    if not db: return []
    try:
        docs = db.collection("comments").where("book", "==", book_title).stream()
        res = [{"id": d.id, **d.to_dict()} for d in docs]
        return sorted(res, key=lambda x: x.get('time', ''), reverse=True)
    except: return []

def save_db_comment(book_title, text, user_info):
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
        c = {"title": 3, "author": 4, "il": 1, "ar": 5, "quiz": 7, "word": 8, "en": 10, "cn": 12, "fnf": 14, "topic": 15, "series": 16, "rec": 2}
        df.iloc[:, c['ar']] = pd.to_numeric(df.iloc[:, c['ar']].astype(str).str.extract(r'(\d+\.?\d*)')[0], errors='coerce').fillna(0.0)
        df.iloc[:, c['word']] = pd.to_numeric(df.iloc[:, c['word']], errors='coerce').fillna(0).astype(int)
        return df.fillna(" "), c
    except: return pd.DataFrame(), {}

df, idx = load_data()

# 初始化状态
if 'role' not in st.session_state: st.session_state.role = "Reader"
if 'user' not in st.session_state: st.session_state.user = None
# 注意：lang_mode 默认设为 EN (英文)
for key in ['bk_focus', 'lang_mode', 'voted', 'blind_idx']:
    if key not in st.session_state:
        st.session_state[key] = "EN" if key == 'lang_mode' else set() if key == 'voted' else None

# ==========================================
# 3. 侧边栏：权限与完整检索
# ==========================================
with st.sidebar:
    try: st.image("YDRC-logo.png", use_container_width=True)
    except: pass

    st.markdown('<div class="sidebar-title">🔐 身份与检索</div>', unsafe_allow_html=True)
    
    with st.expander("管理人员/已登记用户"):
        if st.session_state.user:
            st.write(f"当前：**{st.session_state.user['name']}**")
            if st.button("注销身份"):
                st.session_state.user = None
                st.session_state.role = "Reader"
                st.rerun()
        else:
            pwd = st.text_input("内部密码", type="password")
            if pwd == st.secrets.get("owner_password"):
                st.session_state.role = "Owner"; st.success("👑 创建者模式")
            elif pwd == st.secrets.get("admin_password"):
                st.session_state.role = "Admin"; st.success("🛡️ 管理员模式")

    st.write("---")
    f_fuzzy = st.text_input("💡 智能模糊检索", placeholder="输入关键词...")
    f_title = st.text_input("📖 书名 (Title)")
    f_author = st.text_input("👤 作者 (Author)")
    f_fnf = st.selectbox("📚 类型", ["全部", "Fiction", "Nonfiction"])
    f_il = st.selectbox("🎯 Interest Level", ["全部"] + sorted(df.iloc[:, idx['il']].unique().tolist()))
    f_word = st.number_input("📝 最小词数", min_value=0, step=100)
    f_quiz = st.text_input("🔢 AR Quiz Number")
    st.write("---")
    f_ar = st.slider("📊 ATOS Book Level 范围", 0.0, 12.0, (0.0, 12.0))

# 数据过滤逻辑
f_df = df.copy()
if f_fuzzy: f_df = f_df[f_df.apply(lambda r: f_fuzzy.lower() in str(r.values).lower(), axis=1)]
if f_title: f_df = f_df[f_df.iloc[:, idx['title']].astype(str).str.contains(f_title, case=False)]
if f_author: f_df = f_df[f_df.iloc[:, idx['author']].astype(str).str.contains(f_author, case=False)]
if f_fnf != "全部": f_df = f_df[f_df.iloc[:, idx['fnf']] == f_fnf]
if f_il != "全部": f_df = f_df[f_il == f_df.iloc[:, idx['il']]]
if f_quiz: f_df = f_df[f_df.iloc[:, idx['quiz']].astype(str).str.contains(f_quiz)]
f_df = f_df[(f_df.iloc[:, idx['ar']] >= f_ar[0]) & (f_df.iloc[:, idx['ar']] <= f_ar[1]) & (f_df.iloc[:, idx['word']] >= f_word)]

# ==========================================
# 4. 图书详情页
# ==========================================
if st.session_state.bk_focus is not None:
    row = df.iloc[st.session_state.bk_focus]
    title_key = str(row.iloc[idx['title']])
    
    if st.button("⬅️ 返回图书墙"): 
        st.session_state.bk_focus = None; st.rerun()
    
    st.title(f"📖 {title_key}")
    
    c1, c2, c3 = st.columns(3)
    infos = [("👤 作者", row.iloc[idx['author']]), ("📚 类型", row.iloc[idx['fnf']]), ("📊 ATOS Level", row.iloc[idx['ar']]),
             ("🔢 Quiz No.", row.iloc[idx['quiz']]), ("📝 词数", f"{row.iloc[idx['word']]:,}"), ("🙋 推荐人", row.iloc[idx['rec']])]
    for i, (l, v) in enumerate(infos):
        with [c1, c2, c3][i % 3]: st.markdown(f'<div style="background:white;padding:10px;border-radius:10px;border-left:5px solid #ff6e40;margin-bottom:10px;"><small>{l}</small><br><b>{v}</b></div>', unsafe_allow_html=True)

    # --- 推荐理由切换 (默认先EN后CN) ---
    st.write("#### 🌟 推荐详情")
    lb1, lb2, _ = st.columns([1,1,2])
    if lb1.button("US English"): st.session_state.lang_mode = "EN"; st.rerun()
    if lb2.button("CN 中文理由"): st.session_state.lang_mode = "CN"; st.rerun()
    
    # 根据 lang_mode 显示对应列
    display_text = row.iloc[idx['en']] if st.session_state.lang_mode == "EN" else row.iloc[idx['cn']]
    st.markdown(f'<div style="background:#fffcf5; padding:25px; border-radius:15px; border:2px dashed #ff6e40; min-height:150px;">{display_text}</div>', unsafe_allow_html=True)

    # 留言板 (三级权限核心)
    st.markdown("---")
    st.subheader("💬 读者感悟")
    cms = load_db_comments(title_key)
    for c in cms:
        col_t, col_o = st.columns([9, 1])
        with col_t:
            st.markdown(f'<div class="comment-box"><small>{c["time"]}</small><br>{c["text"]}<br><span class="author-tag">—— {c["author"]}</span></div>', unsafe_allow_html=True)
        with col_o:
            if st.session_state.role in ["Owner", "Admin"]:
                if st.button("🗑️", key=f"del_{c['id']}"):
                    db.collection("comments").document(c['id']).delete(); st.rerun()

    # 发表感悟 (注册/留言逻辑)
    st.write("---")
    if st.session_state.user is None and st.session_state.role == "Reader":
        st.info("💡 只有注册登记后的读者才能发表感悟。")
        with st.expander("📩 快速登记以留言"):
            with st.form("reg_form"):
                u_name = st.text_input("自定义昵称 (署名)")
                u_mail = st.text_input("邮箱 (备案)")
                if st.form_submit_button("完成登记"):
                    if u_name and re.match(r"[^@]+@[^@]+\.[^@]+", u_mail):
                        st.session_state.user = {"name": u_name, "email": u_mail}
                        st.session_state.role = "Verified"; st.rerun()
                    else: st.error("请检查输入内容")
    else:
        with st.form("post_form", clear_on_submit=True):
            curr_name = st.session_state.user['name'] if st.session_state.user else st.session_state.role
            st.write(f"✍️ 以 **{curr_name}** 身份留言")
            txt = st.text_area("分享你的阅读心得...")
            if st.form_submit_button("发布"):
                if txt.strip():
                    save_db_comment(title_key, txt, st.session_state.user or {"name": st.session_state.role, "email": "admin@sys"})
                    st.rerun()

# ==========================================
# 5. 主视图 (盲盒、统计、海报墙)
# ==========================================
else:
    tab1, tab2, tab3 = st.tabs(["📚 图书海报墙", "📊 分级分布统计", "🏆 读者高赞榜单"])
    
    with tab1:
        if st.button("🎁 开启选书盲盒", use_container_width=True):
            st.balloons(); st.session_state.blind_idx = f_df.sample(1).index[0] if not f_df.empty else df.sample(1).index[0]
        if st.session_state.blind_idx is not None:
            b_row = df.iloc[st.session_state.blind_idx]
            st.markdown(f'<div class="blind-box-container"><h3>《{b_row.iloc[idx["title"]]}》</h3><p>作者: {b_row.iloc[idx["author"]]}</p></div>', unsafe_allow_html=True)
            if st.button("🚀 进入详情", use_container_width=True):
                st.session_state.bk_focus = st.session_state.blind_idx; st.rerun()

        cols = st.columns(3)
        for i, (orig_idx, row) in enumerate(f_df.iterrows()):
            with cols[i % 3]:
                t = row.iloc[idx['title']]
                voted = t in st.session_state.voted
                st.markdown(f"""
                <div class="book-tile">
                    <div class="tile-title">《{t}》</div>
                    <div class="tag-container">
                        <span class="tag tag-ar">ATOS {row.iloc[idx["ar"]]}</span>
                        <span class="tag tag-word">{row.iloc[idx["word"]]:,} 字</span>
                        <span class="tag tag-fnf">{row.iloc[idx["fnf"]]}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                cl, cr = st.columns(2)
                if cl.button("❤️" if voted else "🤍", key=f"h_{orig_idx}"):
                    if voted: st.session_state.voted.remove(t)
                    else: st.session_state.voted.add(t)
                    st.rerun()
                if cr.button("详情", key=f"d_{orig_idx}"):
                    st.session_state.bk_focus = orig_idx; st.rerun()

    with tab2:
        st.subheader("📊 ATOS 分级分布统计")
        st.bar_chart(f_df.iloc[:, idx['ar']].value_counts().sort_index())

    with tab3:
        st.subheader("🏆 您的点赞记录")
        for b in st.session_state.voted: st.write(f"⭐ {b}")
