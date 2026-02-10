import streamlit as st
import pandas as pd
from datetime import datetime
from google.cloud import firestore
from google.oauth2 import service_account
import requests
import json

# ==========================================
# 0. 基本配置
# ==========================================
st.set_page_config(page_title="智慧书库·全能旗舰版", layout="wide")

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
    .blind-box-container {
        background: white; border: 4px solid #ff6e40; border-radius: 20px; padding: 30px;
        text-align: center; box-shadow: 0 10px 25px rgba(255,110,64,0.15); margin: 15px 0;
    }
    .info-card { background: white; padding: 15px; border-radius: 12px; border-left: 6px solid #ff6e40; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 0.1 Firebase Web API 相关（邮箱+密码登录）
# ==========================================
# 这些密钥你需要在 .streamlit/secrets.toml 里配置，下面步骤有说明。[web:3][web:12][web:16]
FIREBASE_API_KEY = st.secrets["firebase"]["api_key"]          # Web API Key
FIREBASE_PROJECT_ID = st.secrets["firebase"]["project_id"]    # 项目 ID

FIREBASE_AUTH_BASE = "https://identitytoolkit.googleapis.com/v1/accounts"

def firebase_signup(email: str, password: str):
    """使用 Firebase Auth 注册新用户。[web:14][web:6]"""
    url = f"{FIREBASE_AUTH_BASE}:signUp?key={FIREBASE_API_KEY}"
    payload = {"email": email, "password": password, "returnSecureToken": True}
    r = requests.post(url, json=payload)
    return r

def firebase_signin(email: str, password: str):
    """使用 Firebase Auth 登录。[web:14][web:6]"""
    url = f"{FIREBASE_AUTH_BASE}:signInWithPassword?key={FIREBASE_API_KEY}"
    payload = {"email": email, "password": password, "returnSecureToken": True}
    r = requests.post(url, json=payload)
    return r

def firebase_send_verification(id_token: str):
    """发送邮箱验证邮件。[web:6][web:16]"""
    url = f"{FIREBASE_AUTH_BASE}:sendOobCode?key={FIREBASE_API_KEY}"
    payload = {"requestType": "VERIFY_EMAIL", "idToken": id_token}
    r = requests.post(url, json=payload)
    return r

def firebase_get_user_info(id_token: str):
    """用 idToken 获取用户信息（是否验证邮箱等）。[web:6]"""
    url = f"{FIREBASE_AUTH_BASE}:lookup?key={FIREBASE_API_KEY}"
    payload = {"idToken": id_token}
    r = requests.post(url, json=payload)
    return r

# ==========================================
# 0.2 角色映射：owner / admin / user / guest
# ==========================================
ROLE_MAP = {
    "your_owner_email@example.com": "owner",   # TODO: 换成你的邮箱
    "admin1@example.com": "admin",
    "admin2@example.com": "admin",
}

def get_role(email: str | None) -> str:
    if not email:
        return "guest"
    email = email.lower()
    if email in ROLE_MAP:
        return ROLE_MAP[email]
    return "user"

# 初始化登录状态
for key in ["user_email", "user_nickname", "role", "id_token"]:
    if key not in st.session_state:
        st.session_state[key] = None

# ==========================================
# 1. Firestore 客户端
# ==========================================
@st.cache_resource
def get_db_client():
    """连接 Firestore 数据库（使用服务账号 JSON）。[web:6]"""
    try:
        key_dict = st.secrets["firestore"]
        creds = service_account.Credentials.from_service_account_info(key_dict)
        return firestore.Client(credentials=creds, project=key_dict["project_id"])
    except Exception as e:
        st.error(f"无法读取 Firestore Secrets: {e}")
        return None

db = get_db_client()

def load_db_comments(book_title: str):
    """从云端读取留言。"""
    if db is None:
        return []
    try:
        col_ref = db.collection("comments").where("book", "==", book_title)
        try:
            docs = col_ref.order_by("timestamp", direction=firestore.Query.DESCENDING).stream()
            return [{"id": d.id, **d.to_dict()} for d in docs]
        except Exception:
            docs = col_ref.stream()
            comments = [{"id": d.id, **d.to_dict()} for d in docs]
            return sorted(comments, key=lambda x: x.get("time", ""), reverse=True)
    except Exception as e:
        st.sidebar.warning(f"数据库访问受限: {e}")
        return []

def save_db_comment(book_title: str, text: str, comment_id: str | None = None):
    """保存留言至云端，附带作者信息和角色。"""
    if db is None:
        return
    data = {
        "book": book_title,
        "text": text,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "timestamp": firestore.SERVER_TIMESTAMP,
        "author_email": st.session_state.get("user_email") or "guest",
        "author_name": st.session_state.get("user_nickname") or "游客",
        "author_role": st.session_state.get("role") or "guest",
    }
    try:
        if comment_id:
            db.collection("comments").document(comment_id).update(data)
        else:
            db.collection("comments").add(data)
        st.toast("✅ 留言已同步至云端", icon="☁️")
    except Exception as e:
        st.error(f"保存失败: {e}")

def delete_db_comment(comment_id: str):
    if db is None:
        return
    try:
        db.collection("comments").document(comment_id).delete()
        st.toast("🗑 已删除留言", icon="🗑")
    except Exception as e:
        st.error(f"删除失败: {e}")

# ==========================================
# 2. 图书数据（Google Sheet CSV）
# ==========================================
CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTTIN0pxN-TYH1-_Exm6dfsUdo7SbnqVnWvdP_kqe63PkSL8ni7bH6r6c86MLUtf_q58r0gI2Ft2460/pub?output=csv"

@st.cache_data(ttl=600)
def load_data():
    try:
        df = pd.read_csv(CSV_URL)
        c = {"title": 3, "author": 4, "il": 1, "ar": 5, "quiz": 7, "word": 8, "en": 10, "cn": 12, "fnf": 14, "topic": 15, "series": 16, "rec": 2}
        df.iloc[:, c["ar"]] = pd.to_numeric(
            df.iloc[:, c["ar"]].astype(str).str.extract(r"(\d+\.?\d*)")[0],
            errors="coerce"
        ).fillna(0.0)
        df.iloc[:, c["word"]] = pd.to_numeric(df.iloc[:, c["word"]], errors="coerce").fillna(0).astype(int)
        return df.fillna(" "), c
    except:
        return pd.DataFrame(), {}

df, idx = load_data()

# 初始化状态
for key in ["bk_focus", "lang_mode", "voted", "edit_id", "edit_doc_id", "blind_idx", "temp_comment", "form_version"]:
    if key not in st.session_state:
        if key == "lang_mode":
            st.session_state[key] = "CN"
        elif key == "voted":
            st.session_state[key] = set()
        elif key == "temp_comment":
            st.session_state[key] = ""
        elif key == "form_version":
            st.session_state[key] = 0
        else:
            st.session_state[key] = None

# ==========================================
# 3. 侧边栏：登录 / 注册 + 检索条件
# ==========================================
with st.sidebar:
    # 顶部 logo
    try:
        st.image("YDRC-logo.png", use_container_width=True)
    except:
        pass

    # 登录区
    st.markdown('<div class="sidebar-title">👤 身份 / 登录</div>', unsafe_allow_html=True)

    if st.session_state["user_email"]:
        st.success(f"当前身份：{st.session_state['role']}（{st.session_state['user_nickname'] or st.session_state['user_email']}）")
        if st.button("退出登录"):
            st.session_state["user_email"] = None
            st.session_state["user_nickname"] = None
            st.session_state["role"] = "guest"
            st.session_state["id_token"] = None
            st.rerun()
    else:
        tab_login, tab_signup = st.tabs(["登录", "注册"])
        with tab_login:
            email = st.text_input("邮箱", key="login_email")
            pwd = st.text_input("密码", type="password", key="login_pwd")
            if st.button("登录"):
                if not email or not pwd:
                    st.warning("请填写邮箱和密码")
                else:
                    r = firebase_signin(email, pwd)
                    if r.status_code != 200:
                        st.error(f"登录失败：{r.json().get('error', {}).get('message', '未知错误')}")
                    else:
                        data = r.json()
                        id_token = data["idToken"]
                        info_res = firebase_get_user_info(id_token)
                        info = info_res.json()
                        user_info = info["users"][0]
                        if not user_info.get("emailVerified", False):
                            st.warning("邮箱尚未验证，请先到邮箱点击验证链接。")
                        else:
                            st.session_state["user_email"] = user_info["email"]
                            st.session_state["user_nickname"] = user_info.get("displayName") or user_info["email"].split("@")[0]
                            st.session_state["role"] = get_role(user_info["email"])
                            st.session_state["id_token"] = id_token
                            st.experimental_rerun()

        with tab_signup:
            email_s = st.text_input("注册邮箱", key="signup_email")
            pwd_s = st.text_input("密码（至少6位）", type="password", key="signup_pwd")
            nickname_s = st.text_input("昵称（可选）", key="signup_nick")
            if st.button("注册"):
                if not email_s or not pwd_s:
                    st.warning("请填写邮箱和密码")
                else:
                    r = firebase_signup(email_s, pwd_s)
                    if r.status_code != 200:
                        st.error(f"注册失败：{r.json().get('error', {}).get('message', '未知错误')}")
                    else:
                        data = r.json()
                        id_token = data["idToken"]
                        vr = firebase_send_verification(id_token)
                        if vr.status_code == 200:
                            st.success("注册成功！已发送验证邮件，请到邮箱点击链接完成验证，然后再回来登录。")
                        else:
                            st.warning("注册成功，但发送验证邮件失败，请稍后在 Firebase 控制台检查。")

    st.markdown('<div class="sidebar-title">🔍 检索中心</div>', unsafe_allow_html=True)
    f_fuzzy = st.text_input("💡 智能模糊检索", placeholder="输入关键词...")
    st.write("---")
    f_title = st.text_input("📖 书名 (Title)")
    f_author = st.text_input("👤 作者 (Author)")
    f_fnf = st.selectbox("📚 类型", ["全部", "Fiction", "Nonfiction"])
    f_il = st.selectbox("🎯 Interest Level", ["全部"] + (sorted(df.iloc[:, idx["il"]].unique().tolist()) if not df.empty else []))
    f_word = st.number_input("📝 最小词数", min_value=0, step=100)
    f_quiz = st.text_input("🔢 AR Quiz Number")
    f_series = st.text_input("🔗 系列 (Series)")
    f_topic = st.text_input("🏷️ 主题 (Topic)")
    st.write("---")
    f_ar = st.slider("📊 ATOS Book Level 范围", 0.0, 12.0, (0.0, 12.0))

# 确保 role 至少是 guest
if not st.session_state["role"]:
    st.session_state["role"] = "guest"

# ==========================================
# 4. 图书详情页（带留言权限控制）
# ==========================================
if st.session_state.bk_focus is not None and not df.empty:
    row = df.iloc[st.session_state.bk_focus]
    title_key = str(row.iloc[idx["title"]])

    if st.button("⬅️ 返回图书墙"):
        st.session_state.bk_focus = None
        st.session_state.edit_id = None
        st.session_state.edit_doc_id = None
        st.session_state.temp_comment = ""
        st.rerun()

    st.markdown(f"# 📖 {title_key}")

    c1, c2, c3 = st.columns(3)
    infos = [
        ("👤 作者", row.iloc[idx["author"]]),
        ("📚 类型", row.iloc[idx["fnf"]]),
        ("🎯 Interest Level", row.iloc[idx["il"]]),
        ("📊 ATOS Book Level", row.iloc[idx["ar"]]),
        ("🔢 Quiz No.", row.iloc[idx["quiz"]]),
        ("📝 词数", f"{row.iloc[idx['word']]:,}"),
        ("🔗 系列", row.iloc[idx["series"]]),
        ("🏷️ 主题", row.iloc[idx["topic"]]),
        ("🙋 推荐人", row.iloc[idx["rec"]]),
    ]
    for i, (l, v) in enumerate(infos):
        with [c1, c2, c3][i % 3]:
            st.markdown(f'<div class="info-card"><small>{l}</small><br><b>{v}</b></div>', unsafe_allow_html=True)

    st.write("#### 🌟 推荐详情")
    lb1, lb2, _ = st.columns([1, 1, 2])
    if lb1.button("CN 中文理由", use_container_width=True):
        st.session_state.lang_mode = "CN"; st.rerun()
    if lb2.button("US English", use_container_width=True):
        st.session_state.lang_mode = "EN"; st.rerun()
    st.markdown(
        f'<div style="background:#fffcf5; padding:25px; border-radius:15px; border:2px dashed #ff6e40;">'
        f'{row.iloc[idx["cn"]] if st.session_state.lang_mode=="CN" else row.iloc[idx["en"]]}</div>',
        unsafe_allow_html=True
    )

    st.markdown("---")
    st.subheader("💬 读者感悟 (云端实时同步)")

    cloud_comments = load_db_comments(title_key)
    role = st.session_state.get("role", "guest")
    current_email = (st.session_state.get("user_email") or "").lower()

    # 显示留言 + 编辑 / 删除 权限
    for i, m in enumerate(cloud_comments):
        author = m.get("author_name", "匿名")
        author_email = (m.get("author_email") or "").lower()
        st.markdown(
            f'<div class="comment-box"><small>📅 {m.get("time")} | ✍️ {author}</small><br>{m.get("text")}</div>',
            unsafe_allow_html=True
        )

        can_edit = (
            role in ["owner", "admin"] or
            (role == "user" and author_email and author_email == current_email)
        )

        cols_btn = st.columns(3)
        if can_edit and st.session_state.edit_id is None:
            if cols_btn[0].button("✏️ 修改", key=f"e_btn_{i}"):
                st.session_state.edit_id = i
                st.session_state.edit_doc_id = m["id"]
                st.session_state.temp_comment = m["text"]
                st.session_state.form_version += 1
                st.rerun()

        # 只有 owner/admin 可以删除
        if role in ["owner", "admin"]:
            if cols_btn[1].button("🗑 删除", key=f"del_btn_{i}"):
                delete_db_comment(m["id"])
                st.rerun()

    is_editing = st.session_state.edit_id is not None
    input_key = f"input_area_v{st.session_state.form_version}"

    if st.session_state["role"] == "guest":
        st.info("登录并完成邮箱验证后即可发表读书感悟与互动留言。")
    else:
        with st.form("comment_form", clear_on_submit=False):
            st.write("✍️ " + ("修改留言" if is_editing else "发表感悟"))
            user_input = st.text_area("内容", value=st.session_state.temp_comment, key=input_key)

            cb1, cb2, _ = st.columns([1, 1, 4])
            if cb1.form_submit_button("发布" if not is_editing else "保存"):
                if user_input.strip():
                    save_db_comment(title_key, user_input, st.session_state.get("edit_doc_id") if is_editing else None)
                    st.session_state.edit_id = None
                    st.session_state.edit_doc_id = None
                    st.session_state.temp_comment = ""
                    st.session_state.form_version += 1
                    st.rerun()
                else:
                    st.warning("内容不能为空")

            if is_editing:
                if cb2.form_submit_button("❌ 取消"):
                    st.session_state.edit_id = None
                    st.session_state.edit_doc_id = None
                    st.session_state.temp_comment = ""
                    st.session_state.form_version += 1
                    st.rerun()

# ==========================================
# 5. 主视图（检索 + 图书墙 + 收藏）
# ==========================================
elif not df.empty:
    # 应用检索条件
    f_df = df.copy()
    if f_fuzzy:
        f_df = f_df[f_df.apply(lambda r: f_fuzzy.lower() in str(r.values).lower(), axis=1)]
    if f_title:
        f_df = f_df[f_df.iloc[:, idx["title"]].astype(str).str.contains(f_title, case=False)]
    if f_author:
        f_df = f_df[f_df.iloc[:, idx["author"]].astype(str).str.contains(f_author, case=False)]
    if f_fnf != "全部":
        f_df = f_df[f_df.iloc[:, idx["fnf"]] == f_fnf]
    if f_il != "全部":
        f_df = f_df[f_df.iloc[:, idx["il"]] == f_il]
    if f_quiz:
        f_df = f_df[f_df.iloc[:, idx["quiz"]].astype(str).str.contains(f_quiz)]
    if f_series:
        f_df = f_df[f_df.iloc[:, idx["series"]].astype(str).str.contains(f_series, case=False)]
    if f_topic:
        f_df = f_df[f_df.iloc[:, idx["topic"]].astype(str).str.contains(f_topic, case=False)]
    f_df = f_df[
        (f_df.iloc[:, idx["ar"]] >= f_ar[0]) &
        (f_df.iloc[:, idx["ar"]] <= f_ar[1]) &
        (f_df.iloc[:, idx["word"]] >= f_word)
    ]

    tab1, tab2, tab3 = st.tabs(["📚 图书海报墙", "📊 分级分布统计", "🏆 读者高赞榜单"])

    with tab1:
        if st.button("🎁 开启选书盲盒", use_container_width=True):
            st.balloons()
            st.session_state.blind_idx = f_df.sample(1).index[0] if not f_df.empty else df.sample(1).index[0]
        if st.session_state.blind_idx is not None:
            b_row = df.iloc[st.session_state.blind_idx]
            _, b_col, _ = st.columns([1, 2, 1])
            with b_col:
                st.markdown(
                    f'<div class="blind-box-container"><h3>《{b_row.iloc[idx["title"]]}》</h3>'
                    f'<p>作者: {b_row.iloc[idx["author"]]}</p></div>',
                    unsafe_allow_html=True
                )
                if st.button("🚀 点击进入详情", key="blind_go", use_container_width=True):
                    st.session_state.bk_focus = st.session_state.blind_idx
                    st.rerun()

        cols = st.columns(3)
        for i, (orig_idx, row) in enumerate(f_df.iterrows()):
            with cols[i % 3]:
                t = row.iloc[idx["title"]]
                voted = t in st.session_state.voted
                st.markdown(
                    f"""
                    <div class="book-tile">
                        <div class="tile-title">《{t}》</div>
                        <div style="color:#666; font-size:0.85em; margin-bottom:10px;">{row.iloc[idx["author"]]}</div>
                        <div class="tag-container">
                            <span class="tag tag-ar">ATOS {row.iloc[idx["ar"]]}</span>
                            <span class="tag tag-word">{row.iloc[idx["word"]]:,} 字</span>
                            <span class="tag tag-fnf">{row.iloc[idx["fnf"]]}</span>
                            <span class="tag tag-quiz">Quiz No. {row.iloc[idx["quiz"]]}</span>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
                cl, cr = st.columns(2)
                if cl.button("❤️" if voted else "🤍", key=f"h_{orig_idx}", use_container_width=True):
                    if voted:
                        st.session_state.voted.remove(t)
                    else:
                        st.session_state.voted.add(t)
                    st.rerun()
                if cr.button("查看详情", key=f"d_{orig_idx}", use_container_width=True):
                    st.session_state.bk_focus = orig_idx
                    st.rerun()

    with tab2:
        st.subheader("📊 ATOS Book Level 数据分布")
        if not f_df.empty:
            st.bar_chart(f_df.iloc[:, idx["ar"]].value_counts().sort_index())

    with tab3:
        st.subheader("🏆 您最喜爱的图书")
        if st.session_state.voted:
            title_to_idx = {str(row.iloc[idx["title"]]): i for i, row in df.iterrows()}
            for b_name in st.session_state.voted:
                col_n, col_b = st.columns([3, 1])
                with col_n:
                    st.markdown(f"⭐ **{b_name}**")
                with col_b:
                    if b_name in title_to_idx:
                        if st.button("查看详情", key=f"fav_{b_name}"):
                            st.session_state.bk_focus = title_to_idx[b_name]
                            st.rerun()
        else:
            st.info("暂无收藏记录，快去点击 ❤️ 吧！")

else:
    st.error("未能加载图书数据，请检查 Google Sheet 链接。")
