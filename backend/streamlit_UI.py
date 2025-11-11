import streamlit as st
import requests
import pandas as pd
import time

# -------------------------
# 🎨 Page and Style Settings
# -------------------------
st.set_page_config(
    page_title="🏠 Tenant Chatbot Frontend",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# -------------------------
# 💅 Classic Chat UI Styling
# -------------------------
st.markdown("""
<style>
body {background-color: #f7f7f8;}
.main-header {font-size: 2.2rem;color: #2c3e50;text-align: center;margin-bottom: 1.2rem;font-weight: 600;}
.chat-message {padding: 0.9rem 1.1rem;border-radius: 1rem;margin: 0.4rem 0;line-height: 1.6;max-width: 85%;word-wrap: break-word;font-size: 1rem;box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);}
.assistant-message {background-color: #f1f3f4;border: 1px solid #e0e0e0;align-self: flex-start;margin-left: 0.3rem;color: #2c2c2c;}
.user-message {background-color: #e9f2ff;border: 1px solid #d6e6ff;align-self: flex-end;margin-right: 0.3rem;color: #1a1a1a;}
</style>
""", unsafe_allow_html=True)

# -------------------------
# 🌐 Backend API Endpoints
# -------------------------
API_CHAT_URL = "http://127.0.0.1:8000/chat"
API_USER_URL = "http://127.0.0.1:8000/user"
API_REGISTER_URL = "http://127.0.0.1:8000/register"
API_UPLOAD_URL = "http://127.0.0.1:8000/upload"
API_FEEDBACK_URL = "http://127.0.0.1:8000/feedback"

# -------------------------
# Initialize Session State
# -------------------------
for key, value in {
    "messages": [],
    "logged_in": False,
    "user_info": {},
    "contract_summary": None,
    "contract_uploaded": False,
    "show_feedback_box": False,
}.items():
    st.session_state.setdefault(key, value)


# ======================================================
# ⭐ Login / Register UI
# ======================================================
def show_login_page():
    st.markdown("## 🏠 Tenant Assistant")
    mode = st.radio("Select:", ["Login", "Register"], horizontal=True)

    if mode == "Login":
        email = st.text_input("📧 Email Address")
        if st.button("Login"):
            res = requests.get(API_USER_URL, params={"email": email})
            if res.status_code == 200:
                st.session_state.user_info = res.json()
                st.session_state.logged_in = True
                st.rerun()
            else:
                st.error("User not found.")

    else:
        name = st.text_input("👤 Full Name")
        email = st.text_input("📨 Email")
        if st.button("Register"):
            res = requests.post(API_REGISTER_URL, data={"tenant_id": email, "user_name": name})
            if res.status_code == 200:
                st.session_state.user_info = {"user_id": email, "name": name}
                st.session_state.logged_in = True
                st.rerun()
            else:
                st.error("Registration failed.")


if not st.session_state.logged_in:
    show_login_page()
    st.stop()


# ======================================================
# Sidebar
# ======================================================
with st.sidebar:
    st.header("🔧 Settings")
    st.success(f"👋 Hello, {st.session_state.user_info.get('name','User')}!")

    if st.button("Logout"):
        st.session_state.clear()
        st.rerun()

    st.markdown("---")
    st.subheader("📄 Upload Contract PDF")

    uploaded_file = st.file_uploader("Select PDF", type=["pdf"])

    if uploaded_file and not st.session_state.contract_uploaded:
        with st.spinner("📚 Processing your contract..."):
            res = requests.post(API_UPLOAD_URL,
                                data={"tenant_id": st.session_state.user_info["user_id"]},
                                files={"file": uploaded_file})
            if res.status_code == 200:
                st.session_state.contract_summary = res.json().get("summary")
                st.session_state.contract_uploaded = True
                st.success("✅ Contract processed!")
                st.rerun()
            else:
                st.error("❌ Upload failed.")

    elif uploaded_file and st.session_state.contract_uploaded:
        st.info("✅ Contract already uploaded — no reprocessing.")

    st.markdown("---")
    if st.button("🗑️ Clear Chat History"):
        st.session_state.messages = []
        st.success("Done!")


# ======================================================
# Main Header
# ======================================================
st.markdown('<h1 class="main-header">🏠 Tenant Chatbot Assistant</h1>', unsafe_allow_html=True)

# ======================================================
# Show Contract Summary
# ======================================================
if st.session_state.contract_summary:
    st.markdown("### 📘 Contract Summary")
    st.json(st.session_state.contract_summary)
    st.markdown("---")

# ======================================================
# Chat History
# ======================================================
for idx, msg in enumerate(st.session_state.messages):
    bubble = "user-message" if msg["role"] == "user" else "assistant-message"
    st.markdown(
        f'<div class="chat-message {bubble}"><strong>{"👤 You" if msg["role"]=="user" else "🤖 Assistant"}:</strong><br>{msg["content"]}</div>',
        unsafe_allow_html=True,
    )

    # --- Feedback for assistant messages ---
    if msg["role"] == "assistant":
        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button("👍", key=f"like_{idx}"):
                requests.post(API_FEEDBACK_URL, data={
                    "tenant_id": st.session_state.user_info["user_id"],
                    "query": st.session_state.messages[idx-1]["content"],
                    "response": msg["content"],
                    "rating": 1
                })
                st.toast("👍 Thanks!", icon="👍")

        with col2:
            if st.button("👎", key=f"dislike_{idx}"):
                st.session_state.show_feedback_box = idx

        # Textbox appears *below the message* only when needed
        if st.session_state.show_feedback_box == idx:
            comment = st.text_area("How can we improve?", key=f"fb_{idx}")
            if st.button("Submit Feedback", key=f"submit_{idx}"):
                requests.post(API_FEEDBACK_URL, data={
                    "tenant_id": st.session_state.user_info["user_id"],
                    "query": st.session_state.messages[idx-1]["content"],
                    "response": msg["content"],
                    "rating": -1,
                    "comment": comment
                })
                st.session_state.show_feedback_box = False
                st.toast("💬 Feedback submitted!", icon="✅")


# ======================================================
# Chat Input
# ======================================================
user_input = st.chat_input("Type your message here...")

if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.spinner("🤔 Thinking..."):
        res = requests.post(API_CHAT_URL, data={
            "tenant_id": st.session_state.user_info["user_id"],
            "message": user_input
        })
        reply = res.json().get("reply", "...")
        st.session_state.messages.append({"role": "assistant", "content": reply})
    st.rerun()
