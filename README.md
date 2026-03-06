# 🐙 octopOS - AI Agent Operating System

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> A self-healing, multi-agent AI operating system with episodic memory, tool synthesis, and omni-channel interfaces.

## 🌟 Overview

octopOS is a sophisticated AI agent operating system designed to autonomously handle complex tasks through a coordinated network of specialized agents. It features a unique self-healing capability where the system can generate, test, and deploy new tools (primitives) on-demand when existing capabilities are insufficient.

### Key Features

- **🔧 Self-Healing Architecture**: Automatically generates new tools when needed
- **🧠 Multi-Layer Memory System**: Short-term working memory, long-term semantic memory with decay
- **👥 Multi-Agent Coordination**: Manager, Coder, Self-Healing, and Supervisor agents
- **🐳 Ephemeral Workers**: Docker-based isolated execution environments
- **📱 Omni-Channel**: CLI, Telegram, Slack, WhatsApp, and voice interfaces
- **🛡️ Security-First**: Bedrock Guardrails, code scanning, approval workflows
- **☁️ AWS-Native**: EventBridge, CloudWatch, Bedrock, DynamoDB integration

---

## 🏗️ System Architecture

```mermaid
flowchart TB
    subgraph Interfaces["🎨 Interface Layer"]
        CLI["CLI (octo)"]
        TG["Telegram"]
        SL["Slack"]
        WA["WhatsApp"]
        Voice["Nova Sonic"]
    end

    subgraph Core["⚙️ Core Engine"]
        MB["Main Brain<br/>Orchestrator"]
        MSG["Message Bus<br/>OctoMessage Protocol"]
        WF["Workflow<br/>Integration"]
    end

    subgraph Agents["🤖 Specialist Agents"]
        MA["Manager Agent"]
        CA["Coder Agent"]
        SHA["Self-Healing Agent"]
        SUP["Supervisor"]
        BA["Browser Agent"]
    end

    subgraph Memory["🧠 Memory System"]
        SM["Semantic Memory<br/>LanceDB"]
        IF["IntentFinder"]
        FE["Fact Extractor"]
        WM["Working Memory"]
    end

    subgraph Workers["🐳 Worker Layer"]
        WP["Worker Pool"]
        EW["Ephemeral<br/>Containers"]
    end

    subgraph Primitives["🔧 Primitives"]
        MCP["MCP Tools"]
        AWS["AWS Operations"]
        WEB["Web/Browser"]
        FILE["File Operations"]
    end

    Interfaces --> MB
    MB --> MSG
    MSG --> Agents
    MA --> WP
    CA --> WP
    SHA --> WP
    Agents --> Memory
    WP --> EW
    EW --> Primitives
    SUP --> Agents
```

---

## 📁 Project Structure

```
octopOS/
├── src/
│   ├── engine/              # Core orchestration & messaging
│   │   ├── base_agent.py    # Abstract base for all agents
│   │   ├── orchestrator.py  # Main Brain
│   │   ├── workflow_integration.py  # Complete workflow orchestration
│   │   ├── supervisor.py    # Security & approval
│   │   ├── message.py       # OctoMessage protocol
│   │   └── memory/          # Memory subsystems
│   │       ├── semantic_memory.py    # Long-term memory with decay
│   │       ├── intent_finder.py      # Tool discovery
│   │       ├── fact_extractor.py     # User fact extraction
│   │       └── working_memory.py     # Short-term context
│   │
│   ├── specialist/          # Specialist agents
│   │   ├── manager_agent.py          # Agent coordination
│   │   ├── coder_agent.py            # Code generation
│   │   ├── self_healing_agent.py     # Error recovery
│   │   └── browser_agent.py          # Web automation
│   │
│   ├── workers/             # Ephemeral execution layer
│   │   ├── base_worker.py
│   │   ├── ephemeral_container.py
│   │   └── worker_pool.py
│   │
│   ├── primitives/          # Tool implementations
│   │   ├── base_primitive.py
│   │   ├── tool_registry.py
│   │   ├── mcp_adapter/     # MCP tool integration
│   │   ├── cloud_aws/       # AWS primitives
│   │   ├── web/             # Web scraping & browser
│   │   ├── dev/             # Git & AST operations
│   │   └── native/          # File & bash operations
│   │
│   ├── interfaces/          # User interfaces
│   │   ├── cli/             # Command-line interface
│   │   ├── telegram/        # Telegram bot
│   │   ├── slack/           # Slack integration
│   │   ├── whatsapp/        # WhatsApp Business API
│   │   ├── voice/           # Nova Sonic voice
│   │   └── ui/              # Nova Act UI automation
│   │
│   ├── tasks/               # Task queue & scheduling
│   │   └── task_queue.py    # OctoQueue implementation
│   │
│   └── utils/               # Utilities
│       ├── config.py        # Configuration management
│       ├── bedrock_guardrails.py  # Content safety
│       ├── cloudwatch_logger.py   # AWS logging
│       ├── aws_eventbridge.py     # Serverless scheduling
│       └── token_budget.py        # Cost management
│
├── sandbox/                 # Docker sandbox configuration
├── data/                    # Local data storage
│   └── lancedb/            # Vector database
└── tests/                   # Test suite
```

---

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- Docker (for sandboxed execution)
- AWS CLI configured (optional, for cloud features)

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/octopos.git
cd octopos

# Install dependencies
pip install -e ".[dev]"

# Configure environment
cp .env.example .env
# Edit .env with your settings

# Initialize the system
octo init
```

### Basic Usage

```bash
# Interactive chat
octo chat

# Execute a command
octo ask "List all files in the current directory"

# Check system status
octo status

# Check budget usage
octo budget
```

---

## 🧩 Component Details

### 1. Agent System

| Agent | Role | File |
|-------|------|------|
| **Orchestrator** | Main Brain - coordinates all agents | [`src/engine/orchestrator.py`](src/engine/orchestrator.py) |
| **Manager Agent** | Routes tasks, manages agent lifecycle | [`src/specialist/manager_agent.py`](src/specialist/manager_agent.py) |
| **Coder Agent** | Generates code for new primitives | [`src/specialist/coder_agent.py`](src/specialist/coder_agent.py) |
| **Self-Healing Agent** | Diagnoses and fixes errors | [`src/specialist/self_healing_agent.py`](src/specialist/self_healing_agent.py) |
| **Supervisor** | Security scanning & approval | [`src/engine/supervisor.py`](src/engine/supervisor.py) |
| **Browser Agent** | Web automation & scraping | [`src/specialist/browser_agent.py`](src/specialist/browser_agent.py) |

### 2. Memory System

```mermaid
flowchart LR
    subgraph Input["User Input"]
        UI["Message"]
    end

    subgraph MemoryLayers["Memory Layers"]
        WM["Working Memory<br/>Short-term context"]
        SM["Semantic Memory<br/>Long-term storage<br/>LanceDB + Embeddings"]
        IF["IntentFinder<br/>Tool matching"]
    end

    subgraph Decay["Memory Decay"]
        AC["access_count"]
        LA["last_accessed"]
        GC["Garbage Collector<br/>prune_decayed_memories"]
    end

    UI --> WM
    WM --> SM
    SM --> FE["Fact Extractor"]
    SM --> AC
    SM --> LA
    AC --> GC
    LA --> GC
    WM --> IF
```

**Memory Decay Formula:**
```
Importance Score = (access_count * weight) - (days_since_last_access * decay_rate)
```

See: [`src/engine/memory/semantic_memory.py`](src/engine/memory/semantic_memory.py:367)

### 3. Worker System

Ephemeral Docker containers for isolated task execution:

```mermaid
sequenceDiagram
    participant MA as Manager Agent
    participant WP as Worker Pool
    participant EW as Ephemeral Worker
    participant Sandbox as Docker Sandbox

    MA->>WP: Request worker
    WP->>WP: Check available workers
    alt Worker available
        WP-->>MA: Return existing worker
    else No workers
        WP->>EW: Create new worker
        EW->>Sandbox: Start container
        Sandbox-->>EW: Container ready
        EW-->>WP: Worker ready
        WP-->>MA: Return new worker
    end
    MA->>EW: Execute task
    EW->>Sandbox: Run in isolation
    Sandbox-->>EW: Return result
    EW-->>MA: Task complete
    MA->>WP: Release worker
```

See: [`src/workers/`](src/workers/)

### 4. Workflow Integration

Complete workflow for primitive creation:

```mermaid
sequenceDiagram
    participant User
    participant MB as Main Brain
    participant IF as IntentFinder
    participant MA as Manager Agent
    participant CA as Coder Agent
    participant SH as Self-Healing
    participant SUP as Supervisor

    User->>MB: "Upload files to GCP"
    MB->>IF: find_primitives(query)
    IF-->>MB: No matching primitives
    MB->>MA: create_primitive_workflow
    MA->>CA: Generate code
    CA-->>MA: Code + Tests
    MA->>SH: test_code
    SH-->>MA: Test results
    alt Tests passed
        MA->>SUP: request_approval
        SUP-->>MA: Approved
        MA->>IF: register_primitive
        MA-->>MB: Primitive ready
    else Tests failed
        MA->>CA: fix_code
        Note over MA,CA: Retry loop
    end
    MB-->>User: Task complete
```

See: [`src/engine/workflow_integration.py`](src/engine/workflow_integration.py)

### 5. Security & Guardrails

```mermaid
flowchart TB
    subgraph Input["Input Content"]
        User["User Message"]
        Code["Generated Code"]
    end

    subgraph Security["Security Layer"]
        BG["Bedrock Guardrails"]
        SS["Security Scanner"]
        AV["Approval Workflow"]
    end

    subgraph Actions["Actions"]
        Allow["✅ Allow"]
        Block["❌ Block"]
        Manual["⏸️ Manual Review"]
    end

    User --> BG
    Code --> SS
    BG --> Allow
    BG --> Block
    SS --> AV
    AV --> Allow
    AV --> Block
    AV --> Manual
```

See: [`src/utils/bedrock_guardrails.py`](src/utils/bedrock_guardrails.py), [`src/engine/supervisor.py`](src/engine/supervisor.py)

---

## 📚 Documentation

- [Architecture Documentation](docs/ARCHITECTURE.md) - Detailed system architecture
- [API Reference](docs/API.md) - API documentation
- [Development Guide](docs/DEVELOPMENT.md) - Contributing guidelines
- [Deployment Guide](docs/DEPLOYMENT.md) - Production deployment

---

## 🧪 Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test suite
pytest tests/unit/
pytest tests/integration/
```

---

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🤝 Contributing

Contributions are welcome! Please read our [Contributing Guide](docs/CONTRIBUTING.md) for details.

---

## 🙏 Acknowledgments

- AWS Bedrock for LLM capabilities
- LanceDB for vector storage
- Docker for sandboxed execution
- Model Context Protocol (MCP) for tool integration
