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
        st.error(f"连接数据库失败: {e}")
        return None

db = get_db()

# --- 2. 初始化 Session State (修复 NameError 的关键) ---
if "comment_input" not in st.session_state:
    st.session_state.comment_input = ""
if "editing_id" not in st.session_state:
    st.session_state.editing_id = None

# --- 3. 登录系统 ---
with st.sidebar:
    st.title("👤 账户中心")
    if "user" not in st.session_state:
        email = st.text_input("登录邮箱")
        pwd = st.text_input("登录密码", type="password")
        if st.button("进入书库"):
            user_doc = db.collection("users").document(email).get()
            if user_doc.exists:
                u_data = user_doc.to_dict()
                if u_data.get("password") == pwd:
                    st.session_state.user = u_data
                    st.session_state.user['email'] = email
                    st.rerun()
                else: st.error("密码错误")
            else: st.error("账号不存在")
    else:
        u = st.session_state.user
        role_tag = "👑 站长" if u['role'] == 'owner' else "🛠️ 管理员" if u['role'] == 'admin' else "📖 读者"
        st.success(f"{role_tag}: {u['nickname']}")
        if st.button("退出登录"):
            del st.session_state.user
            st.session_state.comment_input = ""
            st.session_state.editing_id = None
            st.rerun()

# --- 4. 留言板逻辑 (带有编辑功能) ---
current_book = "The Mitten" 

st.subheader(f"💬 {current_book} 读者感悟")

# 加载留言
try:
    comments = db.collection("comments").where("book", "==", current_book).order_by("timestamp", direction="DESCENDING").stream()
except Exception:
    comments = db.collection("comments").where("book", "==", current_book).stream()

for m in comments:
    d = m.to_dict()
    is_author = "user" in st.session_state and st.session_state.user['nickname'] == d.get('nickname')
    is_admin = "user" in st.session_state and st.session_state.user['role'] in ['owner', 'admin']
    
    with st.container():
        st.markdown(f"""
            <div style="background: white; padding: 12px; border-radius: 8px; border-left: 5px solid #1e3d59; margin-bottom: 5px;">
                <small>📅 {d.get('time')} | 👤 {d.get('nickname')}</small><br>
                {d.get('text')}
            </div>
        """, unsafe_allow_html=True)
        
        # 作者或管理员按钮
        cols = st.columns([1, 1, 8])
        if is_author:
            if cols[0].button("📝 修改", key=f"edit_{m.id}"):
                st.session_state.editing_id = m.id
                st.session_state.comment_input = d.get('text')
                st.rerun()
        
        if is_author or is_admin:
            if cols[1].button("🗑️ 删除", key=f"del_{m.id}"):
                db.collection("comments").document(m.id).delete()
                st.toast("留言已移除")
                st.rerun()

# --- 5. 发布/修改留言区 (实现了清空功能) ---
if "user" in st.session_state:
    st.write("---")
    
    # 标题动态显示
    title_label = "✍️ 修改我的感悟" if st.session_state.editing_id else f"✍️ 以 {st.session_state.user['nickname']} 身份留言"
    
    # 输入框绑定 session_state
    user_text = st.text_area(title_label, value=st.session_state.comment_input, placeholder="分享你的阅读心得...")
    
    btn_cols = st.columns([1, 1, 8])
    
    # 逻辑处理
    if st.session_state.editing_id:
        if btn_cols[0].button("保存修改", type="primary"):
            db.collection("comments").document(st.session_state.editing_id).update({
                "text": user_text,
                "time": datetime.now().strftime("%Y-%m-%d %H:%M") + " (已编辑)"
            })
            # 重置状态并清空
            st.session_state.editing_id = None
            st.session_state.comment_input = ""
            st.rerun()
        if btn_cols[1].button("取消"):
            st.session_state.editing_id = None
            st.session_state.comment_input = ""
            st.rerun()
    else:
        if btn_cols[0].button("发布感悟", type="primary"):
            if user_text.strip():
                db.collection("comments").add({
                    "book": current_book,
                    "nickname": st.session_state.user['nickname'],
                    "text": user_text,
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "timestamp": firestore.SERVER_TIMESTAMP
                })
                # 清空输入框
                st.session_state.comment_input = ""
                st.toast("✅ 发布成功！")
                st.rerun()
else:
    st.warning("⚠️ 请先登录后再发表感悟。")
