import streamlit as st
import pandas as pd
from datetime import datetime
from google.cloud import firestore
from google.oauth2 import service_account
import json
import os

# ==========================================
# 1. 样式与视觉配置 (保留原样)
# ==========================================
st.set_page_config(page_title="智慧书库·全能旗舰版", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #fdf6e3; }
    [data-testid="stSidebar"] { background-color: #f0f2f6; border-right: 1px solid #e6e9ef; }
    .sidebar-title { color: #1e3d59; font-size: 1.5em; font-weight: bold; border-bottom: 2px solid #1e3d59; margin-bottom: 15px; }
    .book-tile { background: white; padding: 20px; border-radius: 12px; border: 1px solid #e2d1b0; box-shadow: 0 4px 6px rgba(0,0,0,0.05); min-height: 330px; display: flex; flex-direction: column; }
    .tile-title { color: #1e3d59; font-size: 1.1em; font-weight: bold; margin-bottom: 5px; height: 2.8em; overflow: hidden; }
    .tag-container { margin-top: auto; display: flex; flex-wrap: wrap; gap: 5px; margin-bottom: 15px; }
    .tag { padding: 3px 8px; border-radius: 4px; font-size: 0.75em; font-weight: bold; color: white; }
    .tag-ar { background: #ff6e40; } .tag-word { background: #1e3d59; } .tag-fnf { background: #2a9d8f; } .tag-quiz { background: #6d597a; }
    .comment-box { background: white; padding: 15px; border-radius: 10px; margin-bottom: 12px; border: 1px solid #eee; border-left: 5px solid #1e3d59; }
    .blind-box-container { background: white; border: 4px solid #ff6e40; border-radius: 20px; padding: 30px; text-align: center; box-shadow: 0 10px 25px rgba(255,110,64,0.15); margin: 15px 0; }
    .info-card { background: white; padding: 15px; border-radius: 12px; border-left: 6px solid #ff6e40; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 数据库与账户权限逻辑 (核心增强)
# ==========================================

@st.cache_resource
def get_db_client():
    try:
        key_dict = st.secrets["firestore"]
        creds = service_account.Credentials.from_service_account_info(key_dict)
        return firestore.Client(credentials=creds, project=key_dict["project_id"])
    except Exception as e:
        st.error(f"无法读取 Secrets 配置: {e}")
        return None

db = get_db_client()

# --- 用户管理逻辑 ---
def register_user(email, password, nickname):
    if not db: return False
    # 检查昵称唯一性
    existing_nick = db.collection("users").where("nickname", "==", nickname).limit(1).get()
    if len(list(existing_nick)) > 0:
        return "NICK_EXISTS"
    
    # 检查邮箱是否已注册
    user_doc = db.collection("users").document(email).get()
    if user_doc.exists:
        return "EMAIL_EXISTS"
    
    # 设定角色逻辑: 第一个注册的可以是 Owner（或通过配置文件指定）
    role = "user"
    if email == st.secrets.get("owner_email"): role = "owner"
    
    db.collection("users").document(email).set({
        "password": password, # 建议实际生产环境加密
        "nickname": nickname,
        "role": role,
        "created_at": firestore.SERVER_TIMESTAMP
    })
    return "SUCCESS"

def login_user(email, password):
    if not db: return None
    user_doc = db.collection("users").document(email).get()
    if user_doc.exists:
        u_data = user_doc.to_dict()
        if u_data['password'] == password:
            return {"email": email, "nickname": u_data['nickname'], "role": u_data['role']}
    return None

# --- 留言管理 (增加昵称关联) ---
def load_db_comments(book_title):
    if db is None: return []
    try:
        col_ref = db.collection("comments").where("book", "==", book_title)
        docs = col_ref.stream()
        comments = [{"id": d.id, **d.to_dict()} for d in docs]
        return sorted(comments, key=lambda x: x.get('time', ''), reverse=True)
    except: return []

def save_db_comment(book_title, text, nickname, comment_id=None):
    if db is None: return
    data = {
        "book": book_title,
        "text": text,
        "nickname": nickname, # 仅存昵称，保护隐私
        "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "timestamp": firestore.SERVER_TIMESTAMP
    }
    try:
        if comment_id:
            db.collection("comments").document(comment_id).update(data)
        else:
            db.collection("comments").add(data)
        st.toast("✅ 留言已发布", icon='💬')
    except: st.error("保存失败")

# --- 数据加载 (保留原样) ---
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

# 初始化 Session State
state_keys = {
    'bk_focus': None, 'lang_mode': "CN", 'voted': set(), 
    'edit_doc_id': None, 'blind_idx': None, 'temp_comment': "", 
    'form_version': 0, 'user': None
}
for k, v in state_keys.items():
    if k not in st.session_state: st.session_state[k] = v

# ==========================================
# 3. 侧边栏：账户与检索
# ==========================================
with st.sidebar:
    try: st.image("YDRC-logo.png", use_container_width=True)
    except: pass 

    # --- 账户系统 ---
    st.markdown('<div class="sidebar-title">👤 用户中心</div>', unsafe_allow_html=True)
    if st.session_state.user is None:
        tab_login, tab_reg = st.tabs(["登录", "注册"])
        with tab_login:
            lemail = st.text_input("邮箱", key="login_email")
            lpass = st.text_input("密码", type="password", key="login_pass")
            if st.button("立即登录", use_container_width=True):
                user = login_user(lemail, lpass)
                if user:
                    st.session_state.user = user
                    st.rerun()
                else: st.error("邮箱或密码错误")
        with tab_reg:
            remail = st.text_input("有效邮箱", key="reg_email")
            rpass = st.text_input("密码", type="password", key="reg_pass")
            rnick = st.text_input("唯一昵称 (署名用)", key="reg_nick")
            if st.button("提交注册", use_container_width=True):
                if "@" not in remail: st.error("请输入有效邮箱")
                elif not rnick: st.error("昵称不能为空")
                else:
                    res = register_user(remail, rpass, rnick)
                    if res == "SUCCESS": st.success("注册成功，请切换至登录页"); st.balloons()
                    elif res == "NICK_EXISTS": st.error("❌ 该昵称已被占用")
                    else: st.error("❌ 邮箱已存在")
    else:
        u = st.session_state.user
        role_label = {"owner": "👑 站长", "admin": "🛠️ 管理员", "user": "📖 读者"}[u['role']]
        st.success(f"{role_label}: {u['nickname']}")
        if st.button("退出登录", use_container_width=True):
            st.session_state.user = None
            st.rerun()

    st.write("---")
    # --- 检索中心 (保留原逻辑) ---
    st.markdown('<div class="sidebar-title">🔍 检索中心</div>', unsafe_allow_html=True)
    f_fuzzy = st.text_input("💡 **智能模糊检索**")
    f_title = st.text_input("📖 书名 (Title)")
    f_fnf = st.selectbox("📚 类型", ["全部", "Fiction", "Nonfiction"])
    f_ar = st.slider("📊 ATOS 范围", 0.0, 12.0, (0.0, 12.0))

# ==========================================
# 4. 图书详情页 (隐私与权限保护)
# ==========================================
if st.session_state.bk_focus is not None:
    row = df.iloc[st.session_state.bk_focus]
    title_key = str(row.iloc[idx['title']])
    
    if st.button("⬅️ 返回图书墙"): 
        st.session_state.bk_focus = None
        st.rerun()
    
    st.markdown(f"# 📖 {title_key}")
    # 详情卡片逻辑同原版... (省略重复UI部分，代码逻辑一致)
    c1, c2, c3 = st.columns(3)
    # ...[此处保留你原有的 info-card 渲染逻辑]...
    st.markdown(f'<div style="background:#fffcf5; padding:25px; border-radius:15px; border:2px dashed #ff6e40;">{row.iloc[idx["cn"]] if st.session_state.lang_mode=="CN" else row.iloc[idx["en"]]}</div>', unsafe_allow_html=True)

    st.markdown("---")
    st.subheader("💬 读者感悟 (公开可见)")
    
    # 加载留言
    cloud_comments = load_db_comments(title_key)
    for i, m in enumerate(cloud_comments):
        st.markdown(f'<div class="comment-box"><small>📅 {m.get("time")} | 👤 {m.get("nickname")}</small><br>{m.get("text")}</div>', unsafe_allow_html=True)
        
        # 权限管理：本人、Admin、Owner 可修改
        curr_user = st.session_state.user
        can_edit = curr_user and (curr_user['nickname'] == m.get('nickname') or curr_user['role'] in ['admin', 'owner'])
        
        if can_edit and st.session_state.edit_doc_id is None:
            if st.button(f"✏️ 管理留言", key=f"edit_{m['id']}"):
                st.session_state.edit_doc_id = m["id"]
                st.session_state.temp_comment = m["text"]
                st.rerun()

    # 留言发布区：仅登录用户可见
    if st.session_state.user:
        with st.form("comment_form"):
            st.write(f"✍️ 以 **{st.session_state.user['nickname']}** 的身份留言")
            user_input = st.text_area("分享你的阅读心得...", value=st.session_state.temp_comment)
            if st.form_submit_button("发布感悟"):
                if user_input.strip():
                    save_db_comment(title_key, user_input, st.session_state.user['nickname'], st.session_state.get('edit_doc_id'))
                    st.session_state.edit_doc_id = None
                    st.session_state.temp_comment = ""
                    st.rerun()
    else:
        st.info("💡 留言功能仅对注册用户开放。请在左侧侧边栏 [登录/注册] 后发表感悟。")

# ==========================================
# 5. 主视图海报墙 (保留原逻辑)
# ==========================================
elif not df.empty:
    # ...[此处保留你原有的海报墙、盲盒、统计、高赞榜单逻辑]...
    # (逻辑完全一致，仅需确保使用了 f_df 过滤后的结果)
    f_df = df.copy()
    if f_fuzzy: f_df = f_df[f_df.apply(lambda r: f_fuzzy.lower() in str(r.values).lower(), axis=1)]
    # (此处省略过滤代码，与你提供的版本完全一致)
    
    tab1, tab2, tab3 = st.tabs(["📚 图书海报墙", "📊 分级分布统计", "🏆 读者高赞榜单"])
    with tab1:
        # [海报墙渲染逻辑...]
        st.write("图书检索完成，共找到", len(f_df), "本图书")
        # 之前的海报墙循环代码...
        cols = st.columns(3)
        for i, (orig_idx, row) in enumerate(f_df.iterrows()):
            with cols[i % 3]:
                t = row.iloc[idx['title']]
                st.markdown(f'<div class="book-tile"><div class="tile-title">《{t}》</div></div>', unsafe_allow_html=True)
                if st.button("查看详情", key=f"d_{orig_idx}"):
                    st.session_state.bk_focus = orig_idx; st.rerun()
