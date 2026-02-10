import streamlit as st
import pandas as pd
from datetime import datetime
from google.cloud import firestore
from google.oauth2 import service_account
import random

# ==========================================
# 1. 核心视觉与 CSS 配置
# ==========================================
st.set_page_config(page_title="YDRC 智慧书库", layout="wide")
st.markdown("""
    <style>
    .stApp { background-color: #fdf6e3; }
    .book-tile { background: white; padding: 20px; border-radius: 12px; border: 1px solid #e2d1b0; min-height: 250px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    .info-card { background: white; padding: 12px; border-radius: 10px; border-left: 5px solid #ff6e40; box-shadow: 0 2px 4px rgba(0,0,0,0.05); margin-bottom: 10px; }
    .blind-box-container { background: white; border: 4px solid #ff6e40; border-radius: 20px; padding: 30px; text-align: center; margin-bottom: 25px; }
    .comment-card { background: #f8f9fa; padding: 15px; border-radius: 10px; border-left: 5px solid #1e3d59; margin-bottom: 10px; }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 数据库连接
# ==========================================
@st.cache_resource
def get_db():
    try:
        if "firestore" in st.secrets:
            key_dict = st.secrets["firestore"]
            creds = service_account.Credentials.from_service_account_info(key_dict)
            return firestore.Client(credentials=creds, project=key_dict["project_id"])
    except: pass
    return None

db = get_db()

# ==========================================
# 3. 数据加载与状态初始化
# ==========================================
CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTTIN0pxN-TYH1-_Exm6dfsUdo7SbnqVnWvdP_kqe63PkSL8ni7bH6r6c86MLUtf_q58r0gI2Ft2460/pub?output=csv"

@st.cache_data(ttl=600)
def load_data():
    try:
        df = pd.read_csv(CSV_URL)
        return df.fillna(" ")
    except: return pd.DataFrame()

raw_df = load_data()

# 初始化所有核心 Session State
defaults = {'user': None, 'bk_focus': None, 'blind_idx': None, 'lang': "CN", 'voted': set()}
for k, v in defaults.items():
    if k not in st.session_state: st.session_state[k] = v

# ==========================================
# 4. 侧边栏：Logo + 登录 + 11个检索维度
# ==========================================
with st.sidebar:
    # A. Logo
    try: st.image("YDRC-logo.png", use_container_width=True)
    except: st.header("YDRC Library")
    
    # B. 登录
    if st.session_state.user is None:
        st.write("---")
        u_mail = st.text_input("邮箱 (ID)")
        u_pwd = st.text_input("密码", type="password")
        if st.button("进入系统", use_container_width=True):
            if db:
                doc = db.collection("users").document(u_mail).get()
                if doc.exists and str(doc.to_dict().get("password")) == u_pwd:
                    st.session_state.user = {**doc.to_dict(), "id": u_mail}
                    st.rerun()
                else: st.error("登录失败")
    else:
        st.success(f"你好: {st.session_state.user.get('nickname')}")
        if st.button("退出"): st.session_state.user = None; st.rerun()

    # C. 全维度检索 (1 模糊 + 10 物理字段)
    st.write("---")
    st.subheader("🔍 检索中心")
    s_fuzzy = st.text_input("💡 模糊搜索 (全表关键词)")
    s_il = st.text_input("🎯 利息级别 (IL)")      # Index 1
    s_rec = st.text_input("🙋 推荐人 (Rec)")      # Index 2
    s_title = st.text_input("📖 书名 (Title)")    # Index 3
    s_author = st.text_input("👤 作者 (Author)")  # Index 4
    s_ar = st.text_input("📊 AR 难度")             # Index 5
    s_quiz = st.text_input("🔢 测验编号 (Quiz)")   # Index 7
    s_words = st.text_input("📝 词数 (Words)")    # Index 8
    s_fnf = st.selectbox("📚 类型", ["全部", "Fiction", "Nonfiction"]) # Index 14
    s_topic = st.text_input("🏷️ 主题 (Topic)")    # Index 15
    s_series = st.text_input("🔗 系列 (Series)")  # Index 16

    # 过滤执行
    f_df = raw_df.copy()
    if s_fuzzy: f_df = f_df[f_df.apply(lambda r: s_fuzzy.lower() in str(r.values).lower(), axis=1)]
    if s_il: f_df = f_df[f_df.iloc[:, 1].astype(str).str.contains(s_il, case=False, na=False)]
    if s_rec: f_df = f_df[f_df.iloc[:, 2].astype(str).str.contains(s_rec, case=False, na=False)]
    if s_title: f_df = f_df[f_df.iloc[:, 3].astype(str).str.contains(s_title, case=False, na=False)]
    if s_author: f_df = f_df[f_df.iloc[:, 4].astype(str).str.contains(s_author, case=False, na=False)]
    if s_ar: f_df = f_df[f_df.iloc[:, 5].astype(str).str.contains(s_ar, case=False, na=False)]
    if s_quiz: f_df = f_df[f_df.iloc[:, 7].astype(str).str.contains(s_quiz, case=False, na=False)]
    if s_words: f_df = f_df[f_df.iloc[:, 8].astype(str).str.contains(s_words, case=False, na=False)]
    if s_fnf != "全部": f_df = f_df[f_df.iloc[:, 14].astype(str).str.contains(s_fnf, case=False, na=False)]
    if s_topic: f_df = f_df[f_df.iloc[:, 15].astype(str).str.contains(s_topic, case=False, na=False)]
    if s_series: f_df = f_df[f_df.iloc[:, 16].astype(str).str.contains(s_series, case=False, na=False)]

# ==========================================
# 5. 主视图：盲盒 + 收藏跳转书墙
# ==========================================
if st.session_state.bk_focus is None:
    st.title("🌟 智慧书库中心")
    
    # 盲盒区
    st.markdown('<div class="blind-box-container">', unsafe_allow_html=True)
    if st.button("🎁 开启选书盲盒", use_container_width=True):
        st.balloons()
        if not f_df.empty: st.session_state.blind_idx = random.choice(f_df.index)
    
    if st.session_state.blind_idx is not None and st.session_state.blind_idx in raw_df.index:
        b_row = raw_df.loc[st.session_state.blind_idx]
        st.markdown(f"### 🎊 选中：《{b_row.iloc[3]}》")
        st.write(f"作者：{b_row.iloc[4]} | 主题：{b_row.iloc[15]}")
        if st.button("进入详情页", key="go_blind"):
            st.session_state.bk_focus = st.session_state.blind_idx
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    # 书墙
    st.write(f"--- 找到 {len(f_df)} 本书 ---")
    cols = st.columns(3)
    for i, (idx, row) in enumerate(f_df.head(24).iterrows()):
        with cols[i % 3]:
            st.markdown(f"""<div class="book-tile">
                <h4 style="color:#1e3d59;">《{row.iloc[3]}》</h4>
                <p style="font-size:0.85em; color:#666;">👤 {row.iloc[4]}<br>🏷️ {row.iloc[15]}</p>
                </div>""", unsafe_allow_html=True)
            c_l, c_r = st.columns(2)
            # 点赞跳转逻辑：点赞后记录并直接进入详情页
            if c_l.button("❤️ 收藏" if row.iloc[3] in st.session_state.voted else "🤍 收藏", key=f"v_{idx}"):
                st.session_state.voted.add(row.iloc[3])
                st.session_state.bk_focus = idx
                st.rerun()
            if c_r.button("查看感悟", key=f"d_{idx}"):
                st.session_state.bk_focus = idx
                st.rerun()

# ==========================================
# 6. 详情页：12个维度 + 留言
# ==========================================
else:
    row = raw_df.loc[st.session_state.bk_focus]
    title = str(row.iloc[3])
    
    if st.button("⬅️ 返回书墙"): st.session_state.bk_focus = None; st.rerun()

    st.header(f"📖 {title}")
    
    # 10个核心维度展示 (Index 1, 2, 3, 4, 5, 7, 8, 14, 15, 16)
    dims = [
        ("🎯 IL", 1), ("🙋 推荐人", 2), ("👤 作者", 4), 
        ("📊 AR", 5), ("🔢 Quiz", 7), ("📝 词数", 8), 
        ("📚 类型", 14), ("🏷️ 主题", 15), ("🔗 系列", 16)
    ]
    cols = st.columns(3)
    for i, (label, ix) in enumerate(dims):
        with cols[i % 3]:
            st.markdown(f'<div class="info-card"><small>{label}</small><br><b>{row.iloc[ix]}</b></div>', unsafe_allow_html=True)

    # 中英文理由 (维度 11 & 12)
    st.write("---")
    l1, l2, _ = st.columns([1,1,4])
    if l1.button("中文理由"): st.session_state.lang = "CN"; st.rerun()
    if l2.button("English"): st.session_state.lang = "EN"; st.rerun()
    reason = row.iloc[12] if st.session_state.lang == "CN" else row.iloc[10]
    st.info(f"🌟 推荐理由：{reason}")

    # 留言板
    st.subheader("💬 读者感悟")
    if db:
        try:
            # 基础读取，不排序避免 400 错误
            cms = db.collection("comments").where("book", "==", title).stream()
            for m in cms:
                d = m.to_dict()
                st.markdown(f"""<div class="comment-card">
                    <small>{d.get('time')} | {d.get('nickname')}</small><br>{d.get('text')}
                </div>""", unsafe_allow_html=True)
        except: st.warning("留言加载中...")

    if st.session_state.user:
        new_txt = st.text_area("分享你的心得...")
        if st.button("提交感悟"):
            if new_txt.strip():
                db.collection("comments").add({
                    "book": title, "nickname": st.session_state.user['nickname'],
                    "text": new_txt, "time": datetime.now().strftime("%Y-%m-%d %H:%M")
                })
                st.rerun()
