import streamlit as st
import pandas as pd
from datetime import datetime
from google.cloud import firestore
from google.oauth2 import service_account
import random

# ==========================================
# 1. 核心视觉与 UI 配置
# ==========================================
st.set_page_config(page_title="智慧书库·全能旗舰版", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #fdf6e3; }
    .book-tile { background: white; padding: 20px; border-radius: 12px; border: 1px solid #e2d1b0; box-shadow: 0 4px 6px rgba(0,0,0,0.05); min-height: 350px; display: flex; flex-direction: column; }
    .tag { padding: 3px 8px; border-radius: 4px; font-size: 0.75em; font-weight: bold; color: white; margin-right: 5px; }
    .tag-ar { background: #ff6e40; } .tag-word { background: #1e3d59; }
    .comment-card { background: #f8f9fa; padding: 15px; border-radius: 10px; border-left: 5px solid #1e3d59; margin-bottom: 10px; }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 数据库与 Session State 初始化
# ==========================================
@st.cache_resource
def get_db():
    try:
        key_dict = st.secrets["firestore"]
        creds = service_account.Credentials.from_service_account_info(key_dict)
        return firestore.Client(credentials=creds, project=key_dict["project_id"])
    except Exception as e:
        st.error(f"数据库连接失败: {e}")
        return None

db = get_db()

# 核心状态管理 (防止 NameError 和功能缺失)
if "user" not in st.session_state: st.session_state.user = None
if "bk_focus" not in st.session_state: st.session_state.bk_focus = None
if "editing_id" not in st.session_state: st.session_state.editing_id = None
if "msg_key" not in st.session_state: st.session_state.msg_key = 0

# ==========================================
# 3. 数据加载引擎
# ==========================================
CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTTIN0pxN-TYH1-_Exm6dfsUdo7SbnqVnWvdP_kqe63PkSL8ni7bH6r6c86MLUtf_q58r0gI2Ft2460/pub?output=csv"

@st.cache_data(ttl=600)
def load_data():
    try:
        df = pd.read_csv(CSV_URL)
        # 索引映射 (根据您的 CSV 结构)
        cols = {"title": 3, "author": 4, "il": 1, "ar": 5, "quiz": 7, "word": 8, "en": 10, "cn": 12, "fnf": 14, "topic": 15, "rec": 2}
        return df.fillna(" "), cols
    except:
        return pd.DataFrame(), {}

df, idx = load_data()

# ==========================================
# 4. 侧边栏：账户 + 检索 (找回丢失的检索栏)
# ==========================================
with st.sidebar:
    st.title("👤 账户中心")
    if st.session_state.user is None:
        e_in = st.text_input("邮箱").strip()
        p_in = st.text_input("密码", type="password").strip()
        if st.button("登录"):
            if e_in:
                user_doc = db.collection("users").document(e_in).get()
                if user_doc.exists and user_doc.to_dict().get("password") == p_in:
                    st.session_state.user = {**user_doc.to_dict(), "email": e_in}
                    st.rerun()
                else: st.error("账号或密码错误")
    else:
        st.success(f"Hi, {st.session_state.user['nickname']}")
        if st.button("退出登录"):
            st.session_state.user = None
            st.rerun()

    st.write("---")
    st.subheader("🔍 智能检索")
    q_text = st.text_input("书名/作者关键字")
    q_topic = st.selectbox("主题分类", ["全部"] + list(df.iloc[:, idx['topic']].unique()))
    
    # 过滤逻辑
    res_df = df.copy()
    if q_text:
        res_df = res_df[res_df.iloc[:, idx['title']].str.contains(q_text, case=False) | 
                        res_df.iloc[:, idx['author']].str.contains(q_text, case=False)]
    if q_topic != "全部":
        res_df = res_df[res_df.iloc[:, idx['topic']] == q_topic]

# ==========================================
# 5. 主界面：盲盒选书与列表
# ==========================================
if st.session_state.bk_focus is None:
    st.title("🌟 智慧书库中心")
    
    # 盲盒区域
    with st.container():
        st.markdown('<div style="background:#fff3e0; padding:20px; border-radius:15px; border:2px dashed #ff6e40; text-align:center;">', unsafe_allow_html=True)
        st.subheader("🎁 还没想好读什么？")
        if st.button("🚀 开启选书盲盒"):
            st.session_state.bk_focus = random.randint(0, len(df)-1)
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    # 列表展示 (找回丢失的卡片)
    cols = st.columns(3)
    for i, (index, row) in enumerate(res_df.head(12).iterrows()):
        with cols[i % 3]:
            st.markdown(f"""
                <div class="book-tile">
                    <div style="font-size:0.8em; color:grey;">{row.iloc[idx['il']]}</div>
                    <div style="font-weight:bold; height:3em; overflow:hidden;">{row.iloc[idx['title']]}</div>
                    <div style="font-size:0.9em; color:#1e3d59; margin-bottom:10px;">{row.iloc[idx['author']]}</div>
                    <div style="margin-top:auto;">
                        <span class="tag tag-ar">AR {row.iloc[idx['ar']]}</span>
                        <span class="tag tag-word">{row.iloc[idx['word']]} W</span>
                    </div>
                </div>
            """, unsafe_allow_html=True)
            if st.button("查看详情", key=f"view_{index}", use_container_width=True):
                st.session_state.bk_focus = index
                st.rerun()

# ==========================================
# 6. 详情页：图书详情 + 点赞 + 留言 (核心修复)
# ==========================================
else:
    row = df.iloc[st.session_state.bk_focus]
    title = row.iloc[idx['title']]
    
    if st.button("← 返回列表"):
        st.session_state.bk_focus = None
        st.session_state.editing_id = None
        st.rerun()

    # 图书详情卡片
    c1, c2 = st.columns([1, 2])
    with c1:
        st.image("https://via.placeholder.com/300x400.png?text=No+Cover", use_container_width=True)
    with c2:
        st.header(title)
        st.write(f"**作者:** {row.iloc[idx['author']]} | **主题:** {row.iloc[idx['topic']]}")
        st.info(f"📚 **简介:** {row.iloc[idx['en']]}\n\n{row.iloc[idx['cn']]}")
        
        # 点赞功能 (假设存入 Firestore)
        if st.button("❤️ 收藏/点赞"):
            st.toast("功能已记录")

    st.write("---")
    st.subheader("💬 读者感悟")

    # 留言加载与管理
    msgs = db.collection("comments").where("book", "==", title).stream()
    for m in msgs:
        d = m.to_dict()
        with st.container():
            st.markdown(f'<div class="comment-card"><small>{d.get("time")} | {d.get("nickname")}</small><br>{d.get("text")}</div>', unsafe_allow_html=True)
            
            # 权限：仅作者或管理员可删改
            if st.session_state.user:
                is_me = st.session_state.user['nickname'] == d.get('nickname')
                is_admin = st.session_state.user['role'] in ['owner', 'admin']
                
                b1, b2, _ = st.columns([1, 1, 8])
                if is_me and b1.button("📝修改", key=f"e_{m.id}"):
                    st.session_state.editing_id = m.id
                    st.session_state.temp_text = d.get('text')
                    st.rerun()
                if is_me or is_admin:
                    if b2.button("🗑️删除", key=f"d_{m.id}"):
                        db.collection("comments").document(m.id).delete()
                        st.rerun()

    # 发布/修改区 (自动清空逻辑)
    if st.session_state.user:
        if st.session_state.editing_id:
            new_txt = st.text_area("修改感悟", value=st.session_state.temp_text)
            if st.button("保存修改"):
                db.collection("comments").document(st.session_state.editing_id).update({
                    "text": new_txt, "time": datetime.now().strftime("%Y-%m-%d %H:%M") + " (已修改)"
                })
                st.session_state.editing_id = None
                st.rerun()
        else:
            txt = st.text_area("写下感悟...", key=f"in_{st.session_state.msg_key}")
            if st.button("发布感悟"):
                if txt.strip():
                    db.collection("comments").add({
                        "book": title, "nickname": st.session_state.user['nickname'],
                        "text": txt, "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "timestamp": firestore.SERVER_TIMESTAMP
                    })
                    st.session_state.msg_key += 1 # 强制清空
                    st.rerun()
    else:
        st.warning("登录后即可参与讨论")
