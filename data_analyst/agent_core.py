"""
agent_core.py - Core Agent Implementation
--------------------------------------------------
Minimal, import-safe module that exposes the agent tools and router used
by the Streamlit UI and other integrations. This module provides the
lookup, analysis, and visualization tools as well as the router logic.

"""

from openai import OpenAI
import pandas as pd
import json
import duckdb
from pydantic import BaseModel, Field
from helper import get_openai_api_key
import warnings

warnings.filterwarnings('ignore')  # silence non-actionable warnings

# Phoenix/OpenTelemetry imports
import phoenix as px
import os
from phoenix.otel import register
from openinference.instrumentation.openai import OpenAIInstrumentor
from openinference.semconv.trace import SpanAttributes
from opentelemetry.trace import Status, StatusCode
from openinference.instrumentation import TracerProvider

# Initialize OpenAI client (reads API key from .env or env variables)
openai_api_key = get_openai_api_key()
client = OpenAI(api_key=openai_api_key)

MODEL = "gpt-4o-mini"  # Primary model used for agent operations

# Initialize Phoenix/OpenTelemetry tracing - exports spans to Phoenix
PROJECT_NAME = "evaluating-agent"
tracer_provider = register(
    project_name=PROJECT_NAME,
    endpoint="http://localhost:6006/v1/traces"
)

OpenAIInstrumentor().instrument(tracer_provider=tracer_provider)
tracer = tracer_provider.get_tracer(__name__)

# Data file path
TRANSACTION_DATA_FILE_PATH = 'data/Store_Sales_Price_Elasticity_Promotions_Data.parquet'

# ============================================================================
# TOOL 1: Database Lookup
# ============================================================================

SQL_GENERATION_PROMPT = """
Generate an SQL query based on a prompt. Do not reply with anything besides the SQL query.
The prompt is: {prompt}

The available columns are: {columns}
The table name is: {table_name}
"""

def generate_sql_query(prompt: str, columns: list, table_name: str) -> str:
    """Ask the LLM to create an SQL query string for the provided prompt.

    This function provides a small helper wrapper for formatting the prompt
    passed to the LLM. It returns raw SQL and relies on callers to sanitize
    or validate the query before execution.
    """
    formatted_prompt = SQL_GENERATION_PROMPT.format(
        prompt=prompt,
        columns=columns,
        table_name=table_name
    )

    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": formatted_prompt}],
    )

    return response.choices[0].message.content

@tracer.tool()
def lookup_sales_data(prompt: str) -> str:
    """Lookup tool: create an in-memory DuckDB table, generate SQL via the
    LLM, execute the SQL, and return the results as a string.
    """
    try:
        table_name = "sales"

        # Read the Parquet into a DataFrame and register as a DuckDB table.
        df = pd.read_parquet(TRANSACTION_DATA_FILE_PATH)
        duckdb.sql(f"CREATE TABLE IF NOT EXISTS {table_name} AS SELECT * FROM df")

        # Generate the SQL code
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

# ============================================================================
# TOOL 2: Data Analysis (Human-readable narrative generation)
# ============================================================================

DATA_ANALYSIS_PROMPT = """
Analyze the following data: {data}
Your job is to answer the following question: {prompt}
"""

@tracer.tool()
def analyze_sales_data(prompt: str, data: str) -> str:
    """Analysis tool: send the data + prompt to the LLM and return readable
    analyses and recommendations.
    """
    formatted_prompt = DATA_ANALYSIS_PROMPT.format(data=data, prompt=prompt)

    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": formatted_prompt}],
    )

    analysis = response.choices[0].message.content
    return analysis if analysis else "No analysis could be generated"

# ============================================================================
# TOOL 3: Data Visualization (configuration -> code generation)
# ============================================================================

CHART_CONFIGURATION_PROMPT = """
Generate a chart configuration based on this data: {data}
The goal is to show: {visualization_goal}
"""

class VisualizationConfig(BaseModel):
    chart_type: str = Field(..., description="Type of chart to generate")
    x_axis: str = Field(..., description="Name of the x-axis column")
    y_axis: str = Field(..., description="Name of the y-axis column")
    title: str = Field(..., description="Title of the chart")

@tracer.chain()
def extract_chart_config(data: str, visualization_goal: str) -> dict:
    """Ask the LLM to produce a structured chart configuration for a
    requested visualization goal. On error, fall back to a simple default.
    """
    formatted_prompt = CHART_CONFIGURATION_PROMPT.format(
        data=data,
        visualization_goal=visualization_goal
    )

    response = client.beta.chat.completions.parse(
        model=MODEL,
        messages=[{"role": "user", "content": formatted_prompt}],
        response_format=VisualizationConfig,
    )

    try:
        content = response.choices[0].message.content

        return {
            "chart_type": content.chart_type,
            "x_axis": content.x_axis,
            "y_axis": content.y_axis,
            "title": content.title,
            "data": data
        }
    except Exception:
        return {
            "chart_type": "line",
            "x_axis": "date",
            "y_axis": "value",
            "title": visualization_goal,
            "data": data
        }

CREATE_CHART_PROMPT = """
Write python code to create a chart based on the following configuration.
Only return the code, no other text.
config: {config}
"""

@tracer.chain()
def create_chart(config: dict) -> str:
    """Ask the LLM to generate Python plotting code for a chart matching
    the provided `config`. The code is returned as a string and must be
    executed carefully by the caller.
    """
    formatted_prompt = CREATE_CHART_PROMPT.format(config=config)

    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": formatted_prompt}],
    )

    code = response.choices[0].message.content
    code = code.replace("```python", "").replace("```", "")
    code = code.strip()

    return code

@tracer.tool()
def generate_visualization(data: str, visualization_goal: str) -> str:
    """High-level visualization tool: create config then generate code.
    Returns a string with plotting code (not executed here).
    """
    config = extract_chart_config(data, visualization_goal)
    code = create_chart(config)
    return code

# ============================================================================
# ROUTER AND ORCHESTRATION
# ============================================================================

tools = [
    {
        "type": "function",
        "function": {
            "name": "lookup_sales_data",
            "description": "Look up data from Store Sales Price Elasticity Promotions dataset",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "The unchanged prompt that the user provided."}
                },
                "required": ["prompt"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_sales_data",
            "description": "Analyze sales data to extract insights",
            "parameters": {
                "type": "object",
                "properties": {
                    "data": {"type": "string", "description": "The lookup_sales_data tool's output."},
                    "prompt": {"type": "string", "description": "The unchanged prompt that the user provided."}
                },
                "required": ["data", "prompt"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generate_visualization",
            "description": "Generate Python code to create data visualizations",
            "parameters": {
                "type": "object",
                "properties": {
                    "data": {"type": "string", "description": "The lookup_sales_data tool's output."},
                    "visualization_goal": {"type": "string", "description": "The goal of the visualization."}
                },
                "required": ["data", "visualization_goal"]
            }
        }
    }
]

tool_implementations = {
    "lookup_sales_data": lookup_sales_data,
    "analyze_sales_data": analyze_sales_data,
    "generate_visualization": generate_visualization
}

@tracer.chain()
def handle_tool_calls(tool_calls, messages):
    """Dispatch each function call returned by the model and append
    outputs to the conversation history.
    """
    for tool_call in tool_calls:
        function = tool_implementations[tool_call.function.name]
        function_args = json.loads(tool_call.function.arguments)
        result = function(**function_args)
        messages.append({"role": "tool", "content": result, "tool_call_id": tool_call.id})

    return messages

SYSTEM_PROMPT = """
You are a helpful assistant that can answer questions about the Store Sales Price Elasticity Promotions dataset.
"""

def run_agent(messages):
    """Router loop: submit messages to the LLM, execute requested tools,
    and return a final natural-language answer.
    """
    if isinstance(messages, str):
        messages = [{"role": "user", "content": messages}]

    if not any(isinstance(message, dict) and message.get("role") == "system" for message in messages):
        system_prompt = {"role": "system", "content": SYSTEM_PROMPT}
        messages.append(system_prompt)

    while True:
        with tracer.start_as_current_span(
            "router_call", openinference_span_kind="chain",
        ) as span:
            span.set_input(value=messages)

            response = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                tools=tools,
            )
            messages.append(response.choices[0].message.model_dump())
            tool_calls = response.choices[0].message.tool_calls
            span.set_status(StatusCode.OK)

            if tool_calls:
                messages = handle_tool_calls(tool_calls, messages)
                span.set_output(value=tool_calls)
            else:
                span.set_output(value=response.choices[0].message.content)
                return response.choices[0].message.content

def start_main_span(messages):
    """Start main span for agent execution"""
    with tracer.start_as_current_span(
        "AgentRun", openinference_span_kind="agent"
    ) as span:
        span.set_input(value=messages)
        ret = run_agent(messages)
        span.set_output(value=ret)
        span.set_status(StatusCode.OK)
        return ret
