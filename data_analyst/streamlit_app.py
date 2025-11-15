"""
Parquet Pilot - Streamlit Frontend
An interactive web interface for the LLM-powered data analyst agent
"""

import streamlit as st
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend for Streamlit
import io
import sys
from agent_core import start_main_span, generate_visualization, lookup_sales_data
import warnings
warnings.filterwarnings('ignore')

# Page configuration
st.set_page_config(
    page_title="Parquet Pilot - Data Analyst Agent",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
    <style>
    .main-header {
        font-size: 2.5rem;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 1rem;
    }
    .sub-header {
        font-size: 1.2rem;
        color: #666;
        text-align: center;
        margin-bottom: 2rem;
    }
    .stChatMessage {
        padding: 1rem;
        border-radius: 0.5rem;
    }
    </style>
""", unsafe_allow_html=True)

# Initialize session state
if "messages" not in st.session_state:
    st.session_state.messages = []

if "conversation_history" not in st.session_state:
    st.session_state.conversation_history = []

# Header
st.markdown('<p class="main-header">📊 Parquet Pilot</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">LLM-Powered Data Analyst Agent with OpenTelemetry Observability</p>', unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.header("About")
    st.markdown("""
    **Parquet Pilot** is an intelligent data analyst agent that can:
    - 🔍 Query retail sales data using natural language
    - 📈 Analyze trends and patterns
    - 📊 Generate visualizations

    **Powered by:**
    - OpenAI GPT-4o-mini
    - DuckDB for SQL queries
    - Phoenix for observability
    """)

    st.divider()

    st.header("Example Questions")
    example_questions = [
        "What was the most popular product SKU?",
        "What was the total revenue across all stores?",
        "Which store had the highest sales volume?",
        "Create a bar chart showing total sales by store",
        "What percentage of items were sold on promotion?",
        "What was the average transaction value?",
        "Show me sales trends for the top 5 products"
    ]

    for question in example_questions:
        if st.button(question, key=f"example_{question}", use_container_width=True):
            st.session_state.example_clicked = question

    st.divider()

    st.header("Phoenix Observability")
    st.markdown("""
    View traces and evaluations at:

    [http://localhost:6006](http://localhost:6006)

    Project: `evaluating-agent`
    """)

    st.divider()

    if st.button("🗑️ Clear Conversation", use_container_width=True):
        st.session_state.messages = []
        st.session_state.conversation_history = []
        st.rerun()

# Main chat interface
st.header("💬 Chat with the Data Analyst")

# Display chat messages
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

        # Display visualization if present
        if "visualization" in message:
            st.pyplot(message["visualization"])

# Always show the chat input box
user_input = st.chat_input("Ask a question about the sales data...")

# Handle example question clicks - check this AFTER the chat input
if hasattr(st.session_state, 'example_clicked') and st.session_state.example_clicked:
    user_input = st.session_state.example_clicked
    st.session_state.example_clicked = None  # Clear it instead of deleting

# Process user input
if user_input:
    # Add user message to chat
    st.session_state.messages.append({"role": "user", "content": user_input})

    with st.chat_message("user"):
        st.markdown(user_input)

    # Process with agent
    with st.chat_message("assistant"):
        with st.spinner("Analyzing your question..."):
            try:
                # Build conversation history
                conversation = []
                for msg in st.session_state.conversation_history:
                    conversation.append(msg)

                # Add current user message
                conversation.append({"role": "user", "content": user_input})

                # Get response from agent
                response = start_main_span(conversation)

                # Update conversation history
                st.session_state.conversation_history = conversation
                st.session_state.conversation_history.append({"role": "assistant", "content": response})

                # Display response
                st.markdown(response)

                # Check if visualization was requested
                if any(keyword in user_input.lower() for keyword in ["chart", "graph", "plot", "visualize", "visualization", "show me"]):
                    try:
                        with st.spinner("Generating visualization..."):
                            # Get data first
                            data = lookup_sales_data(user_input)

                            # Generate visualization code
                            viz_goal = user_input
                            viz_code = generate_visualization(data, viz_goal)

                            # Execute visualization code
                            fig = plt.figure(figsize=(10, 6))

                            # Create a safe execution environment
                            exec_globals = {
                                'plt': plt,
                                'pd': __import__('pandas'),
                                'data': data,
                                'fig': fig
                            }

                            exec(viz_code, exec_globals)

                            # Display the chart
                            st.pyplot(fig)
                            plt.close(fig)

                            # Store in message history
                            st.session_state.messages.append({
                                "role": "assistant",
                                "content": response,
                                "visualization": fig
                            })
                    except Exception as viz_error:
                        st.warning(f"Could not generate visualization: {str(viz_error)}")
                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": response
                        })
                else:
                    # Store in message history
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": response
                    })

            except Exception as e:
                error_msg = f"An error occurred: {str(e)}"
                st.error(error_msg)
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": error_msg
                })

# Footer
st.divider()
st.markdown("""
<div style='text-align: center; color: #666; padding: 1rem;'>
    <p>Built with Streamlit, OpenAI, DuckDB, and Phoenix</p>
    <p>Dataset: Store Sales Price Elasticity Promotions Data</p>
</div>
""", unsafe_allow_html=True)
