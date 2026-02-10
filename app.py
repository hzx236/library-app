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
    .comment-meta { color: #888; font-size: 0.8em; margin-bottom: 5px; display: flex; justify-content: space-between;}
    .blind-box-container {
        background: white; border: 4px solid #ff6e40; border-radius: 20px; padding: 30px;
        text-align: center; box-shadow: 0 10px 25px rgba(255,110,64,0.15); margin: 15px 0;
    }
    .info-card { background: white; padding: 15px; border-radius: 12px; border-left: 6px solid #ff6e40; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    
    /* 登录状态指示 */
    .user-badge { padding: 5px 10px; border-radius: 15px; font-size: 0.8rem; font-weight: bold; margin-bottom: 10px; display: inline-block; }
    .badge-owner { background-color: #ffd700; color: #000; }
    .badge-admin { background-color: #ff6e40; color: #fff; }
    .badge-user { background-color: #2a9d8f; color: #fff; }
    .badge-guest { background-color: #ccc; color: #555; }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 数据库与安全工具
# ==========================================

@st.cache_resource
def get_db_client():
    """连接 Firestore 数据库"""
    try:
        # 必须在 .streamlit/secrets.toml 中配置 firestore 信息
        key_dict = st.secrets["firestore"]
        creds = service_account.Credentials.from_service_account_info(key_dict)
        return firestore.Client(credentials=creds, project=key_dict["project_id"])
    except Exception as e:
        # 本地测试时若无 secrets 可通过 try-except 避免直接报错，但在云端必须配置
        st.error(f"数据库连接提示: {e}")
        return None

db = get_db_client()

def make_hash(password):
    """简单的密码哈希"""
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_hashes(password, hashed_text):
    if make_hash(password) == hashed_text:
        return True
    return False

def validate_email(email):
    pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
    return re.match(pattern, email)

# ==========================================
# 3. 用户权限管理逻辑
# ==========================================

def get_user_role(email):
    """获取用户角色"""
    if db is None: return "guest"
    # Owner 邮箱在 secrets 中配置
    if email == st.secrets.get("owner_email", ""):
        return "owner"
    
    doc = db.collection("users").document(email).get()
    if doc.exists:
        return doc.to_dict().get("role", "user")
    return "guest"

def register_user(email, password, nickname):
    if db is None: return False
    try:
        doc_ref = db.collection("users").document(email)
        if doc_ref.get().exists:
            st.warning("该邮箱已被注册")
            return False
        
        role = "owner" if email == st.secrets.get("owner_email", "") else "user"
        
        doc_ref.set({
            "email": email,
            "password": make_hash(password),
            "nickname": nickname,
            "role": role,
            "created_at": firestore.SERVER_TIMESTAMP
        })
        st.success("注册成功！请登录。")
        return True
    except Exception as e:
        st.error(f"注册失败: {e}")
        return False

def login_user(email, password):
    if db is None: return None
    try:
        doc = db.collection("users").document(email).get()
        if doc.exists:
            user_data = doc.to_dict()
            if check_hashes(password, user_data['password']):
                return user_data
            else:
                st.error("密码错误")
        else:
            st.error("用户不存在")
    except Exception as e:
        st.error(f"登录错误: {e}")
    return None

# ==========================================
# 4. 数据加载 (Google Sheets)
# ==========================================
CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTTIN0pxN-TYH1-_Exm6dfsUdo7SbnqVnWvdP_kqe63PkSL8ni7bH6r6c86MLUtf_q58r0gI2Ft2460/pub?output=csv"

@st.cache_data(ttl=600)
def load_data():
    try:
        df = pd.read_csv(CSV_URL)
        # =========================================================
        # 修正列索引映射 (基于0开始计数：A=0, B=1... K=10, M=12)
        # =========================================================
        c = {
            "il": 1,        # B列: Interest Level
            "rec": 2,       # C列: 推荐人
            "title": 3,     # D列: 书名
            "author": 4,    # E列: 作者
            "ar": 5,        # F列: ATOS
            "quiz": 7,      # H列: Quiz No
            "word": 8,      # I列: Word Count
            "en": 10,       # K列: 英文推荐理由 (Index 10)
            "cn": 12,       # M列: 中文推荐理由 (Index 12)
            "fnf": 14,      # O列: Fiction/Nonfiction
            "topic": 15,    # P列: Topic
            "series": 16    # Q列: Series
        }
        
        # 数据清洗与类型转换
        # 提取 AR 数字
        df.iloc[:, c['ar']] = pd.to_numeric(
            df.iloc[:, c['ar']].astype(str).str.extract(r'(\d+\.?\d*)')[0], 
            errors='coerce'
        ).fillna(0.0)
        
        # 转换词数为整数
        df.iloc[:, c['word']] = pd.to_numeric(
            df.iloc[:, c['word']], 
            errors='coerce'
        ).fillna(0).astype(int)
        
        return df.fillna(" "), c
    except Exception as e:
        st.error(f"数据加载失败: {e}")
        return pd.DataFrame(), {}

df, idx = load_data()

# ==========================================
# 5. 初始化 Session State
# ==========================================
state_keys = {
    'bk_focus': None, 'lang_mode': 'CN', 'voted': set(), 
    'edit_id': None, 'edit_doc_id': None, 'blind_idx': None, 
    'temp_comment': "", 'form_version': 0,
    # 用户登录状态
    'logged_in': False, 'user_email': None, 'user_nickname': "游客", 'user_role': 'guest'
}

for key, val in state_keys.items():
    if key not in st.session_state:
        st.session_state[key] = val

# ==========================================
# 6. 侧边栏：登录/注册/管理
# ==========================================
with st.sidebar:
    try: st.image("YDRC-logo.png", use_container_width=True)
    except: pass
    
    st.markdown("### 👤 用户中心")
    
    if not st.session_state.logged_in:
        auth_mode = st.tabs(["登录", "注册"])
        
        with auth_mode[0]: # 登录
            l_email = st.text_input("邮箱", key="l_email")
            l_pass = st.text_input("密码", type="password", key="l_pass")
            if st.button("🚀 登录"):
                user_info = login_user(l_email, l_pass)
                if user_info:
                    st.session_state.logged_in = True
                    st.session_state.user_email = user_info['email']
                    st.session_state.user_nickname = user_info['nickname']
                    st.session_state.user_role = get_user_role(user_info['email']) 
                    st.rerun()

        with auth_mode[1]: # 注册
            r_email = st.text_input("邮箱 (作为账号)", key="r_email")
            r_nick = st.text_input("昵称 (留言显示)", key="r_nick")
            r_pass = st.text_input("密码", type="password", key="r_pass")
            if st.button("📝 注册"):
                if validate_email(r_email):
                    if len(r_pass) >= 6:
                        register_user(r_email, r_pass, r_nick)
                    else: st.warning("密码需至少6位")
                else: st.warning("请输入有效邮箱")

    else:
        # 已登录状态显示
        role_badges = {"owner": "👑 Owner", "admin": "🛡️ Admin", "user": "👤 User"}
        role_cls = f"badge-{st.session_state.user_role}"
        st.markdown(f"""
        <div class='user-badge {role_cls}'>{role_badges.get(st.session_state.user_role, 'Guest')}</div>
        <div style='font-size:1.2em'>你好, <b>{st.session_state.user_nickname}</b></div>
        """, unsafe_allow_html=True)
        
        if st.button("👋 退出登录"):
            st.session_state.logged_in = False
            st.session_state.user_email = None
            st.session_state.user_nickname = "游客"
            st.session_state.user_role = "guest"
            st.rerun()

        # --- Owner 专属管理面板 ---
        if st.session_state.user_role == 'owner':
            with st.expander("⚙️ 权限管理 (Owner Only)"):
                manage_email = st.text_input("输入用户邮箱")
                new_role = st.selectbox("设置角色", ["user", "admin"])
                if st.button("更新权限"):
                    if db:
                        try:
                            db.collection("users").document(manage_email).update({"role": new_role})
                            st.success(f"已将 {manage_email} 设为 {new_role}")
                        except Exception as e:
                            st.error(f"更新失败: {e}")

    st.write("---")
    st.markdown('<div class="sidebar-title">🔍 检索中心</div>', unsafe_allow_html=True)

# ==========================================
# 7. 评论功能逻辑
# ==========================================

def load_db_comments(book_title):
    if db is None: return []
    try:
        col_ref = db.collection("comments").where("book", "==", book_title)
        docs = col_ref.stream()
        comments = [{"id": d.id, **d.to_dict()} for d in docs]
        # 按时间排序
        return sorted(comments, key=lambda x: x.get('timestamp', str(datetime.now())), reverse=True)
    except: return []

def save_db_comment(book_title, text, comment_id=None):
    if db is None: return
    data = {
        "book": book_title,
        "text": text,
        "author_email": st.session_state.user_email,
        "author_nick": st.session_state.user_nickname,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "timestamp": firestore.SERVER_TIMESTAMP
    }
    try:
        if comment_id:
            db.collection("comments").document(comment_id).update({"text": text, "time": data["time"]})
        else:
            db.collection("comments").add(data)
        st.toast("✅ 留言已发布", icon='☁️')
    except Exception as e:
        st.error(f"保存失败: {e}")

def delete_comment(comment_id):
    if db:
        try:
            db.collection("comments").document(comment_id).delete()
            st.toast("🗑️ 留言已删除")
        except Exception as e:
            st.error(f"删除失败: {e}")

# ==========================================
# 8. 图书详情页 (主逻辑)
# ==========================================
if st.session_state.bk_focus is not None:
    row = df.iloc[st.session_state.bk_focus]
    title_key = str(row.iloc[idx['title']])
    
    if st.button("⬅️ 返回图书墙"): 
        st.session_state.bk_focus = None
        st.rerun()
    
    st.markdown(f"# 📖 {title_key}")
    
    # 详情卡片
    c1, c2, c3 = st.columns(3)
    infos = [
        ("👤 作者", row.iloc[idx['author']]), ("📚 类型", row.iloc[idx['fnf']]), ("🎯 Interest Level", row.iloc[idx['il']]), 
        ("📊 ATOS Book Level", row.iloc[idx['ar']]), ("🔢 Quiz No.", row.iloc[idx['quiz']]), ("📝 词数", f"{row.iloc[idx['word']]:,}"), 
        ("🔗 系列", row.iloc[idx['series']]), ("🏷️ 主题", row.iloc[idx['topic']]), ("🙋 推荐人", row.iloc[idx['rec']])
    ]
    for i, (l, v) in enumerate(infos):
        with [c1, c2, c3][i % 3]: st.markdown(f'<div class="info-card"><small>{l}</small><br><b>{v}</b></div>', unsafe_allow_html=True)

    st.write("#### 🌟 推荐详情")
    lb1, lb2, _ = st.columns([1,1,2])
    if lb1.button("CN 中文理由", use_container_width=True): st.session_state.lang_mode = "CN"; st.rerun()
    if lb2.button("US English", use_container_width=True): st.session_state.lang_mode = "EN"; st.rerun()
    
    # 根据 lang_mode 显示对应列内容
    content = row.iloc[idx["cn"]] if st.session_state.lang_mode=="CN" else row.iloc[idx["en"]]
    st.markdown(f'<div style="background:#fffcf5; padding:25px; border-radius:15px; border:2px dashed #ff6e40;">{content}</div>', unsafe_allow_html=True)

    st.markdown("---")
    st.subheader("💬 留言互动区")
    
    # 加载留言
    cloud_comments = load_db_comments(title_key)
    
    # 显示留言列表
    for i, m in enumerate(cloud_comments):
        is_mine = m.get('author_email') == st.session_state.user_email
        is_admin = st.session_state.user_role in ['admin', 'owner']
        
        st.markdown(f"""
        <div class="comment-box">
            <div class="comment-meta">
                <span>👤 {m.get('author_nick', '匿名用户')}</span>
                <span>📅 {m.get('time')}</span>
            </div>
            {m.get('text')}
        </div>
        """, unsafe_allow_html=True)
        
        col_ops = st.columns([1, 1, 8])
        
        # 按钮：修改 (仅本人)
        if st.session_state.logged_in and is_mine and st.session_state.edit_id is None:
            if col_ops[0].button("✏️", key=f"edit_{i}", help="修改留言"):
                st.session_state.edit_id = i
                st.session_state.edit_doc_id = m["id"]
                st.session_state.temp_comment = m["text"]
                st.session_state.form_version += 1
                st.rerun()
        
        # 按钮：删除 (本人或管理员)
        if st.session_state.logged_in and (is_mine or is_admin) and st.session_state.edit_id is None:
             if col_ops[1].button("🗑️", key=f"del_{i}", help="删除留言"):
                 delete_comment(m["id"])
                 st.rerun()

    # 留言输入框 (仅限注册/登录用户显示)
    if st.session_state.logged_in:
        is_editing = st.session_state.edit_id is not None
        input_key = f"input_area_v{st.session_state.form_version}"
        
        with st.form("comment_form", clear_on_submit=False):
            st.write("✍️ " + ("修改留言" if is_editing else f"发表留言 (作为 {st.session_state.user_nickname})"))
            user_input = st.text_area("内容", value=st.session_state.temp_comment, key=input_key)
            
            cb1, cb2, _ = st.columns([1, 1, 4])
            if cb1.form_submit_button("发布" if not is_editing else "保存"):
                if user_input.strip():
                    save_db_comment(title_key, user_input, st.session_state.get('edit_doc_id'))
                    st.session_state.edit_id = None
                    st.session_state.edit_doc_id = None
                    st.session_state.temp_comment = ""
                    st.session_state.form_version += 1
                    st.rerun()
                else: st.warning("内容不能为空")
            
            if is_editing and cb2.form_submit_button("❌ 取消"):
                st.session_state.edit_id = None; st.session_state.edit_doc_id = None
                st.session_state.temp_comment = ""; st.session_state.form_version += 1
                st.rerun()
    else:
        # 游客提示
        st.info("🔒 游客模式仅供浏览。想发表感悟或参与互动？请在左侧注册或登录。")

# ==========================================
# 9. 主视图 (筛选与图书墙)
# ==========================================
elif not df.empty:
    with st.sidebar:
        f_fuzzy = st.text_input("💡 **智能模糊检索**", placeholder="输入关键词...")
        st.write("---")
        f_title = st.text_input("📖 书名 (Title)")
        f_author = st.text_input("👤 作者 (Author)")
        f_fnf = st.selectbox("📚 类型", ["全部", "Fiction", "Nonfiction"])
        il_opts = ["全部"] + sorted([x for x in df.iloc[:, idx['il']].unique().tolist() if str(x)!="nan"])
        f_il = st.selectbox("🎯 Interest Level", il_opts)
        f_word = st.number_input("📝 最小词数", min_value=0, step=100)
        f_quiz = st.text_input("🔢 AR Quiz Number")
        f_series = st.text_input("🔗 系列 (Series)")
        f_topic = st.text_input("🏷️ 主题 (Topic)")
        st.write("---")
        f_ar = st.slider("📊 ATOS Book Level 范围", 0.0, 12.0, (0.0, 12.0))

    # 筛选逻辑
    f_df = df.copy()
    if f_fuzzy: 
        f_df = f_df[f_df.apply(lambda r: f_fuzzy.lower() in str(r.values).lower(), axis=1)]
    if f_title: f_df = f_df[f_df.iloc[:, idx['title']].astype(str).str.contains(f_title, case=False)]
    if f_author: f_df = f_df[f_df.iloc[:, idx['author']].astype(str).str.contains(f_author, case=False)]
    if f_fnf != "全部": f_df = f_df[f_df.iloc[:, idx['fnf']] == f_fnf]
    if f_il != "全部": f_df = f_df[f_df.iloc[:, idx['il']] == f_il]
    if f_quiz: f_df = f_df[f_df.iloc[:, idx['quiz']].astype(str).str.contains(f_quiz)]
    if f_series: f_df = f_df[f_df.iloc[:, idx['series']].astype(str).str.contains(f_series, case=False)]
    if f_topic: f_df = f_df[f_df.iloc[:, idx['topic']].astype(str).str.contains(f_topic, case=False)]
    f_df = f_df[(f_df.iloc[:, idx['ar']] >= f_ar[0]) & (f_df.iloc[:, idx['ar']] <= f_ar[1]) & (f_df.iloc[:, idx['word']] >= f_word)]

    tab1, tab2, tab3 = st.tabs(["📚 图书海报墙", "📊 分级分布统计", "🏆 读者高赞榜单"])
    
    with tab1:
        if st.button("🎁 开启选书盲盒", use_container_width=True):
            st.balloons()
            st.session_state.blind_idx = f_df.sample(1).index[0] if not f_df.empty else df.sample(1).index[0]
        
        if st.session_state.blind_idx is not None:
            b_row = df.iloc[st.session_state.blind_idx]
            _, b_col, _ = st.columns([1, 2, 1])
            with b_col:
                st.markdown(f'<div class="blind-box-container"><h3>《{b_row.iloc[idx["title"]]}》</h3><p>作者: {b_row.iloc[idx["author"]]}</p></div>', unsafe_allow_html=True)
                if st.button(f"🚀 点击进入详情", key="blind_go", use_container_width=True):
                    st.session_state.bk_focus = st.session_state.blind_idx; st.rerun()

        cols = st.columns(3)
        for i, (orig_idx, row) in enumerate(f_df.iterrows()):
            with cols[i % 3]:
                t = row.iloc[idx['title']]
                voted = t in st.session_state.voted
                st.markdown(f"""
                <div class="book-tile">
                    <div class="tile-title">《{t}》</div>
                    <div style="color:#666; font-size:0.85em; margin-bottom:10px;">{row.iloc[idx["author"]]}</div>
                    <div class="tag-container">
                        <span class="tag tag-ar">ATOS {row.iloc[idx["ar"]]}</span>
                        <span class="tag tag-word">{row.iloc[idx["word"]]:,} 字</span>
                        <span class="tag tag-fnf">{row.iloc[idx["fnf"]]}</span>
                        <span class="tag tag-quiz">Q: {row.iloc[idx["quiz"]]}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                cl, cr = st.columns(2)
                
                # =====================================================
                # 修改点：点赞按钮对所有用户（含游客）开放
                # =====================================================
                if cl.button("❤️" if voted else "🤍", key=f"h_{orig_idx}", use_container_width=True):
                    if voted: st.session_state.voted.remove(t)
                    else: st.session_state.voted.add(t)
                    st.rerun()
                
                if cr.button("查看详情", key=f"d_{orig_idx}", use_container_width=True):
                    st.session_state.bk_focus = orig_idx; st.rerun()

    with tab2:
        st.subheader("📊 ATOS Book Level 数据分布")
        if not f_df.empty:
            st.bar_chart(f_df.iloc[:, idx['ar']].value_counts().sort_index())

    with tab3:
        st.subheader("🏆 您最喜爱的图书")
        if st.session_state.voted:
            title_to_idx = {str(row.iloc[idx['title']]): i for i, row in df.iterrows()}
            for b_name in st.session_state.voted:
                col_n, col_b = st.columns([3, 1])
                with col_n: st.markdown(f"⭐ **{b_name}**")
                with col_b:
                    if b_name in title_to_idx:
                        if st.button("查看详情", key=f"fav_{b_name}"):
                            st.session_state.bk_focus = title_to_idx[b_name]; st.rerun()
        else: st.info("暂无收藏记录，快去点击 ❤️ 吧！")
