import streamlit as st
import pandas as pd
from datetime import datetime
from google.cloud import firestore
from google.oauth2 import service_account
import re

# ==========================================
# 1. 核心样式 (还原 UI 细节)
# ==========================================
st.set_page_config(page_title="智慧书库·旗舰版", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #fdf6e3; }
    .book-tile {
        background: white; padding: 20px; border-radius: 12px; border: 1px solid #e2d1b0;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05); min-height: 350px; display: flex; flex-direction: column;
    }
    .tile-title { color: #1e3d59; font-size: 1.1em; font-weight: bold; margin-bottom: 10px; height: 3em; overflow: hidden; }
    .tag-container { margin-top: auto; display: flex; flex-wrap: wrap; gap: 5px; margin-bottom: 15px; }
    .tag { padding: 4px 10px; border-radius: 6px; font-size: 0.8em; font-weight: bold; color: white; }
    .tag-ar { background: #ff6e40; } .tag-word { background: #1e3d59; } .tag-fnf { background: #2a9d8f; } .tag-quiz { background: #457b9d; }
    .comment-box { background: white; padding: 15px; border-radius: 10px; margin-bottom: 12px; border-left: 5px solid #1e3d59; }
    .author-tag { color: #ff6e40; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 数据库逻辑
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

# ==========================================
# 3. 数据加载与列映射 (严禁删减字段)
# ==========================================
CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTTIN0pxN-TYH1-_Exm6dfsUdo7SbnqVnWvdP_kqe63PkSL8ni7bH6r6c86MLUtf_q58r0gI2Ft2460/pub?output=csv"

@st.cache_data(ttl=600)
def load_data():
    try:
        df = pd.read_csv(CSV_URL)
        # 索引映射：il(1), rec(2), title(3), author(4), ar(5), quiz(7), word(8), en(10), cn(12), fnf(14), topic(15), series(16)
        c = {"title": 3, "author": 4, "il": 1, "ar": 5, "quiz": 7, "word": 8, "en": 10, "cn": 12, "fnf": 14, "topic": 15, "series": 16, "rec": 2}
        df.iloc[:, c['ar']] = pd.to_numeric(df.iloc[:, c['ar']].astype(str).str.extract(r'(\d+\.?\d*)')[0], errors='coerce').fillna(0.0)
        df.iloc[:, c['word']] = pd.to_numeric(df.iloc[:, c['word']], errors='coerce').fillna(0).astype(int)
        return df.fillna(" "), c
    except: return pd.DataFrame(), {}

df, idx = load_data()

# ==========================================
# 4. 初始化 Session 状态 (确保逻辑稳固)
# ==========================================
if 'role' not in st.session_state: st.session_state.role = "Reader"
if 'user' not in st.session_state: st.session_state.user = None
if 'bk_focus' not in st.session_state: st.session_state.bk_focus = None
if 'lang_mode' not in st.session_state: st.session_state.lang_mode = "EN"
if 'voted' not in st.session_state: st.session_state.voted = set()

# ==========================================
# 5. 侧边栏：【手动输入检索项】齐全
# ==========================================
with st.sidebar:
    st.markdown("### 🔐 身份验证")
    with st.expander("管理人员/已登记用户"):
        if st.session_state.user:
            st.info(f"👤 登记身份: {st.session_state.user['name']}")
            if st.button("注销"):
                st.session_state.user = None; st.session_state.role = "Reader"; st.rerun()
        else:
            pwd = st.text_input("管理密码", type="password")
            if pwd == st.secrets.get("owner_password"): st.session_state.role = "Owner"
            elif pwd == st.secrets.get("admin_password"): st.session_state.role = "Admin"

    st.write("---")
    st.markdown("### 🔍 全维度检索")
    f_fuzzy = st.text_input("💡 关键词搜索", placeholder="输入任何关键词...")
    f_title = st.text_input("📖 书名 (Title)")
    f_author = st.text_input("👤 作者 (Author)")
    
    # 彻底恢复：手动输入 Topic 和 Series
    f_topic = st.text_input("🏷️ Topic - Subtopic (手动输入)")
    f_series = st.text_input("📺 Series 系列 (手动输入)")
    
    f_quiz = st.text_input("🔢 AR Quiz Number")
    f_fnf = st.selectbox("📚 类型", ["全部", "Fiction", "Nonfiction"])
    f_ar = st.slider("📊 ATOS Book Level", 0.0, 12.0, (0.0, 12.0))

# 数据过滤逻辑 (严格执行)
f_df = df.copy()
if f_fuzzy: f_df = f_df[f_df.apply(lambda r: f_fuzzy.lower() in str(r.values).lower(), axis=1)]
if f_title: f_df = f_df[f_df.iloc[:, idx['title']].astype(str).str.contains(f_title, case=False)]
if f_author: f_df = f_df[f_df.iloc[:, idx['author']].astype(str).str.contains(f_author, case=False)]
if f_topic: f_df = f_df[f_df.iloc[:, idx['topic']].astype(str).str.contains(f_topic, case=False)]
if f_series: f_df = f_df[f_df.iloc[:, idx['series']].astype(str).str.contains(f_series, case=False)]
if f_quiz: f_df = f_df[f_df.iloc[:, idx['quiz']].astype(str).str.contains(f_quiz)]
if f_fnf != "全部": f_df = f_df[f_df.iloc[:, idx['fnf']] == f_fnf]
f_df = f_df[(f_df.iloc[:, idx['ar']] >= f_ar[0]) & (f_df.iloc[:, idx['ar']] <= f_ar[1])]

# ==========================================
# 6. 图书详情页 (全字段展示 + 留言登记)
# ==========================================
if st.session_state.bk_focus is not None:
    # 容错处理，确保索引有效
    try:
        row = df.iloc[int(st.session_state.bk_focus)]
        title_key = str(row.iloc[idx['title']])
    except:
        st.session_state.bk_focus = None; st.rerun()
    
    if st.button("⬅️ 返回列表"): st.session_state.bk_focus = None; st.rerun()
    
    st.title(f"《{title_key}》")
    
    # 全字段矩阵展示
    c1, c2, c3 = st.columns(3)
    details = [
        ("👤 作者", row.iloc[idx['author']]), ("📊 ATOS Level", row.iloc[idx['ar']]), 
        ("📝 词数", f"{row.iloc[idx['word']]:,}"), ("📚 类型", row.iloc[idx['fnf']]),
        ("🔢 Quiz No.", row.iloc[idx['quiz']]), ("🙋 推荐人", row.iloc[idx['rec']]),
        ("📺 系列", row.iloc[idx['series']]), ("🏷️ 主题", row.iloc[idx['topic']]),
        ("🎯 Interest Level", row.iloc[idx['il']])
    ]
    for i, (label, val) in enumerate(details):
        with [c1, c2, c3][i % 3]: 
            st.markdown(f'<div style="background:white;padding:12px;border-radius:10px;border-left:5px solid #ff6e40;margin-bottom:10px;"><small>{label}</small><br><b>{val}</b></div>', unsafe_allow_html=True)

    # 推荐理由 (英文优先)
    st.write("---")
    l_c1, l_c2, _ = st.columns([1, 1, 2])
    if l_c1.button("English Review"): st.session_state.lang_mode = "EN"; st.rerun()
    if l_c2.button("中文推荐理由"): st.session_state.lang_mode = "CN"; st.rerun()
    
    display_txt = row.iloc[idx['en']] if st.session_state.lang_mode == "EN" else row.iloc[idx['cn']]
    st.markdown(f'<div style="background:#fffcf5; padding:25px; border-radius:15px; border:1px solid #e2d1b0; min-height:150px;">{display_txt}</div>', unsafe_allow_html=True)

    # 留言板与登记系统
    st.write("---")
    st.subheader("💬 读者留言感悟")
    cms = load_db_comments(title_key)
    for c in cms:
        ct, cd = st.columns([9, 1])
        with ct: st.markdown(f'<div class="comment-box"><small>{c["time"]}</small><br>{c["text"]}<br><span class="author-tag">—— {c["author"]}</span></div>', unsafe_allow_html=True)
        with cd:
            if st.session_state.role in ["Owner", "Admin"]:
                if st.button("🗑️", key=f"del_{c['id']}"):
                    db.collection("comments").document(c['id']).delete(); st.rerun()

    # 发表感悟逻辑
    if st.session_state.user is None and st.session_state.role == "Reader":
        with st.expander("📩 登记邮箱与昵称后即可留言"):
            with st.form("reg_form"):
                u_n = st.text_input("自定义昵称"); u_m = st.text_input("邮箱地址")
                if st.form_submit_button("完成登记"):
                    if u_n and "@" in u_m:
                        st.session_state.user = {"name": u_n, "email": u_m}; st.rerun()
                    else: st.error("请填写正确的昵称和邮箱")
    else:
        with st.form("msg_form", clear_on_submit=True):
            user_label = st.session_state.user['name'] if st.session_state.user else st.session_state.role
            txt = st.text_area(f"✍️ 以 {user_label} 身份发布留言：")
            if st.form_submit_button("发布感悟"):
                if txt.strip():
                    save_db_comment(title_key, txt, st.session_state.user or {"name": st.session_state.role, "email": "admin@sys"})
                    st.rerun()

# ==========================================
# 7. 主视图 (海报墙 + 盲盒 + 卡片全标签)
# ==========================================
else:
    tab1, tab2, tab3 = st.tabs(["📚 图书海报墙", "📊 分级分布", "🏆 收藏清单"])
    
    with tab1:
        # 盲盒：修复瘫痪逻辑，直接跳转
        if st.button("🎁 开启随机选书盲盒 (惊喜跳转)", use_container_width=True):
            if not f_df.empty:
                st.session_state.bk_focus = int(f_df.sample(1).index[0])
                st.rerun()
        
        # 图书卡片墙 (补全 AR Quiz Number)
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
                        <span class="tag tag-quiz">Q#{row.iloc[idx["quiz"]]}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                cl, cr = st.columns(2)
                if cl.button("❤️" if voted else "🤍", key=f"h_{orig_idx}"):
                    if voted: st.session_state.voted.remove(t)
                    else: st.session_state.voted.add(t)
                    st.rerun()
                if cr.button("详情", key=f"d_{orig_idx}", use_container_width=True):
                    st.session_state.bk_focus = int(orig_idx); st.rerun()

    with tab2:
        st.bar_chart(f_df.iloc[:, idx['ar']].value_counts().sort_index())

    with tab3:
        st.subheader("⭐ 我的点赞收藏")
        if st.session_state.voted:
            # 建立反向映射用于收藏夹点击跳转
            lookup = {str(r.iloc[idx['title']]): i for i, r in df.iterrows()}
            for b_name in st.session_state.voted:
                c_n, c_v = st.columns([4, 1])
                c_n.write(f"📖 {b_name}")
                if c_v.button("进入详情", key=f"fav_{b_name}"):
                    st.session_state.bk_focus = int(lookup[b_name]); st.rerun()
        else: st.info("还没有收藏书籍哦")
