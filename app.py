import streamlit as st
import pandas as pd
from datetime import datetime
from google.cloud import firestore
from google.oauth2 import service_account
import random

# ==========================================
# 1. 核心视觉与 UI 配置
# ==========================================
st.set_page_config(page_title="智慧书库·全能终极版", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #fdf6e3; }
    [data-testid="stSidebar"] { background-color: #f0f2f6; border-right: 1px solid #e6e9ef; }
    .book-tile { background: white; padding: 20px; border-radius: 12px; border: 1px solid #e2d1b0; 
                 box-shadow: 0 4px 6px rgba(0,0,0,0.05); min-height: 350px; display: flex; flex-direction: column; }
    .tile-title { color: #1e3d59; font-size: 1.1em; font-weight: bold; margin-bottom: 5px; height: 2.8em; overflow: hidden; }
    .tag-container { margin-top: auto; display: flex; flex-wrap: wrap; gap: 5px; margin-bottom: 15px; }
    .tag { padding: 3px 8px; border-radius: 4px; font-size: 0.75em; font-weight: bold; color: white; }
    .tag-ar { background: #ff6e40; } .tag-word { background: #1e3d59; } .tag-fnf { background: #2a9d8f; } .tag-quiz { background: #6d597a; }
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
# 3. 数据加载与状态初始化
# ==========================================
CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTTIN0pxN-TYH1-_Exm6dfsUdo7SbnqVnWvdP_kqe63PkSL8ni7bH6r6c86MLUtf_q58r0gI2Ft2460/pub?output=csv"

@st.cache_data(ttl=600)
def load_data():
    try:
        df = pd.read_csv(CSV_URL)
        c = {"title": 3, "author": 4, "il": 1, "ar": 5, "quiz": 7, "word": 8, "en": 10, "cn": 12, "fnf": 14, "topic": 15, "series": 16, "rec": 2}
        # 清洗 AR 和 Word 数据
        df.iloc[:, c['ar']] = pd.to_numeric(df.iloc[:, c['ar']].astype(str).str.extract(r'(\d+\.?\d*)')[0], errors='coerce').fillna(0.0)
        df.iloc[:, c['word']] = pd.to_numeric(df.iloc[:, c['word']], errors='coerce').fillna(0).astype(int)
        return df.fillna(" "), c
    except: return pd.DataFrame(), {}

df, idx = load_data()

# 初始化所有核心 Session State
states = {
    'user': None, 'bk_focus': None, 'lang_mode': "CN", 'voted': set(),
    'editing_id': None, 'temp_comment': "", 'msg_key': 0, 'blind_idx': None
}
for k, v in states.items():
    if k not in st.session_state: st.session_state[k] = v

# ==========================================
# 4. 侧边栏：登录 + 复合检索中心
# ==========================================
with st.sidebar:
    st.markdown('<div style="color:#1e3d59; font-size:1.5em; font-weight:bold; border-bottom:2px solid #1e3d59; margin-bottom:15px;">👤 账户中心</div>', unsafe_allow_html=True)
    if st.session_state.user is None:
        e_in = st.text_input("邮箱 (ID)").strip()
        p_in = st.text_input("密码", type="password").strip()
        if st.button("登录进入"):
            if e_in:
                user_doc = db.collection("users").document(e_in).get()
                if user_doc.exists and user_doc.to_dict().get("password") == p_in:
                    st.session_state.user = {**user_doc.to_dict(), "email": e_in}
                    st.rerun()
                else: st.error("账号或密码错误")
    else:
        u = st.session_state.user
        role_label = "👑站长" if u['role'] == 'owner' else "🛠️管理员" if u['role'] == 'admin' else "📖读者"
        st.success(f"{role_label}: {u['nickname']}")
        if st.button("退出登录"):
            st.session_state.user = None
            st.rerun()

    st.write("---")
    st.markdown('<div style="color:#1e3d59; font-size:1.5em; font-weight:bold; border-bottom:2px solid #1e3d59; margin-bottom:15px;">🔍 检索中心</div>', unsafe_allow_html=True)
    f_fuzzy = st.text_input("💡 智能模糊搜索")
    f_title = st.text_input("📖 书名 (Title)")
    f_author = st.text_input("👤 作者 (Author)")
    f_fnf = st.selectbox("📚 类型", ["全部", "Fiction", "Nonfiction"])
    f_il = st.selectbox("🎯 Interest Level", ["全部"] + sorted(df.iloc[:, idx['il']].unique().tolist()))
    f_word = st.number_input("📝 最小词数", min_value=0, step=500)
    f_ar = st.slider("📊 ATOS 范围", 0.0, 12.0, (0.0, 12.0))

    # 复合筛选逻辑
    f_df = df.copy()
    if f_fuzzy: f_df = f_df[f_df.apply(lambda r: f_fuzzy.lower() in str(r.values).lower(), axis=1)]
    if f_title: f_df = f_df[f_df.iloc[:, idx['title']].astype(str).str.contains(f_title, case=False)]
    if f_author: f_df = f_df[f_df.iloc[:, idx['author']].astype(str).str.contains(f_author, case=False)]
    if f_fnf != "全部": f_df = f_df[f_df.iloc[:, idx['fnf']] == f_fnf]
    if f_il != "全部": f_df = f_df[f_df.iloc[:, idx['il']] == f_il]
    f_df = f_df[(f_df.iloc[:, idx['ar']] >= f_ar[0]) & (f_df.iloc[:, idx['ar']] <= f_ar[1]) & (f_df.iloc[:, idx['word']] >= f_word)]

# ==========================================
# 5. 主视图逻辑
# ==========================================
if st.session_state.bk_focus is None:
    st.title("🌟 智慧书库中心")
    tab1, tab2, tab3 = st.tabs(["📚 图书海报墙", "📊 分级分布统计", "🏆 读者高赞榜单"])
    
    with tab1:
        # 盲盒选书区
        st.markdown('<div class="blind-box-container">', unsafe_allow_html=True)
        st.subheader("🎁 还没想好读什么？")
        if st.button("🚀 开启选书盲盒", use_container_width=True):
            st.balloons()
            st.session_state.blind_idx = f_df.sample(1).index[0] if not f_df.empty else df.sample(1).index[0]
        
        if st.session_state.blind_idx is not None:
            b_row = df.iloc[st.session_state.blind_idx]
            st.markdown(f"### 🎊 盲盒为您选中：《{b_row.iloc[idx['title']]}》")
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
                        <div style="color:#666; font-size:0.85em; margin-bottom:10px;">{row.iloc[idx["author"]]}</div>
                        <div class="tag-container">
                            <span class="tag tag-ar">ATOS {row.iloc[idx["ar"]]}</span>
                            <span class="tag tag-word">{row.iloc[idx["word"]]:,} 字</span>
                            <span class="tag tag-fnf">{row.iloc[idx["fnf"]]}</span>
                            <span class="tag tag-quiz">Quiz No. {row.iloc[idx["quiz"]]}</span>
                        </div>
                    </div>
                """, unsafe_allow_html=True)
                cl, cr = st.columns(2)
                if cl.button("❤️" if voted else "🤍", key=f"vote_{orig_idx}", use_container_width=True):
                    if voted: st.session_state.voted.remove(t)
                    else: st.session_state.voted.add(t)
                    st.rerun()
                if cr.button("查看详情", key=f"dt_{orig_idx}", use_container_width=True):
                    st.session_state.bk_focus = orig_idx
                    st.rerun()

    with tab2:
        st.subheader("📊 当前筛选书籍分级分布")
        if not f_df.empty:
            st.bar_chart(f_df.iloc[:, idx['ar']].value_counts().sort_index())
    
    with tab3:
        st.subheader("🏆 您最喜爱的图书")
        if st.session_state.voted:
            title_to_idx = {str(r.iloc[idx['title']]): i for i, r in df.iterrows()}
            for b_name in st.session_state.voted:
                col_n, col_b = st.columns([3, 1])
                col_n.markdown(f"⭐ **{b_name}**")
                if col_b.button("查看", key=f"fav_{b_name}"):
                    st.session_state.bk_focus = title_to_idx.get(b_name)
                    st.rerun()
        else: st.info("暂无收藏记录")

# ==========================================
# 6. 图书详情页 (深度整合留言管理)
# ==========================================
else:
    row = df.iloc[st.session_state.bk_focus]
    title_key = str(row.iloc[idx['title']])
    
    if st.button("⬅️ 返回图书墙"):
        st.session_state.bk_focus = None
        st.session_state.editing_id = None
        st.rerun()

    st.markdown(f"# 📖 {title_key}")
    
    # 核心信息卡片
    c1, c2, c3 = st.columns(3)
    info_items = [("👤 作者", row.iloc[idx['author']]), ("🎯 利息级别", row.iloc[idx['il']]), 
                  ("📊 ATOS 难度", row.iloc[idx['ar']]), ("🔢 测验编号", row.iloc[idx['quiz']]), 
                  ("📝 总词数", f"{row.iloc[idx['word']]:,}"), ("🏷️ 主题", row.iloc[idx['topic']])]
    for i, (lab, val) in enumerate(info_items):
        with [c1, c2, c3][i % 3]: 
            st.markdown(f'<div class="info-card"><small>{lab}</small><br><b>{val}</b></div>', unsafe_allow_html=True)

    # 中英文详情切换
    st.write("#### 🌟 推荐感悟")
    lb1, lb2, _ = st.columns([1,1,2])
    if lb1.button("CN 中文理由", use_container_width=True): st.session_state.lang_mode = "CN"; st.rerun()
    if lb2.button("US English", use_container_width=True): st.session_state.lang_mode = "EN"; st.rerun()
    st.markdown(f'<div style="background:#fffcf5; padding:25px; border-radius:15px; border:2px dashed #ff6e40;">{row.iloc[idx["cn"]] if st.session_state.lang_mode=="CN" else row.iloc[idx["en"]]}</div>', unsafe_allow_html=True)

    st.markdown("---")
    st.subheader("💬 读者评论区 (Firestore 实时同步)")

    # 留言加载逻辑 (匹配权限)
    try:
        msgs = db.collection("comments").where("book", "==", title_key).order_by("timestamp", direction=firestore.Query.DESCENDING).stream()
    except:
        msgs = db.collection("comments").where("book", "==", title_key).stream()

    for m in msgs:
        d = m.to_dict()
        with st.container():
            st.markdown(f'<div class="comment-card"><small>📅 {d.get("time")} | 👤 {d.get("nickname")}</small><br>{d.get("text")}</div>', unsafe_allow_html=True)
            
            # 权限按钮
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
                        st.toast("已删除")
                        st.rerun()

    # 发布/修改区
    if st.session_state.user:
        if st.session_state.editing_id:
            edit_text = st.text_area("修改我的感悟", value=st.session_state.temp_comment)
            if st.button("💾 保存修改"):
                db.collection("comments").document(st.session_state.editing_id).update({
                    "text": edit_text, "time": datetime.now().strftime("%Y-%m-%d %H:%M") + " (已修改)"
                })
                st.session_state.editing_id = None
                st.session_state.temp_comment = ""
                st.rerun()
        else:
            # 自动清空逻辑：使用 msg_key 强制重置 widget
            new_msg = st.text_area("撰写感悟...", key=f"msg_area_{st.session_state.msg_key}")
            if st.button("🚀 发布感悟"):
                if new_msg.strip():
                    db.collection("comments").add({
                        "book": title_key, "nickname": st.session_state.user['nickname'],
                        "text": new_msg, "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "timestamp": firestore.SERVER_TIMESTAMP
                    })
                    st.session_state.msg_key += 1
                    st.rerun()
    else:
        st.warning("⚠️ 登录后即可参与书籍讨论")
