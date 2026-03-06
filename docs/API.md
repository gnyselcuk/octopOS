# octopOS API Documentation

This document describes the programmatic APIs and CLI commands available in octopOS.

---

## Table of Contents

1. [CLI Commands](#cli-commands)
2. [Python API](#python-api)
3. [Message Protocol](#message-protocol)
4. [Primitive Development](#primitive-development)

---

## CLI Commands

### Global Options

```bash
octo [OPTIONS] COMMAND [ARGS]...

Options:
  --version, -v    Show version and exit
  --verbose        Enable verbose output
  --help           Show help message
```

### Command Reference

#### `octo setup`
Interactive setup wizard for configuring octopOS.

```bash
octo setup [OPTIONS]

Options:
  --force, -f    Force re-setup even if already configured
```

**Guides you through:**
- AWS credentials and region configuration
- Agent identity and personality selection
- User preferences
- Workspace settings

---

#### `octo status`
Show octopOS system status and agent health.

```bash
octo status [OPTIONS]

Options:
  --detailed, -d    Show detailed status

Aliases: agent-status
```

**Output includes:**
- Agent registry (all registered agents and their status)
- Worker pool statistics
- Queue size
- Health summary

---

#### `octo ask`
Ask octopOS a question or assign a task.

```bash
octo ask [OPTIONS] QUERY

Arguments:
  QUERY    The question or task for octopOS

Options:
  --context, -c TEXT    Additional context
  --no-cache           Bypass semantic cache
  --show-reasoning     Show agent reasoning
```

**Examples:**
```bash
# Simple question
octo ask "What files are in the current directory?"

# With context
octo ask "Deploy the application" --context "production environment"

# Complex task
octo ask "Create a Python script to process CSV files"
```

---

#### `octo chat`
Start an interactive continuous chat session.

```bash
octo chat [OPTIONS]

Options:
  --persona [friendly|professional|technical]    Set agent persona
  --no-memory                                     Disable memory for this session
```

---

#### `octo budget`
Manage token budgets and costs.

```bash
octo budget [OPTIONS] COMMAND [ARGS]...

Commands:
  show      Show current budget status
  reset     Reset budget counters
  set       Set budget limits
```

---

#### `octo cache-stats`
Show semantic cache statistics.

```bash
octo cache-stats [OPTIONS]

Options:
  --clear    Clear the cache
```

---

#### `octo dlq`
Manage Dead Letter Queue (failed messages).

```bash
octo dlq [OPTIONS] COMMAND [ARGS]...

Commands:
  list      List failed messages
  retry     Retry a failed message
  purge     Clear all failed messages
```

---

#### `octo mcp`
Model Context Protocol (MCP) market commands.

```bash
octo mcp [OPTIONS] COMMAND [ARGS]...

Commands:
  list          List available MCP servers
  install       Install an MCP server
  uninstall     Remove an MCP server
  search        Search MCP marketplace
```

---

## Python API

### Configuration

```python
from src.utils.config import get_config, OctoConfig

# Get global configuration
config = get_config()

# Access specific settings
aws_region = config.aws.region
agent_name = config.agent.name
memory_path = config.lancedb.path
```

### Agent Usage

```python
from src.engine.orchestrator import get_orchestrator
from src.engine.message import TaskPayload

# Get orchestrator instance
orchestrator = get_orchestrator()

# Execute a task
result = await orchestrator.execute_task(TaskPayload(
    action="process_file",
    params={"file": "data.csv"}
))
```

### Memory Operations

```python
from src.engine.memory.semantic_memory import SemanticMemory

# Initialize memory
memory = SemanticMemory()
await memory.initialize()

# Store a memory
await memory.remember(
    content="User prefers dark mode",
    category="preference",
    source="conversation"
)

# Recall memories
results = await memory.recall("What are user preferences?")

# Prune decayed memories
deleted_count = await memory.prune_decayed_memories(
    threshold_score=0.5,
    decay_rate=0.1
)
```

### IntentFinder

```python
from src.engine.memory.intent_finder import IntentFinder

# Initialize
intent_finder = IntentFinder()
await intent_finder.initialize()

# Find matching primitives
matches = await intent_finder.find_primitives(
    query="upload file to S3",
    top_k=3
)

# Register new primitive
await intent_finder.add_primitive(
    name="s3_upload",
    description="Upload files to AWS S3",
    code="..."
)
```

### Worker Pool

```python
from src.workers.worker_pool import get_worker_pool
from src.workers.base_worker import WorkerConfig

# Get worker pool
pool = get_worker_pool()

# Configure worker
config = WorkerConfig(
    max_memory_mb=512,
    max_execution_time=300
)

# Execute task in worker
result = await pool.execute_task(
    task_payload={"action": "bash", "command": "ls -la"},
    config=config
)
```

### Manager Agent

```python
from src.specialist.manager_agent import get_manager_agent

# Get manager instance
manager = get_manager_agent()

# Execute task through appropriate agent
result = await manager.execute_task(TaskPayload(
    action="create_file",
    params={"path": "test.txt", "content": "Hello"}
))

# Get agent status
status = manager.get_registry().get_health_summary()
```

### Coder Agent

```python
from src.specialist.coder_agent import get_coder_agent

# Get coder instance
coder = get_coder_agent()

# Create new primitive
result = await coder.execute_task(TaskPayload(
    action="create_primitive",
    params={
        "name": "greet_user",
        "description": "Generate personalized greeting",
        "requirements": ["Accept user name", "Return greeting message"]
    }
))
```

### Self-Healing Agent

```python
from src.specialist.self_healing_agent import get_self_healing_agent

# Get self-healing instance
healer = get_self_healing_agent()

# Diagnose error
result = await healer.execute_task(TaskPayload(
    action="diagnose_error",
    params={
        "error_message": "Connection timeout",
        "context": {"service": "database", "retry_count": 3}
    }
))
```

### Supervisor

```python
from src.engine.supervisor import get_supervisor

# Get supervisor instance
supervisor = get_supervisor()

# Scan code for security issues
scan_result = await supervisor.execute_task(TaskPayload(
    action="scan_code",
    params={"code": "import os; os.system('rm -rf /')"}
))

# Request approval
approval = await supervisor.execute_task(TaskPayload(
    action="request_approval",
    params={
        "action_type": "code_execution",
        "description": "Run external script",
        "security_scan": scan_result
    }
))
```

---

## Message Protocol

### Message Types

```python
from src.engine.message import MessageType, OctoMessage, TaskPayload

# Create a task message
message = OctoMessage(
    type=MessageType.TASK,
    sender="orchestrator",
    recipient="coder_agent",
    payload=TaskPayload(
        task_id=uuid4(),
        action="create_primitive",
        params={"name": "test"}
    )
)

# Send message
from src.engine.message import get_message_queue
queue = get_message_queue()
await queue.send(message)
```

### Task Status

```python
from src.engine.message import TaskStatus

# Possible statuses:
TaskStatus.PENDING       # Task created but not started
TaskStatus.IN_PROGRESS   # Currently executing
TaskStatus.COMPLETED     # Successfully finished
TaskStatus.FAILED        # Execution failed
TaskStatus.CANCELLED     # Cancelled by user/system
TaskStatus.PAUSED        # Temporarily paused
```

---

## Primitive Development

### Creating a Custom Primitive

```python
from src.primitives.base_primitive import BasePrimitive, PrimitiveResult

class MyPrimitive(BasePrimitive):
    @property
    def name(self) -> str:
        return "my_custom_tool"

    @property
    def description(self) -> str:
        return "Description of what this tool does"

    async def execute(self, **params) -> PrimitiveResult:
        """Execute the primitive."""
        try:
            # Your implementation here
            result = await self._do_work(params)
            
            return PrimitiveResult(
                success=True,
                data=result,
                message="Operation completed successfully"
            )
        except Exception as e:
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"Operation failed: {str(e)}",
                error="execution_error"
            )

    async def _do_work(self, params):
        # Implementation details
        pass
```

### Registering a Primitive

```python
from src.primitives import register_primitive

# Create instance
my_primitive = MyPrimitive()

# Register with the system
register_primitive(
    my_primitive,
    category='custom',
    tags=['my_tag', 'another_tag']
)
```

### Primitive Categories

Available categories for registration:
- `cloud_aws` - AWS services
- `web` - Web scraping and browsing
- `dev` - Development tools
- `native` - System operations
- `mcp` - MCP adapter tools
- `custom` - User-defined tools

---

## Error Handling

### Error Payload Structure

```python
from src.engine.message import ErrorPayload, ErrorSeverity

error = ErrorPayload(
    error_type="ValidationError",
    error_message="Invalid input format",
    severity=ErrorSeverity.MEDIUM,
    suggestion="Check input format and try again",
    stack_trace=traceback.format_exc(),
    context={"input": user_input}
)
```

### Severity Levels

- `LOW` - Non-critical, can continue
- `MEDIUM` - Issue requires attention
- `HIGH` - Significant problem, needs resolution
- `CRITICAL` - System-affecting error

---

## Integration Hooks

```python
from src.engine.integration_hooks import (
    with_guardrails,
    with_cloudwatch,
    with_token_budget
)

# Apply Bedrock Guardrails
@with_guardrails(source="INPUT")
def process_user_input(text: str) -> str:
    return text

# Log to CloudWatch
@with_cloudwatch(metric_name="api_calls")
def api_call():
    pass

# Track token budget
@with_token_budget()
def llm_call():
    pass
```

---

## Configuration Schema

See [Configuration Guide](CONFIGURATION.md) for complete configuration options.

Quick reference:

```yaml
# ~/.octopos/profile.yaml
aws:
  region: us-east-1
  profile: default

agent:
  name: octoOS
  persona: friendly
  language: en

user:
  name: ""
  timezone: UTC
  workspace_path: ~/octopos-workspace

security:
  require_approval_for_code: true
  auto_approve_safe_operations: false

lancedb:
  path: ./data/lancedb
```

---

*For more examples, see the `/examples` directory in the repository.*