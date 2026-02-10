import streamlit as st
import pandas as pd
from datetime import datetime
from google.cloud import firestore
from google.oauth2 import service_account

# --- 1. 数据库连接 ---
@st.cache_resource
def get_db():
    try:
        key_dict = st.secrets["firestore"]
        creds = service_account.Credentials.from_service_account_info(key_dict)
        return firestore.Client(credentials=creds, project=key_dict["project_id"])
    except Exception as e:
        st.error(f"连接数据库失败，请检查 Secrets 配置: {e}")
        return None

db = get_db()

# --- 2. 登录系统 (匹配你的 users 集合) ---
with st.sidebar:
    st.title("👤 账户中心")
    if "user" not in st.session_state:
        # 这里的 email 对应你 Firestore 里的 Document ID
        email = st.text_input("登录邮箱", placeholder="huizexu11@gmail.com")
        pwd = st.text_input("登录密码", type="password")
        if st.button("进入书库"):
            user_doc = db.collection("users").document(email).get()
            if user_doc.exists:
                u_data = user_doc.to_dict()
                # 匹配你设置的 password 字段
                if u_data.get("password") == pwd:
                    st.session_state.user = u_data
                    st.session_state.user['email'] = email
                    st.rerun()
                else: st.error("密码错误")
            else: st.error("未找到该用户")
    else:
        u = st.session_state.user
        role_icon = "👑" if u['role'] == 'owner' else "🛠️" if u['role'] == 'admin' else "📖"
        st.success(f"{role_icon} {u['nickname']} ({u['role']})")
        if st.button("退出登录"):
            del st.session_state.user
            st.rerun()

# --- 3. 留言板逻辑 (匹配你的 comments 集合) ---
# 建议：这里可以用 st.session_state 获取当前书籍详情页的书名
current_book = "The Mitten" # 默认展示书名

st.title(f"📚 {current_book} 读者感悟")

# 加载留言
try:
    # 尝试按你手动添加的 timestamp 排序
    comments = db.collection("comments").where("book", "==", current_book).order_by("timestamp", direction="DESCENDING").stream()
except Exception:
    # 如果索引还没建立好，则退回普通加载
    comments = db.collection("comments").where("book", "==", current_book).stream()

# 循环显示留言
for m in comments:
    d = m.to_dict()
    with st.chat_message("user"):
        st.write(f"**{d.get('nickname')}** · <small>{d.get('time')}</small>", unsafe_allow_html=True)
        st.write(d.get('text'))
        
        # 权限管理：Owner(你) 和 Admin 可以看到删除按钮
        if "user" in st.session_state:
            if st.session_state.user['role'] in ['owner', 'admin']:
                if st.button(f"🗑️ 移除", key=f"del_{m.id}"):
                    db.collection("comments").document(m.id).delete()
                    st.toast("留言已删除")
                    st.rerun()

# --- 4. 发布留言区 ---
if "user" in st.session_state:
    with st.container():
        st.write("---")
        with st.form("msg_form", clear_on_submit=True):
            input_text = st.text_area(f"以 {st.session_state.user['nickname']} 身份分享感悟...")
            if st.form_submit_button("发布感悟"):
                if input_text.strip():
                    db.collection("comments").add({
                        "book": current_book,
                        "nickname": st.session_state.user['nickname'],
                        "text": input_text,
                        "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "timestamp": firestore.SERVER_TIMESTAMP
                    })
                    st.rerun()
else:
    st.info("💡 请在左侧侧边栏登录后发表您的阅读感悟。")
