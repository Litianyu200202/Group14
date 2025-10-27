#!/usr/bin/env python3
"""
Streamlit PDF Chatbot Application
Interactive AI-powered property Q&A system

Run with: streamlit run codes_streamlit_group14.py
"""

import streamlit as st
import os
from typing import Optional, List, Dict, Any
import tempfile
import base64

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
    DOTENV_AVAILABLE = True
except ImportError:
    DOTENV_AVAILABLE = False

# Core libraries for PDF processing and AI
try:
    from langchain_community.document_loaders import PyPDFLoader
    from langchain.text_splitter import RecursiveCharacterTextSplitter
    from langchain_community.embeddings import OpenAIEmbeddings
    from langchain_community.vectorstores import FAISS
    from langchain_community.chat_models import ChatOpenAI
    from langchain.chains import ConversationalRetrievalChain
    from langchain.memory import ConversationBufferMemory
    import openai
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False

# Page configuration - must be first Streamlit command
st.set_page_config(
    page_title="Property management Chatbot Assistant",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

def setup_custom_css():
    """Configure custom CSS for better styling"""
    st.markdown("""
    <style>
    .main-header {
        font-size: 2.5rem;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 2rem;
    }
    .chat-message {
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 0.5rem 0;
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

def initialize_session_state():
    """Initialize session state variables for the chatbot"""
    
    # Chat history
    if "messages" not in st.session_state:
        st.session_state.messages = []
    
    # Document processing
    if "vectorstore" not in st.session_state:
        st.session_state.vectorstore = None
    
    if "conversation_chain" not in st.session_state:
        st.session_state.conversation_chain = None
    
    # File upload state
    if "uploaded_file_name" not in st.session_state:
        st.session_state.uploaded_file_name = None
    
    # Configuration
    if "temperature" not in st.session_state:
        st.session_state.temperature = 0.7
    
    if "max_tokens" not in st.session_state:
        st.session_state.max_tokens = 1000
    
    if "chunk_size" not in st.session_state:
        st.session_state.chunk_size = 1000
    
    # UI state for disabling input while thinking
    if "is_thinking" not in st.session_state:
        st.session_state.is_thinking = False

    # NEW: holds a question waiting to be answered
    if "pending_question" not in st.session_state:
        st.session_state.pending_question = None

def create_upload_interface():
    """Create PDF upload interface with validation"""
    
    st.subheader("📄 Upload PDF Document")
    
    uploaded_file = st.file_uploader(
        "Choose a PDF file to chat with:",
        type="pdf",
        help="Upload a PDF document and start asking questions about its content"
    )
    
    if uploaded_file is not None:
        # Display file information
        st.success(f"✅ File uploaded: {uploaded_file.name}")
        st.info(f"📊 File size: {uploaded_file.size / 1024:.1f} KB")
        
        # Process file if it's new
        if st.session_state.uploaded_file_name != uploaded_file.name:
            with st.spinner("🔄 Processing PDF document..."):
                success = process_pdf_document(uploaded_file)
                if success:
                    st.session_state.uploaded_file_name = uploaded_file.name
                    st.success("✅ Document processed successfully! You can now ask questions.")
                else:
                    st.error("❌ Failed to process document. Please try again.")
    
    return uploaded_file


def create_configuration_sidebar():
    """Create sidebar with configuration options"""
    
    with st.sidebar:
        st.header("🔧 Configuration")
        
        # API Key management
        st.subheader("🔑 OpenAI API Key")
        
        # Check if API key is already available from environment
        env_api_key = os.getenv("OPENAI_API_KEY")
        
        if env_api_key:
            st.success("✅ API Key loaded from environment")
            st.info("💡 Using API key from .env file")
        else:
            api_key = st.text_input(
                "Enter your OpenAI API Key:",
                type="password",
                help="Get your API key from https://platform.openai.com/api-keys or add to .env file"
            )
            
            if api_key:
                os.environ["OPENAI_API_KEY"] = api_key
                st.success("✅ API Key configured")
            else:
                st.warning("⚠️ Please enter your OpenAI API Key or create a .env file")
                with st.expander("📝 How to use .env file"):
                    st.markdown("""
                    Create a `.env` file in your project directory with:
                    ```
                    OPENAI_API_KEY=your-api-key-here
                    ```
                    This will automatically load your API key on startup.
                    """)
        
        st.divider()
        
        # Model parameters
        st.subheader("🤖 Model Settings")
        
        temperature = st.slider(
            "Temperature (Creativity)",
            min_value=0.0,
            max_value=1.0,
            value=st.session_state.temperature,
            step=0.1,
            help="Higher values make output more creative but less focused"
        )
        
        max_tokens = st.slider(
            "Max Response Length",
            min_value=100,
            max_value=2000,
            value=st.session_state.max_tokens,
            step=100,
            help="Maximum number of tokens in the response"
        )
        
        # Document processing settings
        st.subheader("📄 Document Settings")
        
        chunk_size = st.slider(
            "Text Chunk Size",
            min_value=500,
            max_value=2000,
            value=st.session_state.chunk_size,
            step=100,
            help="Size of text chunks for processing"
        )
        
        # Update session state
        st.session_state.temperature = temperature
        st.session_state.max_tokens = max_tokens
        st.session_state.chunk_size = chunk_size
        
        st.divider()
        
        # Clear conversation button
        if st.button("🗑️ Clear Conversation", type="secondary"):
            st.session_state.messages = []
            if st.session_state.conversation_chain:
                st.session_state.conversation_chain.memory.clear()
            st.success("Conversation cleared!")
        
        # Document info
        if st.session_state.uploaded_file_name:
            st.subheader("📊 Current Document")
            st.info(f"📄 {st.session_state.uploaded_file_name}")
            
            if st.session_state.vectorstore:
                doc_count = len(st.session_state.vectorstore.docstore._dict)
                st.metric("Text Chunks", doc_count)
        
        # Installation instructions
        if not LANGCHAIN_AVAILABLE:
            st.subheader("⚠️ Missing Dependencies")
            st.error("LangChain not installed. Install with:")
            st.code("pip install langchain langchain-community openai pypdf faiss-cpu python-dotenv", language="bash")
        
        if not DOTENV_AVAILABLE:
            st.subheader("💡 Optional Enhancement")
            st.info("Install python-dotenv for .env file support:")
            st.code("pip install python-dotenv", language="bash")

def display_chat_history():
    """Display chat history with custom styling"""
    
    for message in st.session_state.messages:
        if message["role"] == "user":
            st.markdown(f"""
            <div class="chat-message user-message">
                <strong>👤 You:</strong><br>
                {message["content"]}
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div class="chat-message assistant-message">
                <strong>🤖 Assistant:</strong><br>
                {message["content"]}
            </div>
            """, unsafe_allow_html=True)

def handle_user_input(thinking_placeholder):
    """Handle user input, mark as pending, and rerun so UI disables while thinking."""
    # Disable chat when thinking or when no document/chain is ready
    disabled = st.session_state.is_thinking or (st.session_state.conversation_chain is None)

    placeholder = (
        "Upload a PDF to start…" if st.session_state.conversation_chain is None
        else ("🤔 Thinking…" if st.session_state.is_thinking
              else "Ask a question about the uploaded document...")
    )

    user_input = st.chat_input(placeholder, disabled=disabled)

    if user_input:
        # Record the user message
        st.session_state.messages.append({"role": "user", "content": user_input})
        # Mark as pending and disable input
        st.session_state.pending_question = user_input
        st.session_state.is_thinking = True
        # Rerun so the disabled chatbox state is reflected immediately
        st.rerun()

def process_pending_user_message(thinking_placeholder):
    """If there's a pending question, answer it while the chat input is disabled."""
    if not st.session_state.is_thinking or not st.session_state.pending_question:
        return

    # If no conversation chain is available, guide the user
    if not st.session_state.conversation_chain:
        error_msg = "Please upload a PDF document first to start chatting!"
        st.session_state.messages.append({"role": "assistant", "content": error_msg})
        st.session_state.pending_question = None
        st.session_state.is_thinking = False
        st.rerun()

    with thinking_placeholder.container():
        with st.spinner("🤔 Thinking..."):
            try:
                q = st.session_state.pending_question
                response = st.session_state.conversation_chain({"question": q})
                answer = response["answer"]
                st.session_state.messages.append({"role": "assistant", "content": answer})
            except Exception as e:
                error_msg = f"Sorry, I encountered an error: {str(e)}"
                st.session_state.messages.append({"role": "assistant", "content": error_msg})

    # Clear pending + spinner, re-enable input, and refresh UI
    st.session_state.pending_question = None
    st.session_state.is_thinking = False
    thinking_placeholder.empty()
    st.rerun()

def main():
    """Main application function"""
    
    # Initialize app
    setup_custom_css()
    initialize_session_state()
    
    # Page header
    st.markdown('<h1 class="main-header">🤖 PDF Chatbot Assistant</h1>', unsafe_allow_html=True)
    
    
    # Create sidebar configuration
    create_configuration_sidebar()
    
    # Check if dependencies are available
    if not LANGCHAIN_AVAILABLE:
        st.error("⚠️ Required dependencies not installed. Please check the sidebar for installation instructions.")
        st.stop()
    
    # Check if API key is set
    if not os.getenv("OPENAI_API_KEY"):
        st.warning("⚠️ Please enter your OpenAI API Key in the sidebar to continue.")
        st.stop()
    
    # Create two columns for layout
    col1, col2 = st.columns([1, 2])
    
    with col1:
        # File upload section
        uploaded_file = create_upload_interface()
        
        # Sample questions
        if st.session_state.uploaded_file_name:
            st.subheader("💡 Sample Questions")
            sample_questions = [
                "What is the main topic of this document?",
                "Can you summarize the key points?",
                "What are the important details mentioned?",
                "Are there any specific recommendations?"
            ]
            
            for question in sample_questions:
                if st.button(question, key=f"sample_{question[:20]}", disabled=st.session_state.is_thinking):
                    st.session_state.messages.append({"role": "user", "content": question})
                    st.session_state.pending_question = question
                    st.session_state.is_thinking = True
                    st.rerun()
    
    with col2:
        # Chat interface
        st.subheader("💬 Chat with your Document")
        
        # Display chat history
        if st.session_state.messages:
            display_chat_history()
        else:
            st.info("👋 Upload a PDF document and start asking questions!")
        
        # Placeholder for the spinner (above the textbox)
        thinking_placeholder = st.empty()
        
        # ✅ 1) Render the input FIRST so it can be disabled on this run
        handle_user_input(thinking_placeholder)
        
        # ✅ 2) Then process any pending message (may call st.rerun)
        process_pending_user_message(thinking_placeholder)
    
    # Footer information
    with st.expander("📝 How to use this application"):
        st.markdown("""
        ### Getting Started:
        1. **Setup API Key**: 
           - Create a `.env` file with `OPENAI_API_KEY=your-key` (recommended)
           - OR enter your OpenAI API key in the sidebar
        2. **Upload PDF**: Choose a PDF file to analyze
        3. **Ask Questions**: Start chatting about the document content
        
        ### Features:
        - **Real-time Chat**: Interactive conversation with AI
        - **Document Context**: AI understands your PDF content
        - **Customizable**: Adjust AI parameters in the sidebar
        - **Memory**: Conversation history is maintained
        - **Environment Variables**: Auto-load API key from .env file
        
        ### Requirements:
        - OpenAI API key (get from https://platform.openai.com/api-keys)
        - PDF documents (text-based, not scanned images)
        
        ### Installation:
        ```bash
        pip install streamlit langchain langchain-community openai pypdf faiss-cpu python-dotenv
        ```
        """)

if __name__ == "__main__":
    main()