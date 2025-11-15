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
from agent_core import start_main_span, generate_visualization, lookup_sales_data, client, MODEL
import warnings
warnings.filterwarnings('ignore')

# Guardrails - Question validation
def validate_question(question: str) -> tuple[bool, str]:
    """
    Validate if the question is within scope using LLM-based guardrails.

    Returns:
        tuple: (is_valid, message)
    """
    VALIDATION_PROMPT = """You are a validation system for a retail sales data analysis chatbot.

The chatbot can ONLY answer questions about retail sales data with the following information:
- Store performance and sales metrics
- Product sales, SKUs, and categories
- Transaction data and revenue
- Promotional campaigns and their impact
- Price elasticity and pricing data
- Sales trends over time
- Geographic/regional sales analysis

The chatbot CANNOT answer:
- General knowledge questions
- Programming or technical questions unrelated to the data
- Personal advice or opinions
- Questions about topics outside retail sales
- Requests to perform actions outside data analysis
- Offensive or harmful content

Analyze this user question and determine if it's within scope:
"{question}"

Respond with ONLY ONE of these:
VALID - if the question is about retail sales data analysis
INVALID - if the question is outside the scope

If INVALID, provide a brief one-sentence explanation after a pipe character (|).

Examples:
"What was the total revenue in 2021?" -> VALID
"Write me a Python function" -> INVALID|This chatbot only answers questions about retail sales data.
"What's the capital of France?" -> INVALID|This chatbot only analyzes retail sales data, not general knowledge.
"Show me sales by store" -> VALID
"""

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": VALIDATION_PROMPT},
                {"role": "user", "content": question}
            ],
            temperature=0,
            max_tokens=100
        )

        result = response.choices[0].message.content.strip()

        if result.startswith("VALID"):
            return True, ""
        elif result.startswith("INVALID"):
            parts = result.split("|", 1)
            if len(parts) > 1:
                return False, parts[1].strip()
            else:
                return False, "This question is outside the scope of retail sales data analysis."
        else:
            # Default to allowing if validation fails
            return True, ""

    except Exception as e:
        # On error, allow the question but log it
        print(f"Validation error: {e}")
        return True, ""

# Additional keyword-based guardrails (fast pre-check)
def quick_validation(question: str) -> tuple[bool, str]:
    """Quick keyword-based validation before LLM check"""
    question_lower = question.lower()

    # Block obvious out-of-scope patterns
    harmful_patterns = [
        "hack", "exploit", "bypass", "jailbreak", "ignore instructions",
        "pretend you are", "act as if", "roleplay"
    ]

    for pattern in harmful_patterns:
        if pattern in question_lower:
            return False, "This type of question is not allowed."

    # Check for extremely short or empty questions
    if len(question.strip()) < 3:
        return False, "Please provide a more detailed question."

    # Check for excessive length (potential prompt injection)
    if len(question) > 1000:
        return False, "Question is too long. Please keep it concise."

    return True, ""

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

    **🛡️ Safety Features:**
    - Smart guardrails validate questions
    - Only answers retail sales queries
    - Blocks out-of-scope requests
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

# Sample Data Section - Main Screen
st.header("📊 Sample Data")
with st.expander("View Dataset Schema & Sample", expanded=False):
    st.markdown("""
    **Dataset:** Store Sales Price Elasticity Promotions Data

    **Available Fields:**
    """)

    # Load and display sample data
    try:
        import pandas as pd
        from agent_core import TRANSACTION_DATA_FILE_PATH

        df = pd.read_parquet(TRANSACTION_DATA_FILE_PATH)

        st.markdown(f"**Total Records:** {len(df):,}")
        st.markdown("**Columns:**")

        # Display column information
        col_info = pd.DataFrame({
            'Column': df.columns,
            'Type': df.dtypes.astype(str),
            'Sample': [str(df[col].iloc[0]) if len(df) > 0 else 'N/A' for col in df.columns]
        })
        st.dataframe(col_info, use_container_width=True, hide_index=True)

        st.markdown("**Sample Rows (First 5):**")
        st.dataframe(df.head(5), use_container_width=True)

        st.markdown("""
        **Query Ideas:**
        - Ask about specific stores, products, or dates
        - Request aggregations (total, average, count)
        - Compare performance across dimensions
        - Analyze promotional impact
        - Visualize trends over time
        """)

    except Exception as e:
        st.error(f"Could not load sample data: {str(e)}")
        st.info("Make sure you're running from the data_analyst directory")

st.divider()

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

    # Validate question with guardrails
    with st.chat_message("assistant"):
        # Quick validation first (fast)
        quick_valid, quick_msg = quick_validation(user_input)

        if not quick_valid:
            error_response = f"⚠️ **Question Not Allowed**\n\n{quick_msg}\n\n**This chatbot can only answer questions about:**\n- Store sales and performance\n- Product data and SKUs\n- Revenue and transactions\n- Promotional campaigns\n- Sales trends and analysis\n\nPlease ask a question related to the retail sales data."
            st.markdown(error_response)
            st.session_state.messages.append({
                "role": "assistant",
                "content": error_response
            })
        else:
            # LLM-based validation (slower but more accurate)
            with st.spinner("Validating question..."):
                is_valid, validation_msg = validate_question(user_input)

            if not is_valid:
                error_response = f"⚠️ **Question Outside Scope**\n\n{validation_msg}\n\n**This chatbot specializes in:**\n- Retail sales data analysis\n- Store and product performance\n- Revenue trends and metrics\n- Promotional impact analysis\n\nPlease ask a question about the sales data. You can view the sample data above to see what's available."
                st.markdown(error_response)
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": error_response
                })
            else:
                # Question is valid - process with agent
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
