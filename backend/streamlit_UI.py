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

# -------------------------
# 💅 Classic Chat UI Styling
# -------------------------
st.markdown("""
<style>
/* ---- Overall Layout ---- */
body {
    background-color: #f7f7f8;  /* very light gray background */
    font-family: 'Segoe UI', 'Helvetica', 'PingFang SC', sans-serif;
}

/* Page Header */
.main-header {
    font-size: 2.2rem;
    color: #2c3e50;
    text-align: center;
    margin-bottom: 1.2rem;
    font-weight: 600;
}

/* Align chat bubbles vertically with spacing */
div[data-testid="stVerticalBlock"] > div > div {
    display: flex;
    flex-direction: column;
    gap: 0.3rem;
}

/* ---- Common Chat Bubble Style ---- */
.chat-message {
    padding: 0.9rem 1.1rem;
    border-radius: 1rem;
    margin: 0.4rem 0;
    line-height: 1.6;
    max-width: 85%;
    word-wrap: break-word;
    font-size: 1rem;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
}

/* ---- Assistant Bubble (gray) ---- */
.assistant-message {
    background-color: #f1f3f4;       /* soft gray bubble */
    border: 1px solid #e0e0e0;
    align-self: flex-start;
    margin-left: 0.3rem;
    color: #2c2c2c;
}

/* ---- User Bubble (light blue) ---- */
.user-message {
    background-color: #e9f2ff;       /* light blue bubble */
    border: 1px solid #d6e6ff;
    align-self: flex-end;
    margin-right: 0.3rem;
    color: #1a1a1a;
}

/* Hover animation for both */
.chat-message:hover {
    transform: translateY(-1px);
    box-shadow: 0 2px 6px rgba(0,0,0,0.08);
    transition: all 0.2s ease-in-out;
}

/* Scrollbar aesthetics */
::-webkit-scrollbar {
    width: 8px;
}
::-webkit-scrollbar-thumb {
    background-color: #cfcfcf;
    border-radius: 4px;
}

/* Chat input box styling */
div[data-testid="stChatInput"] {
    background-color: #ffffff;
    border: 1px solid #ddd;
    border-radius: 10px;
    padding: 0.4rem 0.8rem;
}

/* Sidebar subtle tone */
section[data-testid="stSidebar"] {
    background-color: #fafafa;
    border-right: 1px solid #e0e0e0;
}
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
API_MAINTENANCE_URL = "http://127.0.0.1:8000/maintenance"

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


# ======================================================
# ⭐ NEW: Fullscreen Login / Register Page
# ======================================================
def show_login_page():
    st.markdown('<div class="login-container">', unsafe_allow_html=True)
    st.markdown('<div class="login-box">', unsafe_allow_html=True)
    st.markdown('<div class="login-title">🏠 Tenant Assistant</div>', unsafe_allow_html=True)
    st.markdown("Welcome! Please login or register to continue.")

    mode = st.radio("Select mode", ["Login", "Register"], horizontal=True)

    if mode == "Login":
        email = st.text_input("📧 Email Address")
        if st.button("Login"):
            if email:
                try:
                    response = requests.get(API_USER_URL, params={"email": email}, timeout=10)
                    if response.status_code == 200:
                        user_data = response.json()
                        if "user_id" in user_data:
                            st.session_state.user_info = user_data
                            st.session_state.logged_in = True
                            st.success(f"✅ Welcome back, {user_data.get('name', 'User')} 👋")
                            st.rerun()
                        else:
                            st.error("⚠️ Invalid response from backend.")
                    else:
                        st.error("⚠️ User not found.")
                except Exception as e:
                    st.error(f"❌ Could not connect to backend: {e}")
            else:
                st.warning("Please enter your email.")
    else:
        name = st.text_input("👤 Full Name")
        email = st.text_input("📨 Email (used as login ID)")
        if st.button("Register"):
            if name and email:
                try:
                    payload = {"tenant_id": email, "user_name": name}
                    response = requests.post(API_REGISTER_URL, data=payload, timeout=10)
                    if response.status_code == 200:
                        result = response.json()
                        if result.get("success", True):
                            st.success("✅ Registration successful! Logging in...")
                            st.session_state.logged_in = True
                            st.session_state.user_info = {"user_id": email, "name": name}
                            st.rerun()
                        else:
                            st.warning("⚠️ Registration failed — this email may already exist.")
                    else:
                        st.error("❌ Server error during registration.")
                except Exception as e:
                    st.error(f"❌ Could not connect to backend: {e}")
            else:
                st.warning("Please fill in both name and email fields.")

    st.markdown('<hr><small style="color:gray;">© 2025 Tenant Assistant | Streamlit App</small>', unsafe_allow_html=True)
    st.markdown('</div></div>', unsafe_allow_html=True)


# ======================================================
# 🧭 ROUTER: Only show chat interface if logged in
# ======================================================
if not st.session_state.logged_in:
    show_login_page()
    st.stop()  # ⛔ Stop here, don't render the chat interface below


# ======================================================
# 🚀 Below is your original chat interface (UNCHANGED)
# ======================================================

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

    auth_mode = "LoggedIn"

    # 👋 Logged-in View
    name = st.session_state.user_info.get("name", "User")
    st.success(f"👋 Hello, {name}!")
    if st.button("Logout"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

    st.markdown("---")

    # 📄 Upload Contract
    st.subheader("📄 Upload Contract PDF")
    uploaded_file = st.file_uploader("Select your tenancy agreement (PDF)", type=["pdf"])

    if uploaded_file:
        with st.spinner("📚 Processing your contract..."):
            try:
                files = {"file": uploaded_file.getvalue()}
                data = {"tenant_id": st.session_state.user_info.get("user_id")}
                response = requests.post(API_UPLOAD_URL, data=data, files={"file": uploaded_file})
                if response.status_code == 200:
                    res = response.json()
                    summary = res.get("summary", {})
                    st.session_state.contract_summary = summary
                    st.success("✅ Contract successfully processed!")
                    st.markdown("#### 📘 Contract Summary:")
                    st.json(summary)
                else:
                    st.error(f"⚠️ Upload failed: {response.status_code}")
            except Exception as e:
                st.error(f"❌ Error: {e}")

    st.markdown("---")

    if st.button("🗑️ Clear Chat History"):
        st.session_state.messages = []
        st.success("Chat history cleared!")

    st.markdown("---")

    st.write("💡 Example Questions:")
    if st.button("Who maintains the air conditioner?"):
        st.session_state.messages.append({"role": "user", "content": "Who maintains the air conditioner?"})
        st.session_state.trigger_send = True
        st.rerun()
    if st.button("Can I terminate the lease early?"):
        st.session_state.messages.append({"role": "user", "content": "Can I terminate the lease early?"})
        st.session_state.trigger_send = True
        st.rerun()

# -------------------------
# 📘 Show Contract Summary
# -------------------------
if st.session_state.contract_summary:
    st.markdown("### 📄 Your Contract Summary")
    st.json(st.session_state.contract_summary)
    st.markdown("---")

# -------------------------
# 💬 Display Chat History
# -------------------------
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

# -------------------------
# 🚀 Send Logic
# -------------------------
if user_input or st.session_state.get("trigger_send", False):
    if not user_input and st.session_state.get("trigger_send", False):
        user_input = st.session_state.messages[-1]["content"]
        st.session_state.trigger_send = False
    st.session_state.messages.append({"role": "user", "content": user_input})

    with st.spinner("🤔 Thinking..."):
        try:
            payload = {
                "tenant_id": st.session_state.user_info.get("user_id", "Guest"),
                "message": user_input
            }
            response = requests.post(API_CHAT_URL, data=payload, timeout=20)
            if response.status_code == 200:
                data = response.json()
                ai_reply = data.get("reply", "No response found.")
                if ai_reply == "MAINTENANCE_REQUEST_TRIGGERED":
                    st.session_state.show_maintenance_form = True
                    ai_reply = "🛠️ I understand you need to report an issue. Please fill out the maintenance form in the sidebar."
                property_data = data.get("properties", None)
            else:
                ai_reply = f"⚠️ Backend returned error: {response.status_code}"
                property_data = None
        except Exception as e:
            ai_reply = f"❌ Could not connect to backend: {e}"
            property_data = None

    st.session_state.messages.append({"role": "assistant", "content": ai_reply})
    css_class = "assistant-message"
    st.markdown(f"""
    <div class="chat-message {css_class}">
        <strong>🤖 Assistant:</strong><br>{ai_reply}
    </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns([1, 10])
    with col1:
        if st.button("👍", key=f"like_{user_input}"):
            requests.post(API_FEEDBACK_URL, data={
                "tenant_id": st.session_state.user_info.get("user_id", "Guest"),
                "query": user_input,
                "response": ai_reply,
                "rating": 1
            })
            st.success("Thank you for your feedback!")

    with col2:
        if st.button("👎", key=f"dislike_{user_input}"):
            user_comment = st.text_area("Tell us how we can improve:", key=f"comment_{user_input}")
            if st.button("Submit Feedback", key=f"submit_{user_input}"):
                requests.post(API_FEEDBACK_URL, data={
                    "tenant_id": st.session_state.user_info.get("user_id", "Guest"),
                    "query": user_input,
                    "response": ai_reply,
                    "rating": -1,
                    "comment": user_comment
                })
                st.success("Thanks! Your feedback has been submitted.")

    if property_data:
        st.markdown("#### 🏘️ Recommended Properties:")
        try:
            df = pd.DataFrame(property_data)
            st.dataframe(df)
        except Exception:
            st.write(property_data)

    time.sleep(0.3)
    st.rerun()