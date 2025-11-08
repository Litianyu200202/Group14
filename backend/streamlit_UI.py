import streamlit as st
import requests
import pandas as pd
import time
import os

# -------------------------
# 🎨 Page and Style Settings
# -------------------------
st.set_page_config(
    page_title="🏠 Tenant Chatbot Frontend",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
.main-header {
    font-size: 2.2rem;
    color: #2c3e50;
    text-align: center;
    margin-bottom: 1.5rem;
}
.chat-message {
    padding: 1rem;
    border-radius: 0.6rem;
    margin: 0.5rem 0;
    line-height: 1.5;
}
.user-message {
    background-color: #e3f2fd;
    border-left: 4px solid #2196f3;
}
.assistant-message {
    background-color: #f3e5f5;
    border-left: 4px solid #9c27b0;
}
.upload-section {
    background-color: #f8f9fa;
    padding: 1rem;
    border-radius: 0.5rem;
    border: 2px dashed #dee2e6;
}
.auth-section {
    background-color: #fff3cd;
    padding: 1rem;
    border-radius: 0.5rem;
    border: 1px solid #ffeaa7;
}
</style>
""", unsafe_allow_html=True)

# -------------------------
# 🌐 Backend API Endpoints
# -------------------------
API_BASE = "http://127.0.0.1:8000"
API_CHAT_URL = f"{API_BASE}/chat"
API_USER_URL = f"{API_BASE}/user"
API_REGISTER_URL = f"{API_BASE}/register"
API_UPLOAD_URL = f"{API_BASE}/upload"
API_FEEDBACK_URL = f"{API_BASE}/feedback"
API_MAINTENANCE_URL = f"{API_BASE}/maintenance"

# -------------------------
# Initialize Session State
# -------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user_info" not in st.session_state:
    st.session_state.user_info = {}
if "contract_summary" not in st.session_state:
    st.session_state.contract_summary = None
if "show_maintenance_form" not in st.session_state:
    st.session_state.show_maintenance_form = False
if "contract_uploaded" not in st.session_state:
    st.session_state.contract_uploaded = False
if "upload_success" not in st.session_state:
    st.session_state.upload_success = False
if "show_feedback_form" not in st.session_state:
    st.session_state.show_feedback_form = False

# -------------------------
# 🏷️ Page Header
# -------------------------
st.markdown('<h1 class="main-header">🏠 Tenant Chatbot Assistant</h1>', unsafe_allow_html=True)

# -------------------------
# 🔧 Sidebar Configuration
# -------------------------
with st.sidebar:
    st.header("🔧 Settings")
    st.markdown("---")

    # Authentication
    st.markdown('<div class="auth-section">', unsafe_allow_html=True)
    st.subheader("🔐 Authentication")

    if not st.session_state.logged_in:
        email = st.text_input("Enter your email address", key="login_email")
        if st.button("Login", type="primary", key="login_btn", use_container_width=True):
            try:
                response = requests.get(API_USER_URL, params={"email": email}, timeout=10)
                data = response.json()
                if response.status_code == 200 and "user_id" in data:
                    st.session_state.logged_in = True
                    st.session_state.user_info = data
                    st.success("✅ Login successful")
                    st.rerun()
                else:
                    st.error("⚠️ User not found. Please register.")
            except Exception as e:
                st.error(f"❌ Could not connect to backend: {e}")
    else:
        st.success(f"👋 Welcome {st.session_state.user_info.get('name', 'User')}!")
        if st.button("Logout", use_container_width=True):
            st.session_state.clear()
            st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)
    st.markdown("---")

    # Upload Section
    st.subheader("📄 Upload Contract PDF")
    st.markdown('<div class="upload-section">', unsafe_allow_html=True)

    uploaded_file = st.file_uploader("Choose PDF", type=["pdf"])

    if uploaded_file:
        if st.button("🚀 Upload and Process", type="primary", use_container_width=True):
            tenant_id = st.session_state.user_info.get("user_id", "Guest")
            files = {"file": (uploaded_file.name, uploaded_file.getvalue(), "application/pdf")}
            data = {"tenant_id": tenant_id}
            res = requests.post(API_UPLOAD_URL, data=data, files=files)
            if res.status_code == 200:
                st.session_state.contract_summary = res.json().get("summary")
                st.session_state.contract_uploaded = True
                st.success("✅ Upload Success!")
                st.rerun()
            else:
                st.error("❌ Upload Failed")

    st.markdown('</div>', unsafe_allow_html=True)
    st.markdown("---")

# -------------------------
# 💬 Chat Display
# -------------------------
chat_container = st.container()
with chat_container:
    for msg in st.session_state.messages:
        css_class = "user-message" if msg["role"] == "user" else "assistant-message"
        speaker = "👤 You" if msg["role"] == "user" else "🤖 Assistant"
        st.markdown(f"""
        <div class="chat-message {css_class}">
            <strong>{speaker}:</strong><br>{msg["content"]}
        </div>
        """, unsafe_allow_html=True)

# -------------------------
# 💬 Chat Input
# -------------------------
user_input = st.chat_input("Type your message here...")
if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    tenant_id = st.session_state.user_info.get("user_id", "Guest")
    res = requests.post(API_CHAT_URL, data={"tenant_id": tenant_id, "message": user_input})
    reply = res.json().get("reply", "⚠️ No response")
    st.session_state.messages.append({"role": "assistant", "content": reply})
    st.rerun()

# -------------------------
# 👍👎 Feedback Section (FIXED)
# -------------------------
if len(st.session_state.messages) >= 2:
    last_ai = next((m for m in reversed(st.session_state.messages) if m["role"]=="assistant"), None)
    last_user = next((m for m in reversed(st.session_state.messages) if m["role"]=="user"), None)

    st.markdown("---")
    st.write("**Was this helpful?**")
    col1, col2 = st.columns(2)

    with col1:
        if st.button("👍 Yes"):
            res = requests.post(API_FEEDBACK_URL, data={
                "tenant_id": st.session_state.user_info.get("user_id", "Guest"),
                "query": last_user["content"],
                "response": last_ai["content"],
                "rating": 1,
            })
            if res.status_code == 200 and res.json().get("success"):
                st.success("✅ Thanks for your feedback!")
            else:
                st.error("❌ Failed to send feedback")

    with col2:
        if st.button("👎 No"):
            st.session_state.show_feedback_form = True

if st.session_state.show_feedback_form:
    st.subheader("💬 Help us improve")
    comment = st.text_area("What was wrong?")
    if st.button("Submit"):
        res = requests.post(API_FEEDBACK_URL, data={
            "tenant_id": st.session_state.user_info.get("user_id", "Guest"),
            "query": last_user["content"],
            "response": last_ai["content"],
            "rating": -1,
            "comment": comment
        })
        if res.status_code == 200 and res.json().get("success"):
            st.success("✅ Thank you!")
        else:
            st.error("❌ Failed to send feedback")
        st.session_state.show_feedback_form = False
        st.rerun()
