import streamlit as st
import pandas as pd
from datetime import datetime
from google.cloud import firestore
from google.oauth2 import service_account
import hashlib
import re

# ==========================================
# 1. 样式与配置
# ==========================================
st.set_page_config(page_title="智慧书库·全能旗舰版", layout="wide", page_icon="📚")

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
    .comment-box { background: white; padding: 15px; border-radius: 10px; margin-bottom: 12px; border: 1px solid #eee; border-left: 5px solid #1e3d59; }
    .info-card { background: white; padding: 15px; border-radius: 12px; border-left: 6px solid #ff6e40; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    .blind-box-container {
        background: white; border: 4px solid #ff6e40; border-radius: 20px; padding: 30px;
        text-align: center; box-shadow: 0 10px 25px rgba(255,110,64,0.15); margin: 15px 0;
    }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 数据库工具
# ==========================================
@st.cache_resource
def get_db_client():
    try:
        key_dict = st.secrets["firestore"]
        creds = service_account.Credentials.from_service_account_info(key_dict)
        return firestore.Client(credentials=creds, project=key_dict["project_id"])
    except:
        return None

db = get_db_client()

def make_hash(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

# ==========================================
# 3. 数据加载 (修正列索引)
# ==========================================
CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTTIN0pxN-TYH1-_Exm6dfsUdo7SbnqVnWvdP_kqe63PkSL8ni7bH6r6c86MLUtf_q58r0gI2Ft2460/pub?output=csv"

@st.cache_data(ttl=600)
def load_data():
    try:
        df = pd.read_csv(CSV_URL)
        # 严格对应 K=10(EN), M=12(CN)
        c = {
            "il": 1, "rec": 2, "title": 3, "author": 4, "ar": 5, 
            "quiz": 7, "word": 8, "en": 10, "cn": 12, 
            "fnf": 14, "topic": 15, "series": 16
        }
        df.iloc[:, c['ar']] = pd.to_numeric(df.iloc[:, c['ar']].astype(str).str.extract(r'(\d+\.?\d*)')[0], errors='coerce').fillna(0.0)
        df.iloc[:, c['word']] = pd.to_numeric(df.iloc[:, c['word']], errors='coerce').fillna(0).astype(int)
        return df.fillna(" "), c
    except:
        return pd.DataFrame(), {}

df, idx = load_data()

# ==========================================
# 4. 初始化状态
# ==========================================
if 'voted' not in st.session_state: st.session_state.voted = set()
if 'bk_focus' not in st.session_state: st.session_state.bk_focus = None
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'user_role' not in st.session_state: st.session_state.user_role = "guest"
if 'lang_mode' not in st.session_state: st.session_state.lang_mode = "CN"
if 'blind_idx' not in st.session_state: st.session_state.blind_idx = None

# ==========================================
# 5. 侧边栏：权限与检索
# ==========================================
with st.sidebar:
    st.markdown("### 👤 用户中心")
    if not st.session_state.logged_in:
        auth_tab = st.tabs(["登录", "注册"])
        with auth_tab[0]:
            l_email = st.text_input("邮箱")
            l_pass = st.text_input("密码", type="password")
            if st.button("🚀 登录"):
                if db:
                    user_doc = db.collection("users").document(l_email).get()
                    if user_doc.exists and user_doc.to_dict()['password'] == make_hash(l_pass):
                        u_data = user_doc.to_dict()
                        st.session_state.update({
                            'logged_in': True, 'user_email': l_email, 
                            'user_nickname': u_data['nickname'], 
                            'user_role': u_data.get('role', 'user')
                        })
                        st.rerun()
                    else: st.error("登录失败")
        
        with auth_tab[1]:
            r_email = st.text_input("新邮箱")
            r_nick = st.text_input("昵称")
            r_pass = st.text_input("设置密码", type="password")
            if st.button("📝 注册"):
                if db and r_email and len(r_pass) >= 6:
                    db.collection("users").document(r_email).set({
                        "email": r_email, "nickname": r_nick, "password": make_hash(r_pass),
                        "role": "owner" if r_email == st.secrets.get("owner_email") else "user"
                    })
                    st.success("注册成功")

        # 增强安全性重置：需验证数据库 Project ID
        with st.expander("🔑 紧急找回(Owner Only)"):
            reset_mail = st.text_input("验证邮箱")
            sec_verify = st.text_input("Firestore ProjectID 验证", type="password")
            new_secret_pw = st.text_input("新密码 ", type="password")
            if st.button("强制重置"):
                if sec_verify == st.secrets["firestore"]["project_id"]:
                    db.collection("users").document(reset_mail).update({"password": make_hash(new_secret_pw)})
                    st.success("已重置！")
                else: st.error("密钥验证不正确")

    else:
        st.write(f"你好, **{st.session_state.get('user_nickname', '用户')}**")
        if st.button("👋 退出"):
            st.session_state.update({'logged_in': False, 'user_role': 'guest'})
            st.rerun()

    st.markdown("---")
    st.markdown('<div class="sidebar-title">🔍 检索中心</div>', unsafe_allow_html=True)
    f_title = st.text_input("📖 书名")
    f_ar = st.slider("📊 ATOS 范围", 0.0, 12.0, (0.0, 12.0))
    f_word = st.number_input("📝 最小词数", 0)

# ==========================================
# 6. 主视图逻辑
# ==========================================
if st.session_state.bk_focus is not None:
    # 详情页逻辑
    row = df.iloc[st.session_state.bk_focus]
    title_key = str(row.iloc[idx['title']])
    if st.button("⬅️ 返回列表"): st.session_state.bk_focus = None; st.rerun()
    
    st.title(f"《{title_key}》")
    # 内容渲染...
    st.write(f"**推荐理由 ({st.session_state.lang_mode}):**")
    b_cn, b_en = st.columns(2)
    if b_cn.button("中文理由"): st.session_state.lang_mode = "CN"; st.rerun()
    if b_en.button("English"): st.session_state.lang_mode = "EN"; st.rerun()
    
    content = row.iloc[idx["cn"]] if st.session_state.lang_mode == "CN" else row.iloc[idx["en"]]
    st.info(content)

    st.subheader("💬 留言互动")
    if st.session_state.logged_in:
        with st.form("comment_form"):
            new_msg = st.text_area("分享你的读后感")
            if st.form_submit_button("发布") and new_msg:
                db.collection("comments").add({
                    "book": title_key, "text": new_msg, 
                    "user": st.session_state.user_nickname, "time": datetime.now().strftime("%Y-%m-%d")
                })
                st.rerun()
    else: st.warning("游客不可留言，请登录。")
    
    # 显示留言
    if db:
        msgs = db.collection("comments").where("book", "==", title_key).stream()
        for m in msgs:
            d = m.to_dict()
            st.markdown(f"<div class='comment-box'><b>{d['user']}</b> ({d['time']}):<br>{d['text']}</div>", unsafe_allow_html=True)

elif not df.empty:
    # 盲盒选书
    if st.button("🎁 开启选书盲盒", use_container_width=True):
        st.session_state.blind_idx = df.sample(1).index[0]
        st.balloons()
    
    if st.session_state.blind_idx is not None:
        b_row = df.iloc[st.session_state.blind_idx]
        st.markdown(f'<div class="blind-box-container"><h3>《{b_row.iloc[idx["title"]]}》</h3></div>', unsafe_allow_html=True)
        if st.button("查看盲盒详情"):
            st.session_state.bk_focus = st.session_state.blind_idx; st.rerun()

    # 列表筛选
    f_df = df[(df.iloc[:, idx['ar']] >= f_ar[0]) & (df.iloc[:, idx['ar']] <= f_ar[1]) & (df.iloc[:, idx['word']] >= f_word)]
    if f_title: f_df = f_df[f_df.iloc[:, idx['title']].str.contains(f_title, case=False)]

    cols = st.columns(3)
    for i, (orig_idx, row) in enumerate(f_df.iterrows()):
        with cols[i % 3]:
            t = row.iloc[idx['title']]
            st.markdown(f"""
                <div class="book-tile">
                    <div class="tile-title">《{t}》</div>
                    <div class="tag-container">
                        <span class="tag tag-ar">AR {row.iloc[idx['ar']]}</span>
                        <span class="tag tag-word">{row.iloc[idx['word']]}字</span>
                    </div>
                </div>
            """, unsafe_allow_html=True)
            
            c1, c2 = st.columns(2)
            # 游客可以点赞
            if c1.button("❤️" if t in st.session_state.voted else "🤍", key=f"v_{orig_idx}"):
                if t in st.session_state.voted: st.session_state.voted.remove(t)
                else: st.session_state.voted.add(t)
                st.rerun()
            if c2.button("详情", key=f"d_{orig_idx}"):
                st.session_state.bk_focus = orig_idx; st.rerun()
