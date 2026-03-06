"""Specialist module - Specialized agent implementations."""

from src.specialist.coder_agent import CoderAgent, get_coder_agent
from src.specialist.self_healing_agent import SelfHealingAgent, get_self_healing_agent
from src.specialist.manager_agent import (
    ManagerAgent,
    get_manager_agent,
    AgentRegistry,
    MessageRouter,
    WorkflowOrchestrator,
    Workflow,
    WorkflowStep,
    AgentInfo,
    AgentStatus,
)
from src.specialist.browser_agent import (
    BrowserAgent,
    BrowserMission,
    SiteResult,
    ComparisonResult,
    create_browser_agent
)

__all__ = [
    "CoderAgent",
    "get_coder_agent",
    "SelfHealingAgent",
    "get_self_healing_agent",
    "ManagerAgent",
    "get_manager_agent",
    "AgentRegistry",
    "MessageRouter",
    "WorkflowOrchestrator",
    "Workflow",
    "WorkflowStep",
    "AgentInfo",
    "AgentStatus",
    # Browser Agent
    "BrowserAgent",
    "BrowserMission",
    "SiteResult",
    "ComparisonResult",
    "create_browser_agent"
]
