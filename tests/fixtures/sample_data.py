"""Sample data for tests.

This module provides sample data structures for testing
various components of the octopOS system.
"""

import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List

# =============================================================================
# Sample Messages
# =============================================================================

def sample_task_message(
    sender: str = "test_sender",
    receiver: str = "test_receiver",
    action: str = "test_action"
) -> Dict[str, Any]:
    """Create a sample task message."""
    return {
        "sender": sender,
        "receiver": receiver,
        "type": "task",
        "payload": {
            "task_id": str(uuid.uuid4()),
            "action": action,
            "params": {"param1": "value1"},
            "priority": 5,
            "deadline": None,
            "dependencies": []
        }
    }


def sample_error_message(
    sender: str = "test_sender",
    receiver: str = "test_receiver",
    error_type: str = "TestError"
) -> Dict[str, Any]:
    """Create a sample error message."""
    return {
        "sender": sender,
        "receiver": receiver,
        "type": "error",
        "payload": {
            "error_type": error_type,
            "error_message": "Test error message",
            "severity": "medium",
            "suggestion": "Try again",
            "stack_trace": None,
            "context": {}
        }
    }


def sample_approval_request(
    sender: str = "coder_agent",
    receiver: str = "supervisor",
    action_type: str = "code_execution"
) -> Dict[str, Any]:
    """Create a sample approval request."""
    return {
        "sender": sender,
        "receiver": receiver,
        "type": "approval_request",
        "payload": {
            "request_id": str(uuid.uuid4()),
            "action_type": action_type,
            "action_description": "Execute generated code",
            "security_scan": {"risk_level": "low"},
            "code_changes": "print('hello')",
            "approved": None,
            "reason": None
        }
    }


def sample_status_update(
    sender: str = "worker_001",
    receiver: str = "orchestrator",
    status: str = "in_progress"
) -> Dict[str, Any]:
    """Create a sample status update."""
    return {
        "sender": sender,
        "receiver": receiver,
        "type": "status_update",
        "payload": {
            "task_id": str(uuid.uuid4()),
            "status": status,
            "progress": 50.0,
            "message": "Task is halfway done",
            "result": None
        }
    }


# =============================================================================
# Sample Worker Configs
# =============================================================================

def sample_worker_config(
    max_memory_mb: int = 512,
    max_cpu_cores: float = 1.0,
    max_execution_time: int = 300
) -> Dict[str, Any]:
    """Create a sample worker configuration."""
    return {
        "max_memory_mb": max_memory_mb,
        "max_cpu_cores": max_cpu_cores,
        "max_disk_mb": 1024,
        "max_execution_time": max_execution_time,
        "idle_timeout": 60,
        "image": "octopos-sandbox:latest",
        "network_mode": "none",
        "read_only": True,
        "user_id": "1000",
        "group_id": "1000",
        "drop_capabilities": ["ALL"],
        "log_level": "INFO",
        "max_log_size_mb": 10
    }


# =============================================================================
# Sample Security Scan Results
# =============================================================================

def sample_security_scan_passed() -> Dict[str, Any]:
    """Create a sample passed security scan."""
    return {
        "passed": True,
        "risk_level": "low",
        "findings": [],
        "recommendations": []
    }


def sample_security_scan_failed(
    risk_level: str = "high",
    finding_count: int = 1
) -> Dict[str, Any]:
    """Create a sample failed security scan."""
    findings = []
    for i in range(finding_count):
        findings.append({
            "type": "dangerous_pattern",
            "pattern": r"os\.system\s*\(",
            "line": i + 1,
            "severity": risk_level
        })
    
    return {
        "passed": False,
        "risk_level": risk_level,
        "findings": findings,
        "recommendations": ["Remove dangerous patterns"]
    }


# =============================================================================
# Sample Primitive Definitions
# =============================================================================

def sample_primitive_definition(
    name: str = "test_primitive",
    description: str = "A test primitive"
) -> Dict[str, Any]:
    """Create a sample primitive definition."""
    return {
        "name": name,
        "description": description,
        "parameters": {
            "input": {
                "type": "string",
                "description": "Input parameter",
                "required": True
            },
            "option": {
                "type": "boolean",
                "description": "Optional flag",
                "required": False,
                "default": False
            }
        }
    }


# =============================================================================
# Sample Container Configs
# =============================================================================

def sample_container_config(
    image: str = "octopos-sandbox:latest",
    command: List[str] = None
) -> Dict[str, Any]:
    """Create a sample container configuration."""
    return {
        "image": image,
        "command": command or ["python", "-c", "print('hello')"],
        "detach": True,
        "mem_limit": "512m",
        "cpu_quota": 100000,
        "cpu_period": 100000,
        "network_mode": "none",
        "read_only": True,
        "security_opt": ["no-new-privileges:true"],
        "cap_drop": ["ALL"],
        "user": "1000:1000",
        "environment": {},
        "volumes": {}
    }


# =============================================================================
# Sample Tasks
# =============================================================================

def sample_task(
    task_id: str = None,
    action: str = "test_action",
    priority: int = 5,
    status: str = "pending"
) -> Dict[str, Any]:
    """Create a sample task."""
    return {
        "task_id": task_id or str(uuid.uuid4()),
        "action": action,
        "params": {},
        "priority": priority,
        "status": status,
        "created_at": datetime.utcnow().isoformat(),
        "started_at": None,
        "completed_at": None,
        "worker_id": None,
        "result": None,
        "error": None
    }


# =============================================================================
# Sample Worker Results
# =============================================================================

def sample_worker_result(
    success: bool = True,
    exit_code: int = 0,
    stdout: str = "output",
    stderr: str = ""
) -> Dict[str, Any]:
    """Create a sample worker result."""
    return {
        "task_id": str(uuid.uuid4()),
        "worker_id": "worker_001",
        "success": success,
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": stderr,
        "output": {"result": stdout},
        "duration_seconds": 1.5,
        "created_at": datetime.utcnow().isoformat(),
        "metadata": {},
        "error": None if success else "Error occurred"
    }
