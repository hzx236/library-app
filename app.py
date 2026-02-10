import streamlit as st
import pandas as pd
from datetime import datetime
from google.cloud import firestore
from google.oauth2 import service_account

# ==========================================
# 1. 数据库连接初始化
# ==========================================
@st.cache_resource
def get_db():
    try:
        key_dict = st.secrets["firestore"]
        creds = service_account.Credentials.from_service_account_info(key_dict)
        return firestore.Client(credentials=creds, project=key_dict["project_id"])
    except Exception as e:
        st.error(f"数据库连接失败，请检查 Secrets 配置: {e}")
        return None

db = get_db()

# ==========================================
# 2. Session State 初始化 (防止 NameError)
# ==========================================
if "comment_input" not in st.session_state:
    st.session_state.comment_input = ""
if "editing_id" not in st.session_state:
    st.session_state.editing_id = None

# ==========================================
# 3. 账户中心 (匹配你的 users 集合)
# ==========================================
with st.sidebar:
    st.title("👤 账户中心")
    if "user" not in st.session_state:
        email = st.text_input("登录邮箱", placeholder="huizexu11@gmail.com")
        pwd = st.text_input("登录密码", type="password")
        if st.button("进入书库"):
            user_doc = db.collection("users").document(email).get()
            if user_doc.exists:
                u_data = user_doc.to_dict()
                if u_data.get("password") == pwd:
                    st.session_state.user = u_data
                    st.session_state.user['email'] = email
                    st.rerun()
                else: st.error("密码不正确")
            else: st.error("账号不存在")
    else:
        u = st.session_state.user
        role_icon = "👑站长" if u['role'] == 'owner' else "🛠️管理员" if u['role'] == 'admin' else "📖读者"
        st.success(f"{role_icon}: {u['nickname']}")
        if st.button("退出登录"):
            del st.session_state.user
            st.session_state.comment_input = ""
            st.session_state.editing_id = None
            st.rerun()

# ==========================================
# 4. 留言板逻辑 (匹配你的 comments 集合)
# ==========================================
current_book = "The Mitten" # 可根据实际书籍详情动态修改
st.subheader(f"💬 {current_book} 读者感悟")

# --- 加载留言 ---
try:
    # 尝试带排序的查询
    comments_ref = db.collection("comments").where("book", "==", current_book).order_by("timestamp", direction="DESCENDING")
    comments = list(comments_ref.stream())
except Exception as e:
    # 兼容处理：如果没有索引，回退到无排序查询，并提示管理员
    comments_ref = db.collection("comments").where("book", "==", current_book)
    comments = list(comments_ref.stream())
    if "index" in str(e).lower():
        st.warning("⚠️ 数据库排序索引正在创建中，留言暂时按随机顺序显示。")

# --- 显示留言列表 ---
for m in comments:
    d = m.to_dict()
    # 权限判定
    is_author = "user" in st.session_state and st.session_state.user['nickname'] == d.get('nickname')
    is_admin = "user" in st.session_state and st.session_state.user['role'] in ['owner', 'admin']
    
    with st.container():
        st.markdown(f"""
            <div style="background: white; padding: 12px; border-radius: 8px; border-left: 5px solid #1e3d59; margin-bottom: 5px;">
                <small>📅 {d.get('time')} | 👤 {d.get('nickname')}</small><br>
                {d.get('text')}
            </div>
        """, unsafe_allow_html=True)
        
        # 操作按钮
        btn_cols = st.columns([1, 1, 8])
        if is_author:
            if btn_cols[0].button("📝 修改", key=f"edit_{m.id}"):
                st.session_state.editing_id = m.id
                st.session_state.comment_input = d.get('text')
                st.rerun()
        
        if is_author or is_admin:
            if btn_cols[1].button("🗑️ 删除", key=f"del_{m.id}"):
                db.collection("comments").document(m.id).delete()
                st.toast("留言已移除")
                st.rerun()

# ==========================================
# 5. 动态发布/编辑区 (实现自动清空)
# ==========================================
if "user" in st.session_state:
    st.write("---")
    edit_mode = st.session_state.editing_id is not None
    label = "✍️ 修改我的感悟" if edit_mode else f"✍️ 以 {st.session_state.user['nickname']} 身份留言"
    
    # 输入框：手动输入内容
    user_text = st.text_area(label, value=st.session_state.comment_input, placeholder="分享你的心得...")
    
    act_cols = st.columns([1, 1, 8])
    if edit_mode:
        if act_cols[0].button("保存修改", type="primary"):
            db.collection("comments").document(st.session_state.editing_id).update({
                "text": user_text,
                "time": datetime.now().strftime("%Y-%m-%d %H:%M") + " (已编辑)"
            })
            st.session_state.editing_id = None
            st.session_state.comment_input = ""
            st.rerun()
        if act_cols[1].button("取消"):
            st.session_state.editing_id = None
            st.session_state.comment_input = ""
            st.rerun()
    else:
        if act_cols[0].button("发布感悟", type="primary"):
            if user_text.strip():
                db.collection("comments").add({
                    "book": current_book,
                    "nickname": st.session_state.user['nickname'],
                    "text": user_text,
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "timestamp": firestore.SERVER_TIMESTAMP
                })
                # 清空输入并刷新
                st.session_state.comment_input = ""
                st.toast("✅ 发布成功！")
                st.rerun()
else:
    st.info("💡 请先在左侧登录账户，即可发表阅读感悟。")
