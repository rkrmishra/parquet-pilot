# Parquet Pilot - LLM Observability Agent

An AI agent for analyzing retail sales data with comprehensive evaluation and observability capabilities. This project demonstrates best practices for building observable LLM applications using OpenAI function calling, Phoenix observability platform, and LLM-as-a-judge evaluation patterns.

## Features

- **Multi-Tool Agent**: Intelligent router pattern orchestrating three specialized tools
  - SQL-based data lookup using DuckDB
  - LLM-powered data analysis
  - Automated visualization code generation

- **Interactive Web Interface**: Streamlit-based chat application (NEW!)
  - User-friendly chat interface for natural conversations
  - Automatic inline visualization rendering
  - Example questions for quick testing
  - Real-time Phoenix observability integration
  - Conversation history management

- **Comprehensive Evaluation System**: Four LLM-as-a-judge evaluators
  - Tool calling accuracy validation
  - Runnable code verification
  - Response clarity assessment
  - SQL generation quality checks

- **Full Observability**: OpenTelemetry instrumentation with Phoenix
  - Distributed tracing for all agent operations
  - Custom span attributes and metrics
  - Real-time debugging and performance monitoring

## Quick Start

Get up and running in under 5 minutes using Docker Compose:

### Option 1: Using Docker Compose (Recommended)

1. **Clone and navigate to the project**:
```bash
git clone <repository-url>
cd parquet-pilot
```

2. **Set your OpenAI API key**:
```bash
export OPENAI_API_KEY=your_openai_api_key_here
```

3. **Start Phoenix with Docker Compose**:
```bash
docker-compose up -d
```

This will start Phoenix observability platform on:
- UI: `http://localhost:6006`
- gRPC traces endpoint: `localhost:4317`

4. **Install Python dependencies**:
```bash
python -m venv venv
source venv/bin/activate  # On Unix/MacOS
pip install -r requirements.txt
```

5. **Run the agent**:

   **Option A: Streamlit Web Interface (Recommended for interactive use)**
   ```bash
   cd data_analyst
   streamlit run streamlit_app.py
   ```
   Open your browser to `http://localhost:8501` to access the chat interface.

   **Option B: Command Line Evaluation Suite**
   ```bash
   cd data_analyst
   python main.py
   ```

6. **View results**: Open `http://localhost:6006` to see traces and evaluations in Phoenix

7. **Stop Phoenix when done**:
```bash
docker-compose down
```

### Option 2: Using Phoenix CLI

If you prefer running Phoenix locally without Docker:

```bash
# Install Phoenix
pip install arize-phoenix

# Start Phoenix server
phoenix serve

# In another terminal, run the agent
cd data_analyst
python main.py
```

## Architecture

### Agent System

The core agent implements a router pattern with three tools:

1. **lookup_sales_data**: Executes SQL queries on parquet data
   - Generates SQL from natural language using LLM
   - Executes queries via DuckDB
   - Returns structured data for analysis

2. **analyze_sales_data**: Extracts insights from query results
   - Processes data returned by lookup tool
   - Provides analytical interpretations
   - Answers business questions

3. **generate_visualization**: Creates executable plotting code
   - Generates Python visualization code (matplotlib)
   - Uses Pydantic models for structured outputs
   - Returns ready-to-execute code

### Evaluation Pipeline

Multiple evaluation layers ensure agent quality:

- **Tool Selection Evaluation**: Validates correct tool routing
- **Code Quality Evaluation**: Tests generated code executability
- **Clarity Evaluation**: Assesses response quality and coherence
- **SQL Validation**: Checks query correctness and efficiency

All evaluations use Phoenix SpanQuery DSL and log results back to the observability platform.

## Project Structure

```
parquet-pilot/
├── data_analyst/
│   ├── streamlit_app.py        # Streamlit web interface (NEW!)
│   ├── agent_core.py           # Refactored agent module (NEW!)
│   ├── main.py                 # Evaluation pipeline and test suite
│   ├── utils.py                # Agent implementation and tools (original)
│   ├── helper.py               # Environment utilities
│   └── data/                   # Parquet data files
│       └── Store_Sales_Price_Elasticity_Promotions_Data.parquet
├── requirements.txt            # Python dependencies (NEW!)
├── docker-compose.yml          # Phoenix container configuration
├── STREAMLIT_GUIDE.md          # Streamlit usage guide (NEW!)
├── .gitignore                  # Git ignore patterns
├── CLAUDE.md                   # Development guidelines
└── README.md                   # This file
```

## Getting Started

### Prerequisites

- Python 3.8+
- OpenAI API key
- Docker and Docker Compose (recommended) OR Phoenix CLI

### Detailed Installation

1. **Clone the repository**:
```bash
git clone <repository-url>
cd parquet-pilot
```

2. **Create and activate virtual environment**:
```bash
python -m venv venv
source venv/bin/activate  # On Unix/MacOS
# or
venv\Scripts\activate  # On Windows
```

3. **Install dependencies**:
```bash
pip install -r requirements.txt
```

4. **Configure environment variables**:
Create a `.env` file in the project root:
```bash
OPENAI_API_KEY=your_openai_api_key_here
PHOENIX_ENDPOINT=http://localhost:6006/v1/traces
```

### Running the Agent

**For a quick start, see the [Quick Start](#quick-start) section above.**

#### Option 1: Streamlit Web Interface (Recommended)

The Streamlit interface provides a user-friendly chat experience:

1. **Start Phoenix**:
```bash
docker-compose up -d
```

2. **Launch Streamlit app**:
```bash
cd data_analyst
streamlit run streamlit_app.py
```

3. **Open browser**: Navigate to `http://localhost:8501`

4. **Start chatting**: Use the example questions or type your own queries

5. **View traces**: Click the Phoenix link in the sidebar or visit `http://localhost:6006`

For detailed Streamlit usage instructions, see [STREAMLIT_GUIDE.md](STREAMLIT_GUIDE.md).

#### Option 2: Command Line Evaluation Suite

Run the automated evaluation pipeline:

1. **Start Phoenix**:
```bash
docker-compose up -d
```

2. **Run agent with full evaluation suite**:
```bash
cd data_analyst
python main.py
```

3. **View results**: Open `http://localhost:6006`

**What the evaluation suite does:**
- Executes agent against 6 predefined test questions
- Generates OpenTelemetry traces
- Runs all evaluation pipelines
- Logs results to Phoenix for analysis

#### Option 3: Interactive Command Line (Legacy)

Single test with auto-execution:
```bash
cd data_analyst
python utils.py
```

**Note:** `utils.py` executes examples on import. Use `agent_core.py` for programmatic access without auto-execution.

## Key Technologies

- **OpenAI**: GPT-4 for agent reasoning and tool calling
- **Streamlit**: Modern web framework for interactive data applications
- **Phoenix**: Observability platform for LLM applications (containerized via Docker)
- **OpenInference**: OpenTelemetry semantic conventions for AI
- **DuckDB**: High-performance SQL analytics engine
- **Pydantic**: Data validation and structured outputs
- **Pandas**: Data manipulation and analysis
- **Matplotlib**: Visualization library for chart generation
- **Docker**: Container platform for easy Phoenix deployment

## Observability

The project uses comprehensive instrumentation:

- **Automatic Tracing**: `@tracer.tool()` and `@tracer.chain()` decorators
- **Custom Spans**: Manual span creation for fine-grained control
- **Span Attributes**: Input/output tracking, status codes, metadata
- **Evaluation Tracing**: Separate trace contexts for evaluation runs

View all traces, spans, and evaluations in the Phoenix UI at `http://localhost:6006`

## Evaluation Metrics

The evaluation system tracks:

- **Tool Calling Accuracy**: Percentage of correct tool selections
- **Code Execution Success**: Ratio of runnable generated code
- **Response Clarity**: Quality scores from LLM judge
- **SQL Correctness**: Validity and efficiency of generated queries

All metrics are logged to Phoenix with timestamps and trace context.

## Data

The agent analyzes retail sales data including:
- Store performance metrics
- Product sales and pricing
- Promotional campaign effectiveness
- Price elasticity analysis

Data location: [data_analyst/data/Store_Sales_Price_Elasticity_Promotions_Data.parquet](data_analyst/data/Store_Sales_Price_Elasticity_Promotions_Data.parquet)

## Extending the Agent

### Adding New Tools

1. Define function with `@tracer.tool()` decorator
2. Add OpenAI function schema to `tools` list
3. Register in `tool_implementations` dictionary
4. Update documentation

### Adding New Evaluations

1. Create Phoenix SpanQuery to extract spans
2. Define evaluation prompt template
3. Implement using `llm_classify()`
4. Log results via Phoenix client

## Best Practices

- Always run Phoenix server before agent execution (use `docker-compose up -d` for easy setup)
- Use `suppress_tracing()` for evaluation LLM calls
- Set proper span attributes for debugging
- Follow OpenInference semantic conventions
- Use structured outputs (Pydantic) for reliability
- Store API keys in `.env` file, never commit them
- Use Docker Compose for consistent Phoenix deployment across environments

## Contributing

Contributions welcome! Please ensure:
- All new tools include proper tracing
- Evaluations follow Phoenix patterns
- Code passes existing test suite
- Documentation is updated

## License

[Add your license here]

## Acknowledgments

- Built with [Phoenix](https://github.com/Arize-ai/phoenix) by Arize AI
- Uses [OpenInference](https://github.com/Arize-ai/openinference) conventions
- Powered by OpenAI GPT-4
