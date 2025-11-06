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
if "current_feedback_key" not in st.session_state:
    st.session_state.current_feedback_key = None

# -------------------------
# 🏷️ Page Header
# -------------------------
st.markdown('<h1 class="main-header">🏠 Tenant Chatbot Assistant</h1>', unsafe_allow_html=True)

# -------------------------
# 🔧 Sidebar Configuration - 所有功能完全独立
# -------------------------
with st.sidebar:
    st.header("🔧 Settings")
    st.markdown("---")
    
    # 🔐 认证区域 - 独立
    st.markdown('<div class="auth-section">', unsafe_allow_html=True)
    st.subheader("🔐 Authentication")
    
    if not st.session_state.logged_in:
        auth_mode = st.radio("选择操作模式", ["登录 Login", "注册 Register"], horizontal=True, key="auth_mode")
        
        if auth_mode == "登录 Login":
            email = st.text_input("Enter your email address", key="login_email")
            if st.button("Login", type="primary", key="login_btn", use_container_width=True):
                if email:
                    with st.spinner("Logging in..."):
                        try:
                            response = requests.get(API_USER_URL, params={"email": email}, timeout=10)
                            if response.status_code == 200:
                                user_data = response.json()
                                if "user_id" in user_data:
                                    st.session_state.user_info = user_data
                                    st.session_state.logged_in = True
                                    st.success(f"✅ Hi, {user_data.get('name', 'User')} 👋")
                                    st.rerun()
                                else:
                                    st.error("⚠️ Invalid response from backend.")
                            else:
                                st.error("⚠️ User not found. Please check your email or register.")
                        except Exception as e:
                            st.error(f"❌ Could not connect to backend: {e}")
                else:
                    st.warning("Please enter your email first.")
        
        else:  # 注册模式
            name = st.text_input("Your Name", key="reg_name")
            email = st.text_input("Your Email (as login ID)", key="reg_email")
            if st.button("Register", type="primary", key="reg_btn", use_container_width=True):
                if name and email:
                    with st.spinner("Registering..."):
                        try:
                            payload = {"tenant_id": email, "user_name": name}
                            response = requests.post(API_REGISTER_URL, data=payload, timeout=10)
                            if response.status_code == 200:
                                result = response.json()
                                if result.get("success", True):
                                    st.success("✅ Registration successful! Logging you in...")
                                    st.session_state.logged_in = True
                                    st.session_state.user_info = {"user_id": email, "name": name}
                                    st.rerun()
                                else:
                                    st.warning(f"⚠️ {result.get('message', 'Registration failed')}")
                            else:
                                st.error(f"❌ Server error during registration: {response.status_code}")
                        except Exception as e:
                            st.error(f"❌ Could not connect to backend: {e}")
                else:
                    st.warning("Please enter both name and email.")
    else:
        # 已登录状态
        name = st.session_state.user_info.get("name", "User")
        st.success(f"👋 Welcome, {name}!")
        if st.button("Logout", type="secondary", use_container_width=True):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()
    
    st.markdown('</div>', unsafe_allow_html=True)
    st.markdown("---")

    # 📄 文件上传区域 - 完全独立，不需要登录
    st.subheader("📄 Upload Contract PDF")
    st.markdown('<div class="upload-section">', unsafe_allow_html=True)
    
    uploaded_file = st.file_uploader(
        "Choose a PDF file", 
        type=["pdf"], 
        key="pdf_uploader",
        help="Upload your tenancy agreement PDF file. Login for personalized experience."
    )

    if uploaded_file is not None:
        # 显示文件信息
        file_details = {
            "Filename": uploaded_file.name,
            "File size": f"{len(uploaded_file.getvalue()) / 1024:.1f} KB"
        }
        st.write("**File details:**")
        st.json(file_details)
        
        # 上传按钮 - 始终可用，不需要登录
        if st.button("🚀 Upload and Process Contract", type="primary", use_container_width=True, key="upload_btn"):
            with st.spinner("📚 Processing your contract... This may take a few seconds."):
                try:
                    # 如果已登录，使用用户ID；否则使用"Guest"
                    tenant_id = st.session_state.user_info.get("user_id", "Guest") if st.session_state.logged_in else "Guest"
                    
                    # 准备文件数据
                    files = {"file": (uploaded_file.name, uploaded_file.getvalue(), "application/pdf")}
                    data = {"tenant_id": tenant_id}
                    
                    # 发送上传请求
                    response = requests.post(
                        API_UPLOAD_URL, 
                        data=data, 
                        files=files,
                        timeout=60
                    )
                    
                    if response.status_code == 200:
                        res = response.json()
                        summary = res.get("summary", {})
                        
                        # 设置会话状态
                        st.session_state.contract_summary = summary
                        st.session_state.contract_uploaded = True
                        st.session_state.upload_success = True
                        
                        st.success("✅ Contract successfully processed!")
                        
                        # 显示合同摘要
                        if summary:
                            with st.expander("View Contract Summary", expanded=True):
                                st.json(summary)
                        
                        # 如果未登录，提示登录以获得更好体验
                        if not st.session_state.logged_in:
                            st.info("💡 **Login to save your contract and get personalized responses**")
                        
                        st.rerun()
                        
                    else:
                        st.error(f"❌ Upload failed with status {response.status_code}")
                        st.write(f"Error: {response.text}")
                        
                except Exception as e:
                    st.error(f"❌ Error uploading file: {e}")
    
    st.markdown('</div>', unsafe_allow_html=True)
    st.markdown("---")

    # 🛠️ 维修请求表单 - 独立显示
    if st.session_state.get("show_maintenance_form", False):
        st.subheader("🛠️ Submit Maintenance Request")
        with st.form("maintenance_form"):
            location = st.text_input("Issue location (e.g., kitchen, aircon)")
            description = st.text_area("Issue description (e.g., water leakage)")
            submitted = st.form_submit_button("Submit Request", use_container_width=True)
            if submitted:
                if not st.session_state.logged_in:
                    st.error("Please login to submit maintenance requests")
                else:
                    try:
                        data = {
                            "tenant_id": st.session_state.user_info.get("user_id"),
                            "location": location,
                            "description": description
                        }
                        r = requests.post(API_MAINTENANCE_URL, data=data)
                        if r.status_code == 200:
                            st.success("✅ Request submitted successfully!")
                            st.session_state.show_maintenance_form = False
                            st.rerun()
                        else:
                            st.error("⚠️ Failed to submit maintenance request.")
                    except Exception as e:
                        st.error(f"❌ Error: {e}")

    st.markdown("---")

    # 💡 示例问题 - 始终显示
    st.write("💡 **Sample Questions:**")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Aircon 🛠️", use_container_width=True, key="q1"):
            st.session_state.messages.append({"role": "user", "content": "Who maintains the aircon?"})
            st.session_state.trigger_send = True
            st.rerun()
    with col2:
        if st.button("Termination 📄", use_container_width=True, key="q2"):
            st.session_state.messages.append({"role": "user", "content": "Can I terminate the lease early?"})
            st.session_state.trigger_send = True
            st.rerun()
    
    if st.button("Rent Calculation 💰", use_container_width=True, key="q3"):
        st.session_state.messages.append({"role": "user", "content": "Calculate total rent for 12 months at $2500 per month"})
        st.session_state.trigger_send = True
        st.rerun()

    st.markdown("---")

    # 🧹 清除聊天 - 始终显示
    if st.button("🗑️ Clear Chat History", use_container_width=True, key="clear_chat"):
        st.session_state.messages = []
        st.success("Chat history cleared!")
        st.rerun()

# -------------------------
# 📊 主内容区域 - 所有功能独立
# -------------------------

# 合同状态显示
if st.session_state.get("upload_success", False):
    st.balloons()
    st.session_state.upload_success = False

# 合同信息显示 - 无论登录状态都显示
if st.session_state.contract_uploaded and st.session_state.contract_summary:
    st.success("🎉 **Your contract is loaded!** You can now ask questions about your tenancy agreement.")
    
    summary = st.session_state.contract_summary
    if any(value for value in summary.values() if value is not None):
        st.subheader("📋 Contract Overview")
        cols = st.columns(4)
        
        metrics = [
            ("Monthly Rent", summary.get('monthly_rent'), "💰", "${}"),
            ("Security Deposit", summary.get('security_deposit'), "🏦", "${}"),
            ("Tenant", summary.get('tenant_name'), "👤", "{}"),
            ("Landlord", summary.get('landlord_name'), "🏠", "{}")
        ]
        
        for i, (label, value, icon, fmt) in enumerate(metrics):
            if value is not None:
                if fmt == "${}":
                    display_value = fmt.format(value)
                else:
                    display_value = fmt.format(str(value))
                cols[i].metric(f"{icon} {label}", display_value)
    
    # 如果未登录，提示登录的好处
    if not st.session_state.logged_in:
        st.info("🔐 **Login to save your contract permanently and get personalized responses**")
    
    st.markdown("---")
    
elif not st.session_state.contract_uploaded:
    st.info("📝 **Upload a contract PDF** in the sidebar to get contract-specific answers to your questions.")
    st.markdown("---")

# 登录状态提示（独立显示）
if not st.session_state.logged_in:
    st.info("👤 **You're browsing as a guest.** Login for personalized experience and to save your contract.")
elif st.session_state.logged_in and not st.session_state.contract_uploaded:
    st.info("📄 **You're logged in!** Upload a contract to get personalized responses.")

# -------------------------
# 💬 聊天显示区域 - 始终可用
# -------------------------
chat_container = st.container()
with chat_container:
    for i, msg in enumerate(st.session_state.messages):
        css_class = "user-message" if msg["role"] == "user" else "assistant-message"
        speaker = "👤 You" if msg["role"] == "user" else "🤖 Assistant"
        st.markdown(f"""
        <div class="chat-message {css_class}">
            <strong>{speaker}:</strong><br>{msg["content"]}
        </div>
        """, unsafe_allow_html=True)

# -------------------------
# 💬 聊天输入 - 始终可用
# -------------------------
user_input = st.chat_input("Type your message here...")

# -------------------------
# 🚀 发送逻辑 - 始终可用
# -------------------------
if user_input or st.session_state.get("trigger_send", False):
    if not user_input and st.session_state.get("trigger_send", False):
        user_input = st.session_state.messages[-1]["content"]
        st.session_state.trigger_send = False
        
    # 添加用户消息
    st.session_state.messages.append({"role": "user", "content": user_input})

    with st.spinner("🤔 Thinking..."):
        try:
            # 如果已登录，使用用户ID；否则使用"Guest"
            tenant_id = st.session_state.user_info.get("user_id", "Guest") if st.session_state.logged_in else "Guest"
            
            payload = {
                "tenant_id": tenant_id,
                "message": user_input
            }
            response = requests.post(API_CHAT_URL, data=payload, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                ai_reply = data.get("reply", "No reply found.")
                
                # 处理维修请求触发
                if ai_reply == "MAINTENANCE_REQUEST_TRIGGERED":
                    if st.session_state.logged_in:
                        st.session_state.show_maintenance_form = True
                        ai_reply = "🛠️ I understand you need to report an issue. Please fill out the maintenance form in the sidebar."
                    else:
                        ai_reply = "🛠️ I understand you need to report an issue. Please login to submit a maintenance request."
                    
                property_data = data.get("properties", None)
            else:
                ai_reply = f"⚠️ Backend returned error: {response.status_code}"
                property_data = None
                
        except Exception as e:
            ai_reply = f"❌ Could not connect to backend: {e}"
            property_data = None

    # 添加AI回复
    st.session_state.messages.append({"role": "assistant", "content": ai_reply})
    st.rerun()

# -------------------------
# 👍👎 反馈区域 - 始终可用但需要消息
# -------------------------
if st.session_state.messages:
    st.markdown("---")
    st.write("**Was this response helpful?**")
    col1, col2 = st.columns(2)
    
    last_assistant_msg = None
    last_user_msg = None
    
    # 找到最后一条AI消息和对应的用户消息
    for i in range(len(st.session_state.messages)-1, -1, -1):
        if st.session_state.messages[i]["role"] == "assistant" and last_assistant_msg is None:
            last_assistant_msg = st.session_state.messages[i]
        elif st.session_state.messages[i]["role"] == "user" and last_user_msg is None and last_assistant_msg is not None:
            last_user_msg = st.session_state.messages[i]
            break
    
    with col1:
        if st.button("👍 Yes", use_container_width=True, key="like_btn"):
            if last_assistant_msg and last_user_msg:
                try:
                    tenant_id = st.session_state.user_info.get("user_id", "Guest") if st.session_state.logged_in else "Guest"
                    requests.post(API_FEEDBACK_URL, data={
                        "tenant_id": tenant_id,
                        "query": last_user_msg["content"],
                        "response": last_assistant_msg["content"],
                        "rating": 1
                    })
                    st.success("Thanks for your feedback! 👍")
                    st.rerun()
                except:
                    st.error("Failed to submit feedback")
    
    with col2:
        if st.button("👎 No", use_container_width=True, key="dislike_btn"):
            st.session_state.show_feedback_form = True
            st.session_state.current_feedback_key = len(st.session_state.messages)
            st.rerun()

# 反馈表单
if st.session_state.get("show_feedback_form", False):
    st.markdown("---")
    st.subheader("💬 Provide Feedback")
    with st.form("feedback_form"):
        feedback_comment = st.text_area("What could be improved?", placeholder="Please tell us what was missing or incorrect...")
        col1, col2 = st.columns(2)
        with col1:
            submit_feedback = st.form_submit_button("Submit Feedback", use_container_width=True)
        with col2:
            cancel_feedback = st.form_submit_button("Cancel", use_container_width=True)
        
        if submit_feedback and feedback_comment:
            if last_assistant_msg and last_user_msg:
                try:
                    tenant_id = st.session_state.user_info.get("user_id", "Guest") if st.session_state.logged_in else "Guest"
                    requests.post(API_FEEDBACK_URL, data={
                        "tenant_id": tenant_id,
                        "query": last_user_msg["content"],
                        "response": last_assistant_msg["content"],
                        "rating": -1,
                        "comment": feedback_comment
                    })
                    st.success("Thank you for your feedback! We'll review it.")
                    st.session_state.show_feedback_form = False
                    st.rerun()
                except:
                    st.error("Failed to submit feedback")
        
        if cancel_feedback:
            st.session_state.show_feedback_form = False
            st.rerun()