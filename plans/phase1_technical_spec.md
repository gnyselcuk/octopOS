# Phase 1 Technical Specification: Foundation

## Overview
Build the foundational infrastructure for octopOS including project structure, core abstractions, AWS authentication, and CLI interface.

## System Components

### 1. Project Structure
```
octopos/
├── src/
│   ├── engine/
│   │   ├── __init__.py
│   │   ├── base_agent.py      # Abstract base for all agents
│   │   └── message.py         # OctoMessage protocol
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── aws_sts.py         # AWS credential management
│   │   ├── config.py          # Configuration loader
│   │   └── logger.py          # Logging setup
│   ├── interfaces/
│   │   └── cli/
│   │       ├── __init__.py
│   │       └── main.py        # Typer CLI entry point
│   └── __init__.py
├── sandbox/                   # Docker workspace (empty initially)
├── plans/                     # Architecture & planning docs
├── .env.example
├── pyproject.toml
└── README.md
```

### 2. Core Abstractions

#### BaseAgent (Abstract Class)
All agents in the system inherit from this base class.

**Responsibilities:**
- Message sending/receiving via OctoMessage protocol
- Lifecycle management (start, stop, pause)
- State tracking
- Error handling and reporting

**Key Methods:**
- `send_message(receiver, message_type, payload)` → Send OctoMessage
- `receive_message()` → Process incoming messages
- `execute_task(task_payload)` → Abstract method for task execution
- `report_error(error, suggestion)` → Error reporting to Self-Healing Agent

#### OctoMessage Protocol
Standardized JSON message format for inter-agent communication.

**Schema (Pydantic Model):**
```python
class OctoMessage(BaseModel):
    message_id: UUID
    sender: str           # Agent identifier
    receiver: str         # Target agent
    type: MessageType     # TASK, ERROR, APPROVAL_REQUEST, etc.
    payload: Dict         # Message content
    timestamp: datetime
    correlation_id: UUID  # For request/response tracking
```

**Message Types:**
- `TASK`: Standard task assignment
- `ERROR`: Error reporting with suggestions
- `APPROVAL_REQUEST`: Supervisor approval needed
- `APPROVAL_GRANTED`: Approval response
- `STATUS_UPDATE`: Progress reporting
- `SYSTEM`: Internal system messages

### 3. AWS Authentication (STS)

**Requirements:**
- Support both local development and AWS-hosted deployments
- Use STS temporary credentials for security
- Auto-detect execution environment
- Support IAM roles when running on AWS

**Implementation:**
```python
class AWSAuthManager:
    def get_credentials(self) -> AWSCredentials
    def refresh_credentials(self) -> None
    def detect_environment(self) -> EnvironmentType  # LOCAL | EC2 | ECS | LAMBDA
    def get_bedrock_client(self) -> boto3.client
```

**Environment Detection Logic:**
1. Check for `AWS_EXECUTION_ENV` environment variable
2. Check EC2 instance metadata service (IMDS)
3. Check for ECS container credentials
4. Default to local credentials (AWS_PROFILE or access keys)

### 4. CLI Interface

**Commands (Phase 1):**

| Command | Description |
|---------|-------------|
| `octo setup` | Interactive onboarding flow |
| `octo status` | Show system/agent status |
| `octo --version` | Display version info |
| `octo --help` | Show help message |

**Setup Flow (`octo setup`):**
1. Detect environment (local/AWS)
2. Configure AWS credentials/region
3. Set agent persona (name, style)
4. Configure user preferences
5. Validate configuration
6. Save to profile

### 5. Configuration Management

**Configuration Sources (priority order):**
1. Environment variables (`OCTO_*`)
2. `.env` file
3. User profile (`~/.octopos/profile.yaml`)
4. Default values

**Configuration Schema:**
```yaml
aws:
  region: us-east-1
  profile: default
  
agent:
  name: octoOS
  persona: friendly  # friendly | professional | technical
  language: tr
  
user:
  name: ""
  timezone: Europe/Istanbul
  workspace: ~/octopos-workspace
  
logging:
  level: INFO
  destination: stdout  # stdout | file | cloudwatch
```

## Dependencies

**Core:**
- `python = "^3.10"`
- `pydantic = "^2.0"` - Data validation
- `typer = "^0.9"` - CLI framework

**AWS:**
- `boto3 = "^1.28"` - AWS SDK
- `botocore = "^1.31"` - AWS core

**Utilities:**
- `python-dotenv = "^1.0"` - Environment file support
- `pyyaml = "^6.0"` - YAML parsing
- `rich = "^13.0"` - Terminal formatting

## Success Criteria

- [ ] Project installs with `pip install -e .`
- [ ] `octo --version` returns version
- [ ] `octo setup` completes interactive flow
- [ ] AWS credentials are properly managed
- [ ] Configuration loads from multiple sources
- [ ] BaseAgent can be subclassed
- [ ] OctoMessage validates correctly

## Open Questions

1. Should we use asyncio for the BaseAgent from the start?
2. Do we need a message queue (Redis/RabbitMQ) or in-memory for Phase 1?
3. What's the minimum AWS permission set needed?
