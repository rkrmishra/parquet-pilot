"""
streamlit_app.py
-----------------
Streamlit frontend that provides an interactive chat UI for the agent.
Users can query a default Parquet dataset or upload their own file, view a
preview of the data, and ask questions that the agent answers using the
instrumented tools in `agent_core.py`.

This file integrates guardrails, UI components, and a simple pattern for
executing visualizations (the code produced by the LLM is executed using
`exec()` and should be treated carefully).
"""

import streamlit as st
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend for Streamlit
import io
import sys
from agent_core import (
    start_main_span, generate_visualization, lookup_sales_data,
    client, MODEL, generate_sql_query, tracer, TRANSACTION_DATA_FILE_PATH
)
import pandas as pd
import duckdb
from opentelemetry.trace import Status, StatusCode
import warnings
warnings.filterwarnings('ignore')

# Guardrails - Question validation
# These functions define a two-tier validation approach to keep questions
# within the dataset scope and prevent abuse or out-of-scope queries.
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
        # On error, we default to allowing the question so the user isn't
        # blocked by validation outages; errors are logged to the console
        # and traced in Phoenix.
        print(f"Validation error: {e}")
        return True, ""

# Additional keyword-based guardrails (fast pre-check)
def quick_validation(question: str) -> tuple[bool, str]:
    """Fast client-side checks to block obviously harmful or out-of-scope
    requests before incurring LLM latency.
    """
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

# Custom lookup function that uses uploaded file if available
# This function is used by the Streamlit UI to prioritize user-uploaded
# data over the default dataset. It keeps the same interface as the
# `lookup_sales_data` tool but chooses the data source from session state.
@tracer.tool()
def lookup_data_with_upload(prompt: str) -> str:
    """Implementation of data lookup that checks for uploaded file first"""
    try:
        table_name = "data_table"

        # Check if user uploaded a file
        if st.session_state.uploaded_file_path and st.session_state.uploaded_df is not None:
            # Use uploaded file
            df = st.session_state.uploaded_df
            file_source = st.session_state.uploaded_file_name
        else:
            # Use default file
            df = pd.read_parquet(TRANSACTION_DATA_FILE_PATH)
            file_source = "default dataset"

        # Create DuckDB table
        duckdb.sql(f"DROP TABLE IF EXISTS {table_name}")
        duckdb.sql(f"CREATE TABLE {table_name} AS SELECT * FROM df")

        # Generate SQL query
        sql_query = generate_sql_query(prompt, df.columns, table_name)
        sql_query = sql_query.strip()
        sql_query = sql_query.replace("```sql", "").replace("```", "")

        # Execute the SQL query
        with tracer.start_as_current_span("execute_sql_query", openinference_span_kind="chain") as span:
            span.set_input(sql_query)
            result = duckdb.sql(sql_query).df()
            span.set_output(value=str(result))
            span.set_status(StatusCode.OK)

        return result.to_string()
    except Exception as e:
        return f"Error accessing data: {str(e)}"

# Custom agent runner that uses uploaded file
def run_agent_with_upload(messages):
    """Run the agent while checking for a user-uploaded dataset.

    This wrapper swaps out the lookup implementation with `lookup_data_with_upload`
    so the agent operates against the user's dataset if present, and updates
    the system prompt accordingly. All other tool calls behave the same as
    the refactored core.
    """
    from agent_core import (
        analyze_sales_data, handle_tool_calls,
        SYSTEM_PROMPT, tools as original_tools
    )
    import json

    # Create custom tool implementations that use uploaded file
    tool_implementations_custom = {
        "lookup_sales_data": lookup_data_with_upload,
        "analyze_sales_data": analyze_sales_data,
        "generate_visualization": generate_visualization
    }

    if isinstance(messages, str):
        messages = [{"role": "user", "content": messages}]

    # Update system prompt based on dataset
    if st.session_state.uploaded_file_path:
        system_prompt_text = f"""
You are a helpful assistant that can answer questions about the uploaded dataset: {st.session_state.uploaded_file_name}.
Analyze the data and provide insights based on the available columns and data.
"""
    else:
        system_prompt_text = SYSTEM_PROMPT

    if not any(isinstance(message, dict) and message.get("role") == "system" for message in messages):
        system_prompt = {"role": "system", "content": system_prompt_text}
        messages.append(system_prompt)

    while True:
        with tracer.start_as_current_span(
            "router_call", openinference_span_kind="chain",
        ) as span:
            span.set_input(value=messages)

            response = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                tools=original_tools,
            )
            messages.append(response.choices[0].message.model_dump())
            tool_calls = response.choices[0].message.tool_calls
            span.set_status(StatusCode.OK)

            if tool_calls:
                # Use custom tool implementations
                for tool_call in tool_calls:
                    function = tool_implementations_custom[tool_call.function.name]
                    function_args = json.loads(tool_call.function.arguments)
                    result = function(**function_args)
                    messages.append({"role": "tool", "content": result, "tool_call_id": tool_call.id})
                span.set_output(value=tool_calls)
            else:
                span.set_output(value=response.choices[0].message.content)
                return response.choices[0].message.content

def start_agent_with_upload(messages):
    """Create the root span and invoke `run_agent_with_upload` so the
    entire execution is recorded as a single observable AgentRun trace.
    """
    with tracer.start_as_current_span(
        "AgentRun", openinference_span_kind="agent"
    ) as span:
        span.set_input(value=messages)
        ret = run_agent_with_upload(messages)
        span.set_output(value=ret)
        span.set_status(StatusCode.OK)
        return ret

# Page configuration (Streamlit)
# Configure the page meta and layout. The app is a simple single-page UI
# built with Streamlit widgets.
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

# Initialize session state variables used by the UI to retain conversation
# and uploaded file information for the session's duration.
if "messages" not in st.session_state:
    st.session_state.messages = []

if "conversation_history" not in st.session_state:
    st.session_state.conversation_history = []

if "uploaded_file_path" not in st.session_state:
    st.session_state.uploaded_file_path = None

if "uploaded_file_name" not in st.session_state:
    st.session_state.uploaded_file_name = None

if "uploaded_df" not in st.session_state:
    st.session_state.uploaded_df = None

# Header and sub-header
st.markdown('<p class="main-header">📊 Parquet Pilot</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">LLM-Powered Data Analyst Agent with OpenTelemetry Observability</p>', unsafe_allow_html=True)

# Sidebar (upload, examples, and observability links)
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

    st.header("📁 Upload Your Data")
    uploaded_file = st.file_uploader(
        "Upload a Parquet file to analyze",
        type=['parquet'],
        help="Upload your own Parquet file to ask questions about your data"
    )

    if uploaded_file is not None:
        try:
            import pandas as pd
            import tempfile
            import os

            # Save uploaded file to temporary location
            with tempfile.NamedTemporaryFile(delete=False, suffix='.parquet') as tmp_file:
                tmp_file.write(uploaded_file.getvalue())
                temp_path = tmp_file.name

            # Load the file to validate it
            df = pd.read_parquet(temp_path)

            # Update session state
            st.session_state.uploaded_file_path = temp_path
            st.session_state.uploaded_file_name = uploaded_file.name
            st.session_state.uploaded_df = df

            st.success(f"✅ Loaded: {uploaded_file.name}")
            st.info(f"📊 {len(df):,} rows × {len(df.columns)} columns")

            # Show preview in expander
            with st.expander("Preview uploaded data"):
                st.dataframe(df.head(10), use_container_width=True)

        except Exception as e:
            st.error(f"Error loading file: {str(e)}")
            st.session_state.uploaded_file_path = None
            st.session_state.uploaded_file_name = None
            st.session_state.uploaded_df = None

    elif st.session_state.uploaded_file_path:
        # Show currently loaded file
        st.info(f"📊 Using: {st.session_state.uploaded_file_name}")
        if st.button("🔄 Use Default Dataset", use_container_width=True):
            st.session_state.uploaded_file_path = None
            st.session_state.uploaded_file_name = None
            st.session_state.uploaded_df = None
            st.rerun()

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

# Main area - sample data viewer and schema preview
st.header("📊 Sample Data")

# Determine which dataset to show
if st.session_state.uploaded_file_path and st.session_state.uploaded_df is not None:
    dataset_name = f"📁 {st.session_state.uploaded_file_name} (Uploaded)"
    df = st.session_state.uploaded_df
else:
    dataset_name = "Store Sales Price Elasticity Promotions Data (Default)"
    try:
        df = pd.read_parquet(TRANSACTION_DATA_FILE_PATH)
    except Exception as e:
        st.error(f"Could not load default dataset: {str(e)}")
        df = None

if df is not None:
    with st.expander(f"View Dataset Schema & Sample - {dataset_name}", expanded=False):
        st.markdown(f"""
        **Dataset:** {dataset_name}

        **Available Fields:**
        """)

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
        - Ask about specific columns and their values
        - Request aggregations (total, average, count, min, max)
        - Compare performance across different dimensions
        - Filter data by specific conditions
        - Visualize trends and patterns
        """)
else:
    st.warning("No dataset available. Please upload a Parquet file or ensure the default dataset is accessible.")

st.divider()

# Main chat interface: handles user inputs, applies guardrails, and runs the
# agent. Visualization code is executed with `exec()` and rendered inline.
st.header("💬 Chat with the Data Analyst")

# Show active dataset indicator
if st.session_state.uploaded_file_path:
    st.info(f"🔍 Analyzing: **{st.session_state.uploaded_file_name}** ({len(st.session_state.uploaded_df):,} rows)")
else:
    st.info("🔍 Analyzing: **Default Store Sales Dataset**")

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

                        # Get response from agent - use custom runner with upload support
                        response = start_agent_with_upload(conversation)

                        # Update conversation history
                        st.session_state.conversation_history = conversation
                        st.session_state.conversation_history.append({"role": "assistant", "content": response})

                        # Display response
                        st.markdown(response)

                        # Check if visualization was requested
                        if any(keyword in user_input.lower() for keyword in ["chart", "graph", "plot", "visualize", "visualization", "show me"]):
                            try:
                                with st.spinner("Generating visualization..."):
                                    # Get data first - use uploaded file if available
                                    data = lookup_data_with_upload(user_input)

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

                                    # Execute the generated visualization code in a
                                    # restricted global dict to avoid polluting the
                                    # app's namespace. This is still potentially
                                    # risky; exercise caution when enabling uploads.
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
