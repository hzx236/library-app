import streamlit as st
import pandas as pd
from datetime import datetime
from google.cloud import firestore
from google.oauth2 import service_account
import random

# ==========================================
# 1. 核心视觉与 UI 配置 (修正了Logo显示和布局)
# ==========================================
st.set_page_config(page_title="智慧书库·终极修复版", layout="wide")

# 加载 Logo CSS
st.markdown("""
    <style>
    .stApp { background-color: #fdf6e3; }
    [data-testid="stSidebar"] { background-color: #f0f2f6; border-right: 1px solid #e6e9ef; }
    .book-tile { background: white; padding: 20px; border-radius: 12px; border: 1px solid #e2d1b0; 
                 box-shadow: 0 4px 6px rgba(0,0,0,0.05); min-height: 380px; display: flex; flex-direction: column; }
    .tile-title { color: #1e3d59; font-size: 1.1em; font-weight: bold; margin-bottom: 5px; height: 2.8em; overflow: hidden; }
    .tag-container { margin-top: auto; display: flex; flex-wrap: wrap; gap: 5px; margin-bottom: 15px; }
    .tag { padding: 3px 8px; border-radius: 4px; font-size: 0.75em; font-weight: bold; color: white; }
    .tag-ar { background: #ff6e40; } .tag-word { background: #1e3d59; } .tag-fnf { background: #2a9d8f; }
    .comment-card { background: #f8f9fa; padding: 15px; border-radius: 10px; border-left: 5px solid #1e3d59; margin-bottom: 10px; border: 1px solid #eee; }
    .blind-box-container { background: white; border: 4px solid #ff6e40; border-radius: 20px; padding: 30px; text-align: center; box-shadow: 0 10px 25px rgba(255,110,64,0.15); margin: 15px 0; }
    .info-card { background: white; padding: 15px; border-radius: 12px; border-left: 6px solid #ff6e40; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 数据库引擎
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

# ==========================================
# 3. 数据加载与状态初始化 (修复字段映射丢失)
# ==========================================
CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTTIN0pxN-TYH1-_Exm6dfsUdo7SbnqVnWvdP_kqe63PkSL8ni7bH6r6c86MLUtf_q58r0gI2Ft2460/pub?output=csv"

@st.cache_data(ttl=600)
def load_data():
    try:
        df = pd.read_csv(CSV_URL)
        # 修复：明确定义所有字段映射，确保topic、series、rec不丢失
        c = {"title": 3, "author": 4, "il": 1, "ar": 5, "quiz": 7, "word": 8, "en": 10, "cn": 12, "fnf": 14, "topic": 15, "series": 16, "rec": 2}
        
        # 数据类型安全清洗
        df.iloc[:, c['ar']] = pd.to_numeric(df.iloc[:, c['ar']].astype(str).str.extract(r'(\d+\.?\d*)')[0], errors='coerce').fillna(0.0)
        df.iloc[:, c['word']] = pd.to_numeric(df.iloc[:, c['word']], errors='coerce').fillna(0).astype(int)
        
        return df.fillna(" "), c
    except Exception as e:
        st.error(f"数据加载失败: {e}")
        return pd.DataFrame(), {}

df, idx = load_data()

# 初始化所有核心 Session State
defaults = {
    'user': None, 'bk_focus': None, 'lang_mode': "CN", 'voted': set(),
    'editing_id': None, 'temp_comment': "", 'msg_key': 0, 'blind_idx': None
}
for k, v in defaults.items():
    if k not in st.session_state: st.session_state[k] = v

# ==========================================
# 4. 侧边栏：登录 + 复合检索中心
# ==========================================
with st.sidebar:
    # 修复：尝试加载 Logo (需要本地有文件)
    try:
        st.image("YDRC-logo.png", use_container_width=True)
    except:
        st.markdown('<div style="text-align:center; padding:10px; font-weight:bold; color:#1e3d59;">智慧书库</div>', unsafe_allow_html=True)
    
    st.markdown('<div style="color:#1e3d59; font-size:1.5em; font-weight:bold; border-bottom:2px solid #1e3d59; margin-bottom:15px;">👤 账户中心</div>', unsafe_allow_html=True)
    if st.session_state.user is None:
        e_in = st.text_input("邮箱 (ID)").strip()
        p_in = st.text_input("密码", type="password").strip()
        if st.button("登录进入"):
            if e_in and p_in:
                try:
                    user_doc = db.collection("users").document(e_in).get()
                    if user_doc.exists and user_doc.to_dict().get("password") == p_in:
                        st.session_state.user = {**user_doc.to_dict(), "email": e_in}
                        st.rerun()
                    else: st.error("账号或密码错误")
                except: st.error("登录数据库连接失败")
            else: st.warning("请输入邮箱和密码")
    else:
        u = st.session_state.user
        role_label = "👑站长" if u['role'] == 'owner' else "🛠️管理员" if u['role'] == 'admin' else "📖读者"
        st.success(f"{role_label}: {u['nickname']}")
        if st.button("退出登录"):
            st.session_state.user = None
            st.rerun()

    st.write("---")
    # --- 检索中心 ---
    st.markdown('<div style="color:#1e3d59; font-size:1.5em; font-weight:bold; border-bottom:2px solid #1e3d59; margin-bottom:15px;">🔍 检索中心</div>', unsafe_allow_html=True)
    f_fuzzy = st.text_input("💡 智能模糊搜索")
    f_title = st.text_input("📖 书名 (Title)")
    f_author = st.text_input("👤 作者 (Author)")
    f_fnf = st.selectbox("📚 类型", ["全部", "Fiction", "Nonfiction"])
    f_il = st.selectbox("🎯 Interest Level", ["全部"] + sorted(df.iloc[:, idx['il']].unique().tolist()))
    f_series = st.text_input("🔗 系列 (Series)")
    f_topic = st.text_input("🏷️ 主题 (Topic)")
    f_ar = st.slider("📊 ATOS 难度范围", 0.0, 12.0, (0.0, 12.0))

    # 过滤逻辑
    f_df = df.copy()
    if f_fuzzy: f_df = f_df[f_df.apply(lambda r: f_fuzzy.lower() in str(r.values).lower(), axis=1)]
    if f_title: f_df = f_df[f_df.iloc[:, idx['title']].astype(str).str.contains(f_title, case=False)]
    if f_author: f_df = f_df[f_df.iloc[:, idx['author']].astype(str).str.contains(f_author, case=False)]
    if f_fnf != "全部": f_df = f_df[f_df.iloc[:, idx['fnf']] == f_fnf]
    if f_il != "全部": f_df = f_df[f_df.iloc[:, idx['il']] == f_il]
    if f_series: f_df = f_df[f_df.iloc[:, idx['series']].astype(str).str.contains(f_series, case=False)]
    if f_topic: f_df = f_df[f_df.iloc[:, idx['topic']].astype(str).str.contains(f_topic, case=False)]
    f_df = f_df[(f_df.iloc[:, idx['ar']] >= f_ar[0]) & (f_df.iloc[:, idx['ar']] <= f_ar[1])]

# ==========================================
# 5. 主视图：图书海报墙与盲盒 (修复大框)
# ==========================================
if st.session_state.bk_focus is None:
    st.title("🌟 智慧书库中心")
    
    # 盲盒选书区 (修复大框显示)
    st.markdown('<div class="blind-box-container">', unsafe_allow_html=True)
    st.subheader("🎁 还没想好读什么？")
    if st.button("🚀 开启选书盲盒", use_container_width=True):
        st.balloons()
        st.session_state.blind_idx = f_df.sample(1).index[0] if not f_df.empty else df.sample(1).index[0]
    
    if st.session_state.blind_idx is not None:
        b_row = df.iloc[st.session_state.blind_idx]
        st.markdown(f"### 🎊 盲盒为您选中：《{b_row.iloc[idx['title']]}》")
        # 修复：明确显示作者和主题
        st.markdown(f"<p>👤 作者: {b_row.iloc[idx['author']]} | 🏷️ 主题: {b_row.iloc[idx['topic']]}</p>", unsafe_allow_html=True)
        if st.button("🚀 点击进入详情页", key="blind_go"):
            st.session_state.bk_focus = st.session_state.blind_idx
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    # 图书卡片展示
    cols = st.columns(3)
    for i, (orig_idx, row) in enumerate(f_df.head(24).iterrows()):
        with cols[i % 3]:
            t = row.iloc[idx['title']]
            voted = t in st.session_state.voted
            st.markdown(f"""
                <div class="book-tile">
                    <div class="tile-title">《{t}》</div>
                    <div style="color:#666; font-size:0.85em; margin-bottom:5px;">👤 {row.iloc[idx["author"]]}</div>
                    <div style="color:#666; font-size:0.85em; margin-bottom:10px;">🏷️ {row.iloc[idx["topic"]]}</div>
                    <div class="tag-container">
                        <span class="tag tag-ar">ATOS {row.iloc[idx["ar"]]}</span>
                        <span class="tag tag-word">{row.iloc[idx["word"]]:,} 字</span>
                        <span class="tag tag-fnf">{row.iloc[idx["fnf"]]}</span>
                    </div>
                </div>
            """, unsafe_allow_html=True)
            cl, cr = st.columns(2)
            # 点赞功能 (基于Session State)
            if cl.button("❤️" if voted else "🤍", key=f"vote_{orig_idx}", use_container_width=True):
                if voted: st.session_state.voted.remove(t)
                else: st.session_state.voted.add(t)
                st.rerun()
            if cr.button("查看详情", key=f"dt_{orig_idx}", use_container_width=True):
                st.session_state.bk_focus = orig_idx
                st.rerun()

# ==========================================
# 6. 图书详情页 (修复评论功能)
# ==========================================
else:
    row = df.iloc[st.session_state.bk_focus]
    title_key = str(row.iloc[idx['title']])
    
    if st.button("⬅️ 返回图书墙"):
        st.session_state.bk_focus = None
        st.session_state.editing_id = None
        st.rerun()

    st.markdown(f"# 📖 {title_key}")
    
    # --- 详情展示区 ---
    c1, c2, c3 = st.columns(3)
    # 修复：明确映射所有字段，确保 Series 和 Rec 不丢失
    info_items = [
        ("👤 作者", row.iloc[idx['author']]), 
        ("🎯 利息级别", row.iloc[idx['il']]), 
        ("📊 ATOS 难度", row.iloc[idx['ar']]), 
        ("🔢 测验编号", row.iloc[idx['quiz']]), 
        ("📝 总词数", f"{row.iloc[idx['word']]:,}"), 
        ("🏷️ 主题", row.iloc[idx['topic']]),
        ("🔗 系列", row.iloc[idx['series']]),
        ("🙋 推荐人", row.iloc[idx['rec']])
    ]
    for i, (lab, val) in enumerate(info_items):
        with [c1, c2, c3][i % 3]: 
            st.markdown(f'<div class="info-card"><small>{lab}</small><br><b>{val}</b></div>', unsafe_allow_html=True)

    # 中英文推荐理由切换
    st.write("#### 🌟 推荐感悟")
    lb1, lb2, _ = st.columns([1,1,2])
    if lb1.button("CN 中文理由", use_container_width=True): st.session_state.lang_mode = "CN"; st.rerun()
    if lb2.button("US English", use_container_width=True): st.session_state.lang_mode = "EN"; st.rerun()
    st.markdown(f'<div style="background:#fffcf5; padding:25px; border-radius:15px; border:2px dashed #ff6e40;">{row.iloc[idx["cn"]] if st.session_state.lang_mode=="CN" else row.iloc[idx["en"]]}</div>', unsafe_allow_html=True)

    st.markdown("---")
    st.subheader("💬 读者评论区 (实时同步)")

    # --- 评论区处理 (修复 failedPrecondition) ---
    if db:
        try:
            msgs_ref = db.collection("comments").where("book", "==", title_key)
            
            # 核心修复：即使索引没建好，留言也要能显示
            try:
                # 优先尝试按时间倒序
                msgs = msgs_ref.order_by("timestamp", direction=firestore.Query.DESCENDING).stream()
            except Exception:
                # 回退：普通获取（不排序），确保功能不挂掉
                msgs = msgs_ref.stream()
                st.warning("⚠️ 数据库同步中，留言显示顺序可能不准")
            
            # 渲染评论
            for m in msgs:
                d = m.to_dict()
                with st.container():
                    st.markdown(f'''
                        <div class="comment-card">
                            <small>📅 {d.get("time")} | 👤 {d.get("nickname")}</small><br>
                            {d.get("text")}
                        </div>
                    ''', unsafe_allow_html=True)
                    
                    # 权限控制：登录用户可以修改/删除自己的评论，管理员可以删除所有
                    if st.session_state.user:
                        is_me = st.session_state.user['nickname'] == d.get('nickname')
                        is_admin = st.session_state.user['role'] in ['owner', 'admin']
                        
                        b1, b2, _ = st.columns([1, 1, 8])
                        if is_me and b1.button("📝 修改", key=f"ed_{m.id}"):
                            st.session_state.editing_id = m.id
                            st.session_state.temp_comment = d.get('text')
                            st.rerun()
                        if is_me or is_admin:
                            if b2.button("🗑️ 删除", key=f"dl_{m.id}"):
                                db.collection("comments").document(m.id).delete()
                                st.toast("评论已删除")
                                st.rerun()
        except Exception as e:
            st.error(f"评论加载错误: {e}")

    # --- 发布/修改区 (修复自动清空) ---
    if st.session_state.user:
        st.write("---")
        if st.session_state.editing_id:
            st.write("✍️ **修改我的感悟**")
            edit_text = st.text_area("内容", value=st.session_state.temp_comment)
            if st.button("💾 保存修改"):
                db.collection("comments").document(st.session_state.editing_id).update({
                    "text": edit_text, 
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M") + " (已修改)"
                })
                st.session_state.editing_id = None
                st.session_state.temp_comment = ""
                st.rerun()
        else:
            st.write("✍️ **发表感悟**")
            # 强制清空逻辑：使用 msg_key 强制重置 widget
            new_msg = st.text_area("分享你的阅读心得...", key=f"msg_area_{st.session_state.msg_key}")
            if st.button("🚀 发布感悟"):
                if new_msg.strip():
                    db.collection("comments").add({
                        "book": title_key,
                        "nickname": st.session_state.user['nickname'],
                        "text": new_msg,
                        "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "timestamp": firestore.SERVER_TIMESTAMP
                    })
                    st.session_state.msg_key += 1 # 改变 key 触发清空
                    st.rerun()
    else:
        st.warning("⚠️ 登录后即可参与书籍讨论")
