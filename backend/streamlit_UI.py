import streamlit as st
import requests
import pandas as pd
import time

# -------------------------
# Page and Style Settings
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
</style>
""", unsafe_allow_html=True)

# -------------------------
#  Backend API Endpoint
# -------------------------
API_URL = "http://127.0.0.1:8000/chat"

# -------------------------
# Initialize Session State
# -------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []

# -------------------------
# Page Header
# -------------------------
st.markdown('<h1 class="main-header">🏠 Tenant Chatbot Assistant</h1>', unsafe_allow_html=True)

# -------------------------
#  Sidebar Configuration
# -------------------------
with st.sidebar:
    st.header("🔧 Settings")
    st.info("This frontend connects to your FastAPI backend endpoint:\n\n`http://127.0.0.1:8000/chat`")
    st.markdown("---")
    if st.button("🗑️ Clear Chat History"):
        st.session_state.messages = []
        st.success("Chat history cleared!")

    st.markdown("---")
    st.write("💡 Sample Questions:")
    if st.button("Who maintains the aircon?"):
        st.session_state.messages.append({"role": "user", "content": "Who maintains the aircon?"})
        st.session_state.trigger_send = True
        st.rerun()
    if st.button("Can I terminate the lease early?"):
        st.session_state.messages.append({"role": "user", "content": "Can I terminate the lease early?"})
        st.session_state.trigger_send = True
        st.rerun()

# -------------------------
# Display Chat History
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
# Chat Input
# -------------------------
user_input = st.chat_input("Type your message here...")

# -------------------------
# Send Logic
# -------------------------
if user_input or st.session_state.get("trigger_send", False):
    if not user_input and st.session_state.get("trigger_send", False):
        # Triggered by sidebar button
        user_input = st.session_state.messages[-1]["content"]
        st.session_state.trigger_send = False
    st.session_state.messages.append({"role": "user", "content": user_input})

    with st.spinner("🤔 Thinking..."):
        try:
            payload = {"user_id": "U001", "message": user_input}
            response = requests.post(API_URL, json=payload, timeout=20)

            if response.status_code == 200:
                data = response.json()
                ai_reply = data.get("reply", "No reply found.")
                property_data = data.get("properties", None)
            else:
                ai_reply = f"⚠️ Backend returned error: {response.status_code}"
                property_data = None

        except Exception as e:
            ai_reply = f"❌ Could not connect to backend: {e}"
            property_data = None

    # Show AI response
    st.session_state.messages.append({"role": "assistant", "content": ai_reply})
    css_class = "assistant-message"
    st.markdown(f"""
    <div class="chat-message {css_class}">
        <strong>🤖 Assistant:</strong><br>{ai_reply}
    </div>
    """, unsafe_allow_html=True)

    # Display property results if any
    if property_data:
        st.markdown("#### 🏘️ Recommended Properties:")
        try:
            df = pd.DataFrame(property_data)
            st.dataframe(df)
        except Exception:
            st.write(property_data)

    # Auto-scroll to bottom
    time.sleep(0.3)
    st.rerun()