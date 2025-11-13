import streamlit as st
import requests

# ========== Streamlit page config ==========
st.set_page_config(
    page_title="Tenant Chatbot Frontend",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ========== Backend API endpoints ==========
API_BASE = "https://group14-1.onrender.com"
API_CHAT_URL = f"{API_BASE}/chat"
API_USER_URL = f"{API_BASE}/user"
API_REGISTER_URL = f"{API_BASE}/register"
API_UPLOAD_URL = f"{API_BASE}/upload"
API_MAINTENANCE_URL = f"{API_BASE}/maintenance"

# ========== Initialize session_state ==========
if "messages" not in st.session_state:
    st.session_state.messages = []

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if "user_info" not in st.session_state:
    st.session_state.user_info = {}

if "summary_data" not in st.session_state:
    st.session_state.summary_data = None

if "awaiting_maintenance_form" not in st.session_state:
    st.session_state.awaiting_maintenance_form = False

if "history_loaded" not in st.session_state:
    st.session_state.history_loaded = False

if "pdf_uploaded" not in st.session_state:
    st.session_state.pdf_uploaded = False

if "last_uploaded_filename" not in st.session_state:
    st.session_state.last_uploaded_filename = None


# ========== Login / Register page ==========
def show_login_page():
    st.markdown("""
    <div style="display:flex;align-items:center;justify-content:center;gap:12px;margin-top:0.8rem;margin-bottom:1.5rem;">
        <img src="https://huggingface.co/spaces/DSS5105group14/tenant-chatbot/resolve/main/src/title.jpg" width="60">
        <h1 style="margin:0;text-align:center;">Tenant Chatbot Assistant</h1>
    </div>
    """, unsafe_allow_html=True)

    mode = st.radio("Mode", ["Login", "Register"], horizontal=True)

    if mode == "Login":
        email = st.text_input("Email")
        if st.button("Login"):
            if email:
                try:
                    resp = requests.get(API_USER_URL, params={"email": email})
                    if resp.status_code == 200 and "user_id" in resp.json():
                        st.session_state.user_info = resp.json()
                        st.session_state.logged_in = True
                        st.session_state.history_loaded = False
                        st.rerun()
                    else:
                        st.error("User not found.")
                except Exception as e:
                    st.error(f"Login failed: {e}")
    else:
        name = st.text_input("Full Name")
        email = st.text_input("Email (used as login)")
        if st.button("Register"):
            if name and email:
                payload = {"tenant_id": email, "user_name": name}
                try:
                    r = requests.post(API_REGISTER_URL, data=payload)
                    if r.status_code == 200:
                        st.session_state.logged_in = True
                        st.session_state.user_info = {"user_id": email, "name": name}
                        st.session_state.history_loaded = False
                        st.rerun()
                    else:
                        st.error("Registration failed.")
                except Exception as e:
                    st.error(f"Registration failed: {e}")


# ========== Routing: show login page or main app ==========
if not st.session_state.logged_in:
    show_login_page()
    st.stop()

# ========== After login: load chat history once (S3) ==========
if not st.session_state.history_loaded:
    user_id = st.session_state.user_info.get("user_id")
    if user_id:
        try:
            # Convention: POST with message="__INIT__" returns chat history
            res = requests.post(
                API_CHAT_URL,
                data={"tenant_id": user_id, "message": "__INIT__"}
            )
            if res.status_code == 200:
                data = res.json()
                history = data.get("history", [])
                if isinstance(history, list):
                    st.session_state.messages = history
        except Exception:
            # Fail silently, start with empty history
            pass
    st.session_state.history_loaded = True

# ========== Page title ==========
st.title("Tenant Chatbot Assistant")

# ========== Sidebar: Settings, Logout, Contract upload, Clear chat ==========
with st.sidebar:
    st.subheader("Settings")
    name = st.session_state.user_info.get("name", "User")
    st.success(f"Hello, {name}")

    if st.button("Log out"):
        st.session_state.clear()
        st.rerun()

    st.markdown("---")
    st.subheader("Contract Upload")

    uploaded_file = st.file_uploader("Upload contract PDF", type=["pdf"])

    # Process the PDF only when a NEW file is selected (S6 + fix reloading)
    if uploaded_file and uploaded_file.name != st.session_state.last_uploaded_filename:
        with st.spinner("Uploading and processing contract..."):
            files = {
                "file": (
                    uploaded_file.name,
                    uploaded_file.getvalue(),
                    "application/pdf"
                )
            }
            data = {"tenant_id": st.session_state.user_info.get("user_id")}
            try:
                r = requests.post(API_UPLOAD_URL, files=files, data=data)
                if r.status_code == 200 and r.json().get("success"):
                    st.session_state.summary_data = r.json().get("summary")
                    st.session_state.pdf_uploaded = True
                    st.session_state.last_uploaded_filename = uploaded_file.name
                    st.success("Contract uploaded successfully!")
                else:
                    st.error("Contract upload failed.")
            except Exception as e:
                st.error(f"Contract upload failed: {e}")

    st.markdown("---")
    if st.button("Clear chat"):
        st.session_state.messages = []
        st.session_state.awaiting_maintenance_form = False
        st.rerun()

# ========== Show contract summary in an expander (S6) ==========
if st.session_state.summary_data:
    with st.expander("📄 Contract Summary"):
        st.json(st.session_state.summary_data)

# ========== Chat history display ==========
st.markdown("### 💬 Chat History")
for msg in st.session_state.messages:
    role = msg.get("role", "assistant")
    label = "👤 User" if role == "user" else "🤖 Assistant"
    content = msg.get("content", "")
    st.markdown(f"**{label}:** {content}")
        # === Feedback section: only for assistant messages ===
    if role == "assistant":
        with st.expander("Feedback for this reply"):
            rating = st.radio(f"Rate this reply:", ["👍 Good", "👎 Bad"], key=f"rating_{len(st.session_state.messages)}")
            comment = None
            if rating == "👎 Bad":
                comment = st.text_area("Tell us what went wrong:", key=f"comment_{len(st.session_state.messages)}")
            
            if st.button("Submit Feedback", key=f"feedback_btn_{len(st.session_state.messages)}"):
                data = {
                    "tenant_id": st.session_state.user_info.get("user_id"),
                    "query": st.session_state.messages[-2]["content"] if len(st.session_state.messages) >= 2 else "",
                    "response": content,
                    "rating": -1 if rating == "👎 Bad" else 1,
                    "comment": comment
                }
                try:
                    r = requests.post(API_BASE + "/feedback", data=data)
                    if r.status_code == 200:
                        st.success("Feedback submitted!")
                    else:
                        st.error("Failed to submit feedback.")
                except Exception as e:
                    st.error(f"Error submitting feedback: {e}")


# ========== User input ==========
user_input = st.chat_input("Type your message...")

if user_input:
    # Append user message and placeholder assistant message
    st.session_state.messages.append({"role": "user", "content": user_input})
    st.session_state.messages.append({"role": "assistant", "content": "Thinking..."})
    st.rerun()

# ========== Call backend chat API for the latest message ==========
if st.session_state.messages and st.session_state.messages[-1]["content"] == "Thinking...":
    # The last user message should be the one before the placeholder
    last_user_query = st.session_state.messages[-2]["content"]
    payload = {
        "tenant_id": st.session_state.user_info.get("user_id"),
        "message": last_user_query
    }

    try:
        res = requests.post(API_CHAT_URL, data=payload)
        if res.status_code == 200:
            data = res.json()
            ai_reply = data.get("reply", "No reply from backend.")

            # ====== S5: Maintenance trigger detection ======
            if ai_reply == "MAINTENANCE_REQUEST_TRIGGERED":
                st.session_state.awaiting_maintenance_form = True
                ai_reply = "A maintenance request is required. Please fill out the form below."
        else:
            ai_reply = f"Backend error: {res.status_code}"
    except Exception as e:
        ai_reply = f"Backend request failed: {e}"

    # Replace placeholder with actual reply
    st.session_state.messages[-1] = {"role": "assistant", "content": ai_reply}
    st.rerun()

# ========== S5: Maintenance request form ==========
if st.session_state.awaiting_maintenance_form:
    st.markdown("## 🛠️ Maintenance Request Form")
    with st.form("maintenance_form"):
        location = st.text_input("Location (e.g., Kitchen, Bedroom)")
        description = st.text_area("Issue Description")
        submitted = st.form_submit_button("Submit maintenance request")

        if submitted:
            data = {
                "tenant_id": st.session_state.user_info.get("user_id"),
                "location": location,
                "description": description,
            }
            try:
                r = requests.post(API_MAINTENANCE_URL, data=data)
                if r.status_code == 200:
                    st.success("Maintenance request submitted!")
                    st.session_state.awaiting_maintenance_form = False
                else:
                    st.error("Failed to submit maintenance request.")
            except Exception as e:
                st.error(f"Failed to submit maintenance request: {e}")
            st.rerun()
