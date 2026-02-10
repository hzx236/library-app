# --- 留言板高级逻辑 ---

# 1. 初始化输入框状态
if "comment_input" not in st.session_state:
    st.session_state.comment_input = ""
if "editing_id" not in st.session_state:
    st.session_state.editing_id = None

st.subheader("💬 读者感悟 (公开可见)")

# 2. 循环显示留言
for m in comments:
    d = m.to_dict()
    is_author = "user" in st.session_state and st.session_state.user['nickname'] == d.get('nickname')
    is_admin = "user" in st.session_state and st.session_state.user['role'] in ['owner', 'admin']
    
    # 留言卡片 UI
    with st.container():
        st.markdown(f"""
            <div style="background: white; padding: 12px; border-radius: 8px; border-left: 5px solid #1e3d59; margin-bottom: 5px;">
                <small>📅 {d.get('time')} | 👤 {d.get('nickname')}</small><br>
                {d.get('text')}
            </div>
        """, unsafe_allow_html=True)
        
        # 按钮行：仅作者或管理员可见
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

# 3. 动态发布/修改区
if "user" in st.session_state:
    st.write("---")
    label = "✍️ 修改我的感悟" if st.session_state.editing_id else f"✍️ 以 {st.session_state.user['nickname']} 的身份留言"
    
    # 使用 key 绑定 session_state 实现自动清空
    user_text = st.text_area(label, value=st.session_state.comment_input, placeholder="分享你的阅读心得...")
    
    btn_cols = st.columns([1, 1, 8])
    
    # 发布或保存逻辑
    if st.session_state.editing_id:
        if btn_cols[0].button("保存修改", type="primary"):
            db.collection("comments").document(st.session_state.editing_id).update({
                "text": user_text,
                "time": datetime.now().strftime("%Y-%m-%d %H:%M") + " (已编辑)"
            })
            st.session_state.editing_id = None
            st.session_state.comment_input = "" # 清空
            st.rerun()
        if btn_cols[1].button("取消"):
            st.session_state.editing_id = None
            st.session_state.comment_input = ""
            st.rerun()
    else:
        if st.button("发布感悟", type="primary"):
            if user_text.strip():
                db.collection("comments").add({
                    "book": current_book,
                    "nickname": st.session_state.user['nickname'],
                    "text": user_text,
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "timestamp": firestore.SERVER_TIMESTAMP
                })
                st.session_state.comment_input = "" # 发布后立刻清空内部变量
                st.toast("✅ 发布成功！")
                st.rerun()
