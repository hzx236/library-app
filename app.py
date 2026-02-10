import streamlit as st
import pandas as pd
from datetime import datetime
from google.cloud import firestore
from google.oauth2 import service_account
import random

# ==========================================
# 1. 核心 UI 配置与 CSS 锁定
# ==========================================
st.set_page_config(page_title="YDRC 智慧书库", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #fdf6e3; }
    .book-tile { background: white; padding: 20px; border-radius: 12px; border: 1px solid #e2d1b0; min-height: 350px; }
    .info-card { background: white; padding: 12px; border-radius: 10px; border-left: 5px solid #ff6e40; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    .comment-card { background: #f8f9fa; padding: 15px; border-radius: 10px; border-left: 5px solid #1e3d59; margin-bottom: 10px; }
    .blind-box-container { background: white; border: 4px solid #ff6e40; border-radius: 20px; padding: 30px; text-align: center; }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 数据库连接 (带自检逻辑)
# ==========================================
@st.cache_resource
def get_db():
    try:
        if "firestore" not in st.secrets:
            st.error("❌ 未在 Secrets 中找到 firestore 配置")
            return None
        key_dict = st.secrets["firestore"]
        creds = service_account.Credentials.from_service_account_info(key_dict)
        return firestore.Client(credentials=creds, project=key_dict["project_id"])
    except Exception as e:
        st.error(f"❌ 数据库初始化失败: {e}")
        return None

db = get_db()

# ==========================================
# 3. 数据加载 (采用列名匹配，彻底解决字段丢失)
# ==========================================
CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTTIN0pxN-TYH1-_Exm6dfsUdo7SbnqVnWvdP_kqe63PkSL8ni7bH6r6c86MLUtf_q58r0gI2Ft2460/pub?output=csv"

@st.cache_data(ttl=600)
def load_data():
    try:
        df = pd.read_csv(CSV_URL)
        # 清洗列名，去掉可能存在的空格
        df.columns = [c.strip() for c in df.columns]
        
        # 强制类型转换，防止 AR 或词数报错
        if 'AR' in df.columns:
            df['AR'] = pd.to_numeric(df['AR'].astype(str).str.extract(r'(\d+\.?\d*)')[0], errors='coerce').fillna(0.0)
        if 'WordsCount' in df.columns:
            df['WordsCount'] = pd.to_numeric(df['WordsCount'], errors='coerce').fillna(0).astype(int)
            
        return df.fillna(" ")
    except Exception as e:
        st.error(f"❌ CSV 数据加载失败: {e}")
        return pd.DataFrame()

df = load_data()

# ==========================================
# 4. 状态初始化
# ==========================================
if 'user' not in st.session_state: st.session_state.user = None
if 'bk_focus' not in st.session_state: st.session_state.bk_focus = None
if 'voted' not in st.session_state: st.session_state.voted = set()
if 'blind_idx' not in st.session_state: st.session_state.blind_idx = None

# ==========================================
# 5. 侧边栏 (修复 Logo 和登录)
# ==========================================
with st.sidebar:
    # 自查：Logo 必须在最上方
    try:
        st.image("YDRC-logo.png", use_container_width=True)
    except:
        st.title("📚 YDRC 图书馆")

    st.write("---")
    if st.session_state.user is None:
        st.subheader("🔑 成员登录")
        u_mail = st.text_input("邮箱/ID")
        u_pwd = st.text_input("密码", type="password")
        if st.button("进入系统", use_container_width=True):
            if db:
                doc = db.collection("users").document(u_mail).get()
                if doc.exists and doc.to_dict().get("password") == u_pwd:
                    st.session_state.user = {**doc.to_dict(), "id": u_mail}
                    st.rerun()
                else: st.error("账号或密码错误")
    else:
        st.success(f"你好, {st.session_state.user.get('nickname', '读者')}")
        if st.button("退出登录"):
            st.session_state.user = None
            st.rerun()

# ==========================================
# 6. 主页面：盲盒与书墙
# ==========================================
if st.session_state.bk_focus is None:
    st.title("🌟 发现下一本好书")

    # 盲盒选书大框 (自查：确保内容不留白)
    st.markdown('<div class="blind-box-container">', unsafe_allow_html=True)
    st.subheader("🎁 选书盲盒")
    if st.button("🚀 随机抽取一本"):
        st.session_state.blind_idx = random.randint(0, len(df)-1)
    
    if st.session_state.blind_idx is not None:
        b_row = df.iloc[st.session_state.blind_idx]
        st.markdown(f"### 🎊 为您选中：《{b_row['Title']}》")
        st.write(f"👤 作者: {b_row['Author']} | 🏷️ 主题: {b_row['Topic']}")
        if st.button("查看详情", key="go_blind"):
            st.session_state.bk_focus = st.session_state.blind_idx
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    # 书墙列表
    st.write("---")
    cols = st.columns(3)
    for i, (idx, row) in enumerate(df.head(12).iterrows()):
        with cols[i % 3]:
            st.markdown(f"""
                <div class="book-tile">
                    <h4>《{row['Title']}》</h4>
                    <p>👤 {row['Author']}<br>🏷️ {row['Topic']}</p>
                </div>
            """, unsafe_allow_html=True)
            if st.button("阅读感悟", key=f"dt_{idx}", use_container_width=True):
                st.session_state.bk_focus = idx
                st.rerun()

# ==========================================
# 7. 详情页 (修复所有丢失的字段和留言)
# ==========================================
else:
    row = df.iloc[st.session_state.bk_focus]
    title = str(row['Title'])
    
    if st.button("⬅️ 返回列表"):
        st.session_state.bk_focus = None
        st.rerun()

    st.header(f"📖 {title}")

    # 点赞/收藏 (自查：直接体现在界面上)
    liked = title in st.session_state.voted
    if st.button("❤️ 已收藏" if liked else "🤍 收藏本书"):
        if liked: st.session_state.voted.remove(title)
        else: st.session_state.voted.add(title)
        st.rerun()

    # 核心字段展示 (Topic, Series, Rec)
    st.write("---")
    c1, c2, c3 = st.columns(3)
    with c1: st.markdown(f'<div class="info-card"><b>主题 (Topic)</b><br>{row["Topic"]}</div>', unsafe_allow_html=True)
    with c2: st.markdown(f'<div class="info-card"><b>系列 (Series)</b><br>{row["Series"]}</div>', unsafe_allow_html=True)
    with c3: st.markdown(f'<div class="info-card"><b>推荐人 (Rec)</b><br>{row["Rec"]}</div>', unsafe_allow_html=True)

    # 留言板 (自查：采用最稳健的读取方式)
    st.subheader("💬 读者感悟")
    if db:
        try:
            # 放弃 order_by 排序以避免索引未创建导致的 400 错误
            comments = db.collection("comments").where("book", "==", title).stream()
            count = 0
            for m in comments:
                d = m.to_dict()
                st.markdown(f"""<div class="comment-card">
                    <small>{d.get('time', '未知时间')} | {d.get('nickname', '匿名')}</small><br>{d.get('text', '')}
                </div>""", unsafe_allow_html=True)
                count += 1
            if count == 0: st.info("暂无感悟，快来当第一个分享的人吧！")
        except Exception as e:
            st.warning("留言功能正在同步中...")

    # 发表感悟
    if st.session_state.user:
        st.write("---")
        new_msg = st.text_area("分享你的阅读心得...")
        if st.button("发布感悟"):
            if new_msg.strip():
                db.collection("comments").add({
                    "book": title,
                    "nickname": st.session_state.user['nickname'],
                    "text": new_msg,
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M")
                })
                st.success("发布成功！")
                st.rerun()
    else:
        st.warning("🔒 登录后即可发表阅读感悟")
