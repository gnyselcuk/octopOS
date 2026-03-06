# octopOS Architecture Documentation

This document provides a comprehensive technical overview of the octopOS architecture, based on the actual implementation in the codebase.

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Core Components](#core-components)
3. [Agent System](#agent-system)
4. [Memory Architecture](#memory-architecture)
5. [Worker System](#worker-system)
6. [Primitives System](#primitives-system)
7. [Message Protocol](#message-protocol)
8. [Workflow Integration](#workflow-integration)
9. [Security Architecture](#security-architecture)
10. [Interface Layer](#interface-layer)

---

## System Overview

octopOS is a multi-agent AI operating system built on a layered architecture:

```mermaid
flowchart TB
    subgraph Layer1["Layer 1: Interface"]
        direction LR
        L1A["CLI"]
        L1B["Telegram"]
        L1C["Slack"]
        L1D["WhatsApp"]
        L1E["Voice"]
    end

    subgraph Layer2["Layer 2: Core Engine"]
        direction LR
        L2A["Orchestrator"]
        L2B["Message Bus"]
        L2C["Scheduler"]
    end

    subgraph Layer3["Layer 3: Specialist Agents"]
        direction LR
        L3A["Manager"]
        L3B["Coder"]
        L3C["Self-Healing"]
        L3D["Supervisor"]
    end

    subgraph Layer4["Layer 4: Memory & Context"]
        direction LR
        L4A["Semantic Memory"]
        L4B["IntentFinder"]
        L4C["Fact Extractor"]
    end

    subgraph Layer5["Layer 5: Execution"]
        direction LR
        L5A["Worker Pool"]
        L5B["Sandbox"]
        L5C["Primitives"]
    end

    Layer1 --> Layer2
    Layer2 --> Layer3
    Layer3 --> Layer4
    Layer3 --> Layer5
```

---

## Core Components

### Base Agent

All agents inherit from [`BaseAgent`](src/engine/base_agent.py:24), which provides:

- **Lifecycle Management**: `start()`, `stop()`, `pause()`
- **Message Handling**: Automatic subscription to message queue
- **State Tracking**: Task status management
- **Error Reporting**: Structured error propagation

```python
class BaseAgent(ABC):
    @abstractmethod
    async def execute_task(self, task: TaskPayload) -> Dict[str, Any]:
        """Execute a task assigned to this agent."""
        pass
```

### Message Protocol

The [`OctoMessage`](src/engine/message.py:102) protocol enables inter-agent communication:

```mermaid
classDiagram
    class OctoMessage {
        +UUID message_id
        +MessageType type
        +str sender
        +str recipient
        +BaseModel payload
        +datetime timestamp
    }

    class MessageType {
        <<enumeration>>
        TASK
        ERROR
        APPROVAL_REQUEST
        APPROVAL_GRANTED
        APPROVAL_DENIED
        STATUS_UPDATE
        SYSTEM
        CHAT
    }

    class TaskPayload {
        +UUID task_id
        +str action
        +dict params
        +TaskStatus status
    }

    class ErrorPayload {
        +str error_type
        +str error_message
        +ErrorSeverity severity
        +str suggestion
    }

    OctoMessage --> MessageType
    OctoMessage --> TaskPayload
    OctoMessage --> ErrorPayload
```

---

## Agent System

### Agent Hierarchy

```mermaid
classDiagram
    BaseAgent <|-- Orchestrator
    BaseAgent <|-- ManagerAgent
    BaseAgent <|-- CoderAgent
    BaseAgent <|-- SelfHealingAgent
    BaseAgent <|-- Supervisor
    BaseAgent <|-- BrowserAgent

    class BaseAgent {
        <<abstract>>
        +str name
        +TaskStatus state
        +execute_task(task)*
        +start()
        +stop()
    }

    class Orchestrator {
        +Dict[str, BaseAgent] _agents
        +register_agent(agent)
        +get_agent(name)
    }

    class ManagerAgent {
        +AgentRegistry _registry
        +AgentRouter _router
        +coordinate_task()
        +execute_workflow()
    }

    class CoderAgent {
        +create_primitive()
        +modify_primitive()
        +_generate_code()
    }

    class SelfHealingAgent {
        +diagnose_error()
        +repair_code()
        +analyze_failure()
    }

    class Supervisor {
        +scan_code()
        +process_approval()
        +_check_security()
    }
```

### Manager Agent

The [`ManagerAgent`](src/specialist/manager_agent.py:1) is the central coordinator:

**Key Responsibilities:**
1. **Agent Registry**: Maintains directory of all agents and their capabilities
2. **Task Routing**: Routes tasks to appropriate agents
3. **Workflow Orchestration**: Manages multi-step workflows
4. **Health Monitoring**: Tracks agent health and status

**Key Methods:**
- [`execute_task()`](src/specialist/manager_agent.py:847): Execute a task through appropriate agent
- [`create_workflow()`](src/specialist/manager_agent.py:956): Create multi-agent workflow
- [`get_agent_status()`](src/specialist/manager_agent.py:1098): Query agent health

### Coder Agent

The [`CoderAgent`](src/specialist/coder_agent.py:1) generates new primitives:

**Workflow:**
1. Receives natural language description
2. Generates Python code using LLM
3. Creates tests for the code
4. Sends for security review

**Key Methods:**
- [`create_primitive()`](src/specialist/coder_agent.py:53): Generate new tool
- [`modify_primitive()`](src/specialist/coder_agent.py:95): Modify existing tool
- [`approve_primitive()`](src/specialist/coder_agent.py:447): Handle approval

### Self-Healing Agent

The [`SelfHealingAgent`](src/specialist/self_healing_agent.py:1) diagnoses and fixes errors:

**Capabilities:**
- Error pattern recognition
- Log analysis
- Code repair suggestions
- Anomaly detection

**Key Methods:**
- [`diagnose_error()`](src/specialist/self_healing_agent.py:227): Analyze error
- [`repair_code()`](src/specialist/self_healing_agent.py:64): Attempt code fix

### Supervisor

The [`Supervisor`](src/engine/supervisor.py:1) enforces security policies:

**Security Features:**
- Code import scanning
- Security risk assessment
- Approval workflows
- Policy enforcement

**Key Methods:**
- [`scan_code()`](src/engine/supervisor.py:285): Scan for security issues
- [`_process_approval_request()`](src/engine/supervisor.py:418): Handle approvals

---

## Memory Architecture

### Memory Layers

```mermaid
flowchart TB
    subgraph Layer1["Working Memory"]
        WM["Short-term Context"]
        Cache["Semantic Cache"]
    end

    subgraph Layer2["Long-term Memory"]
        SM["Semantic Memory<br/>LanceDB"]
        IF["IntentFinder<br/>Tool Registry"]
    end

    subgraph Layer3["User Profile"]
        FE["Fact Extractor"]
        Persona["User Persona"]
    end

    Input["User Input"] --> WM
    WM --> Cache
    WM --> SM
    SM --> FE
    FE --> Persona
    WM --> IF
```

### Semantic Memory

Location: [`src/engine/memory/semantic_memory.py`](src/engine/memory/semantic_memory.py)

**Features:**
- Vector-based storage using LanceDB
- Embedding-based semantic search
- Memory decay with garbage collection
- Access tracking for importance scoring

**Memory Entry Structure:**
```python
@dataclass
class MemoryEntry:
    id: str
    content: str
    category: str  # "fact", "preference", "event", "learning"
    timestamp: str
    source: str
    confidence: float
    metadata: Dict[str, Any]
    access_count: int = 1
    last_accessed: str = ""
```

**Memory Decay:**

The [`prune_decayed_memories()`](src/engine/memory/semantic_memory.py:367) method implements synaptic pruning:

```
Importance Score = (access_count * weight) - (days_since_last_access * decay_rate)
```

Memories with scores below the threshold are automatically removed.

### IntentFinder

Location: [`src/engine/memory/intent_finder.py`](src/engine/memory/intent_finder.py)

**Purpose:** Match user requests to available tools/primitives

**Key Methods:**
- [`find_primitives()`](src/engine/memory/intent_finder.py:124): Find matching tools
- [`add_primitive()`](src/engine/memory/intent_finder.py:221): Register new tool

### Fact Extractor

Location: [`src/engine/memory/fact_extractor.py`](src/engine/memory/fact_extractor.py)

**Purpose:** Automatically extract user facts from conversations

**Fact Categories:**
- Personal (location, preferences)
- Professional (job, skills)
- Preferences (likes, dislikes)

---

## Worker System

### Architecture

```mermaid
flowchart TB
    subgraph Pool["Worker Pool"]
        WP["WorkerPool"]
        Registry["Worker Registry"]
        Queue["Task Queue"]
    end

    subgraph Workers["Ephemeral Workers"]
        W1["Worker 1"]
        W2["Worker 2"]
        W3["Worker 3"]
    end

    subgraph Sandbox["Docker Sandbox"]
        C1["Container 1"]
        C2["Container 2"]
        C3["Container 3"]
    end

    MA["Manager Agent"] --> WP
    WP --> Registry
    WP --> Queue
    WP --> W1
    WP --> W2
    WP --> W3
    W1 --> C1
    W2 --> C2
    W3 --> C3
```

### BaseWorker

Location: [`src/workers/base_worker.py`](src/workers/base_worker.py)

**Lifecycle:**
1. **Created**: Worker instance created
2. **Started**: Docker container launched
3. **Busy**: Executing task
4. **Idle**: Ready for next task
5. **Destroyed**: Container cleaned up

**Configuration:**
```python
@dataclass
class WorkerConfig:
    max_memory_mb: int = 512
    max_cpu_cores: float = 1.0
    max_disk_mb: int = 1024
    max_execution_time: int = 300
    image: str = "octopos-sandbox:latest"
    network_mode: str = "none"
    read_only: bool = True
```

### WorkerPool

Location: [`src/workers/worker_pool.py`](src/workers/worker_pool.py)

**Features:**
- Dynamic worker creation
- Load balancing
- Health monitoring
- Auto-scaling

---

## Primitives System

### Primitive Categories

```mermaid
mindmap
  root((Primitives))
    AWS
      S3 Manager
      DynamoDB Client
      CloudWatch Inspector
      Bedrock Invoker
    Web
      Browser Session
      Search Engine
      API Index
      Nova Act Driver
    Development
      Git Manipulator
      AST Parser
    Native
      Bash Executor
      File Editor
      File Search
    MCP
      MCP Client
      MCP Tool Wrapper
      MCP Transport
```

### Base Primitive

Location: [`src/primitives/base_primitive.py`](src/primitives/base_primitive.py)

All primitives implement:
```python
class BasePrimitive(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def description(self) -> str: ...

    @abstractmethod
    async def execute(self, **params) -> PrimitiveResult: ...
```

### Tool Registry

Location: [`src/primitives/tool_registry.py`](src/primitives/tool_registry.py)

Manages all available primitives and provides discovery.

---

## Workflow Integration

### Complete Workflow

Location: [`src/engine/workflow_integration.py`](src/engine/workflow_integration.py)

```mermaid
sequenceDiagram
    autonumber
    participant User
    participant MB as Main Brain
    participant IF as IntentFinder
    participant MA as Manager Agent
    participant CA as Coder Agent
    participant SH as Self-Healing
    participant SUP as Supervisor

    User->>MB: User Request
    MB->>IF: 1. Find existing primitives
    
    alt Primitive Found
        IF-->>MB: Return existing tool
        MB-->>User: Execute with existing tool
    else No Match
        IF-->>MB: No matching primitives
        MB->>MA: 2. Trigger creation workflow
        MA->>CA: 3. Generate code
        CA-->>MA: Code + Tests
        MA->>SH: 4. Test code
        SH-->>MA: Test results
        
        alt Tests Failed
            MA->>CA: 5. Fix code
            Note over MA,CA: Retry loop
        else Tests Passed
            MA->>SUP: 6. Request approval
            SUP-->>MA: Approval decision
            
            alt Approved
                MA->>IF: 7. Register primitive
                MA-->>MB: Workflow complete
                MB-->>User: Task complete
            else Rejected
                MA-->>MB: Creation failed
                MB-->>User: Explain failure
            end
        end
    end
```

---

## Security Architecture

### Bedrock Guardrails

Location: [`src/utils/bedrock_guardrails.py`](src/utils/bedrock_guardrails.py)

```mermaid
flowchart LR
    Input["Input"] --> Filter["Guardrails Filter"]
    Filter --> Check{"Check"}
    Check -->|Allowed| Output["Output"]
    Check -->|Blocked| Deny["Deny"]
    
    subgraph Filters["Filter Types"]
        Content["Content Filters"]
        Topic["Topic Policies"]
        Word["Word Filters"]
        PII["PII Detection"]
    end
    
    Filter --> Filters
```

### Security Scanner

The Supervisor's [`scan_code()`](src/engine/supervisor.py:285) method checks for:
- Blocked imports (security risk)
- Allowed imports (safe)
- Unverified imports (needs review)

### Approval Workflow

```mermaid
flowchart TB
    Request["Approval Request"] --> Risk{"Risk Assessment"}
    Risk -->|Low Risk| Auto["Auto-Approve"]
    Risk -->|Medium Risk| Manual["Manual Review"]
    Risk -->|High Risk| Deny["Deny"]
    
    Auto --> Register["Register Primitive"]
    Manual --> Decision{"Decision?"}
    Decision -->|Approve| Register
    Decision -->|Reject| Deny
```

---

## Interface Layer

### Unified Message Adapter

All interfaces use [`MessageAdapter`](src/interfaces/message_adapter.py) to convert platform-specific messages to the internal `OctoMessage` format.

### Available Interfaces

| Platform | Files | Features |
|----------|-------|----------|
| **CLI** | [`cli/main.py`](src/interfaces/cli/main.py), [`cli/commands.py`](src/interfaces/cli/commands.py) | Interactive chat, commands, status |
| **Telegram** | [`telegram/`](src/interfaces/telegram/) | Bot, webhooks, message adapter |
| **Slack** | [`slack/`](src/interfaces/slack/) | Bot, events, slash commands |
| **WhatsApp** | [`whatsapp/`](src/interfaces/whatsapp/) | Business API, webhooks |
| **Voice** | [`voice/`](src/interfaces/voice/) | Nova Sonic integration |
| **UI** | [`ui/`](src/interfaces/ui/) | Nova Act automation |

---

## Configuration

Location: [`src/utils/config.py`](src/utils/config.py)

Configuration is loaded from multiple sources (in order of precedence):
1. Environment variables (`OCTO_*`)
2. `.env` file
3. User profile (`~/.octopos/profile.yaml`)
4. Default values

---

## Task Queue & Scheduling

Location: [`src/tasks/task_queue.py`](src/tasks/task_queue.py), [`src/engine/scheduler.py`](src/engine/scheduler.py)

**Features:**
- Persistent task storage (SQLite/DynamoDB)
- Priority-based scheduling
- Recurring tasks (cron expressions)
- AWS EventBridge integration for cloud deployments

---

## Data Flow Summary

```mermaid
flowchart TB
    subgraph Input["Input"]
        UI["User Interface"]
    end

    subgraph Processing["Processing"]
        MB["Main Brain"]
        MA["Manager Agent"]
        Agents["Specialist Agents"]
    end

    subgraph Memory["Memory"]
        WM["Working Memory"]
        SM["Semantic Memory"]
        IF["IntentFinder"]
    end

    subgraph Execution["Execution"]
        WP["Worker Pool"]
        SB["Sandbox"]
    end

    subgraph Output["Output"]
        Result["Result"]
        Learn["Learning"]
    end

    UI --> MB
    MB --> WM
    WM --> IF
    IF -->|Found| MB
    IF -->|Not Found| MA
    MA --> Agents
    Agents --> WP
    WP --> SB
    SB --> Result
    SB --> Learn
    Learn --> SM
    Result --> UI
```

---

*This documentation reflects the actual implementation as of the current codebase state.*