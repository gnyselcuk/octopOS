"""Manager Agent - Coordinates specialist agents and manages workflows.

This module implements the Manager Agent that:
- Routes messages between specialist agents (Coder, Self-Healing)
- Manages agent collaboration workflows
- Handles agent lifecycle (start, stop, restart)
- Monitors agent health and status
- Orchestrates multi-agent task execution

Example:
    >>> manager = ManagerAgent()
    >>> await manager.start()
    >>> # Manager coordinates between agents automatically
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
from uuid import UUID, uuid4

from src.engine.base_agent import BaseAgent
from src.engine.message import (
    ApprovalPayload,
    ErrorPayload,
    ErrorSeverity,
    MessageType,
    OctoMessage,
    StatusPayload,
    TaskPayload,
    TaskStatus,
)
from src.utils.config import get_config
from src.utils.logger import AgentLogger


class AgentStatus(str, Enum):
    """Status of a registered agent."""
    
    IDLE = "idle"
    BUSY = "busy"
    STARTING = "starting"
    STOPPING = "stopping"
    ERROR = "error"
    OFFLINE = "offline"


@dataclass
class AgentInfo:
    """Information about a registered agent."""
    
    agent_id: str
    agent_type: str
    name: str
    status: AgentStatus
    capabilities: List[str]
    last_heartbeat: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    current_task: Optional[UUID] = None
    task_count: int = 0
    error_count: int = 0


@dataclass
class WorkflowStep:
    """A single step in a workflow."""
    
    step_id: UUID
    agent_type: str
    action: str
    params: Dict[str, Any]
    depends_on: List[UUID] = field(default_factory=list)
    timeout_seconds: int = 300
    retry_count: int = 0
    max_retries: int = 3


@dataclass
class Workflow:
    """A multi-step workflow definition."""
    
    workflow_id: UUID
    name: str
    description: str
    steps: List[WorkflowStep]
    current_step: Optional[UUID] = None
    status: TaskStatus = TaskStatus.PENDING
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    completed_at: Optional[str] = None
    results: Dict[UUID, Any] = field(default_factory=dict)
    errors: List[Dict[str, Any]] = field(default_factory=list)


class AgentRegistry:
    """Registry for tracking and discovering agents.
    
    Maintains a directory of all agents in the system, their capabilities,
    and current status. Enables dynamic agent discovery and selection.
    
    Example:
        >>> registry = AgentRegistry()
        >>> registry.register_agent("CoderAgent", ["code_generation", "debugging"])
        >>> agents = registry.find_agents_by_capability("code_generation")
    """
    
    def __init__(self) -> None:
        """Initialize the agent registry."""
        self._agents: Dict[str, AgentInfo] = {}
        self._capabilities: Dict[str, Set[str]] = {}  # capability -> agent_ids
        self._logger = AgentLogger("AgentRegistry")
    
    def register_agent(
        self,
        agent_id: str,
        agent_type: str,
        name: str,
        capabilities: List[str],
        metadata: Optional[Dict[str, Any]] = None
    ) -> AgentInfo:
        """Register a new agent.
        
        Args:
            agent_id: Unique agent identifier
            agent_type: Type of agent (CoderAgent, SelfHealingAgent, etc.)
            name: Human-readable name
            capabilities: List of capabilities this agent provides
            metadata: Optional additional metadata
            
        Returns:
            The registered AgentInfo
        """
        agent_info = AgentInfo(
            agent_id=agent_id,
            agent_type=agent_type,
            name=name,
            status=AgentStatus.IDLE,
            capabilities=capabilities,
            last_heartbeat=datetime.utcnow().isoformat(),
            metadata=metadata or {}
        )
        
        self._agents[agent_id] = agent_info
        
        # Index capabilities
        for capability in capabilities:
            if capability not in self._capabilities:
                self._capabilities[capability] = set()
            self._capabilities[capability].add(agent_id)
        
        self._logger.info(f"Registered agent: {agent_id} ({agent_type})")
        return agent_info
    
    def unregister_agent(self, agent_id: str) -> bool:
        """Unregister an agent.
        
        Args:
            agent_id: Agent to remove
            
        Returns:
            True if agent was found and removed
        """
        if agent_id not in self._agents:
            return False
        
        agent = self._agents[agent_id]
        
        # Remove from capability indices
        for capability in agent.capabilities:
            if capability in self._capabilities:
                self._capabilities[capability].discard(agent_id)
        
        del self._agents[agent_id]
        self._logger.info(f"Unregistered agent: {agent_id}")
        return True
    
    def get_agent(self, agent_id: str) -> Optional[AgentInfo]:
        """Get information about a specific agent.
        
        Args:
            agent_id: Agent identifier
            
        Returns:
            AgentInfo if found, None otherwise
        """
        return self._agents.get(agent_id)
    
    def update_agent_status(self, agent_id: str, status: AgentStatus) -> bool:
        """Update an agent's status.
        
        Args:
            agent_id: Agent to update
            status: New status
            
        Returns:
            True if agent was found and updated
        """
        if agent_id not in self._agents:
            return False
        
        self._agents[agent_id].status = status
        self._agents[agent_id].last_heartbeat = datetime.utcnow().isoformat()
        
        if status == AgentStatus.ERROR:
            self._agents[agent_id].error_count += 1
        
        return True
    
    def update_heartbeat(self, agent_id: str) -> bool:
        """Update an agent's last heartbeat timestamp.
        
        Args:
            agent_id: Agent to update
            
        Returns:
            True if agent was found and updated
        """
        if agent_id not in self._agents:
            return False
        
        self._agents[agent_id].last_heartbeat = datetime.utcnow().isoformat()
        return True
    
    def find_agents_by_capability(self, capability: str) -> List[AgentInfo]:
        """Find all agents with a specific capability.
        
        Args:
            capability: Capability to search for
            
        Returns:
            List of agents with the capability
        """
        agent_ids = self._capabilities.get(capability, set())
        return [self._agents[agent_id] for agent_id in agent_ids if agent_id in self._agents]
    
    def find_agents_by_type(self, agent_type: str) -> List[AgentInfo]:
        """Find all agents of a specific type.
        
        Args:
            agent_type: Type of agent to find
            
        Returns:
            List of matching agents
        """
        return [
            agent for agent in self._agents.values()
            if agent.agent_type == agent_type
        ]
    
    def get_available_agents(self) -> List[AgentInfo]:
        """Get all agents that are currently available (idle).
        
        Returns:
            List of available agents
        """
        return [
            agent for agent in self._agents.values()
            if agent.status == AgentStatus.IDLE
        ]
    
    def get_all_agents(self) -> List[AgentInfo]:
        """Get all registered agents.
        
        Returns:
            List of all agents
        """
        return list(self._agents.values())
    
    def get_health_summary(self) -> Dict[str, Any]:
        """Get a summary of agent health.
        
        Returns:
            Dictionary with health statistics
        """
        total = len(self._agents)
        by_status = {}
        for agent in self._agents.values():
            by_status[agent.status] = by_status.get(agent.status, 0) + 1
        
        return {
            "total_agents": total,
            "by_status": by_status,
            "idle": by_status.get(AgentStatus.IDLE, 0),
            "busy": by_status.get(AgentStatus.BUSY, 0),
            "error": by_status.get(AgentStatus.ERROR, 0),
            "offline": by_status.get(AgentStatus.OFFLINE, 0)
        }


class MessageRouter:
    """Routes messages between agents.
    
    Provides intelligent message routing between agents, including:
    - Direct routing to specific agents
    - Broadcasting to agents with specific capabilities
    - Load balancing across available agents
    
    Example:
        >>> router = MessageRouter(registry)
        >>> router.route_to_capability("code_generation", task_message)
    """
    
    def __init__(self, registry: AgentRegistry) -> None:
        """Initialize the message router.
        
        Args:
            registry: AgentRegistry for agent discovery
        """
        self._registry = registry
        self._logger = AgentLogger("MessageRouter")
        self._route_history: List[Dict[str, Any]] = []
    
    def route_to_agent(
        self,
        agent_id: str,
        message: OctoMessage,
        wait_for_response: bool = False,
        timeout: float = 30.0
    ) -> Optional[OctoMessage]:
        """Route a message directly to a specific agent.
        
        Args:
            agent_id: Target agent
            message: Message to route
            wait_for_response: Whether to wait for a response
            timeout: Timeout for response waiting
            
        Returns:
            Response message if wait_for_response is True, None otherwise
        """
        agent = self._registry.get_agent(agent_id)
        if not agent:
            self._logger.error(f"Cannot route to unknown agent: {agent_id}")
            return None
        
        if agent.status == AgentStatus.OFFLINE:
            self._logger.warning(f"Routing to offline agent: {agent_id}")
        
        # Update message receiver
        message.receiver = agent_id
        
        # Log route
        self._route_history.append({
            "timestamp": datetime.utcnow().isoformat(),
            "from": message.sender,
            "to": agent_id,
            "type": message.type
        })
        
        self._logger.info(f"Routed message from {message.sender} to {agent_id}")
        
        if wait_for_response:
            # This would integrate with the message queue response handling
            # For now, return None as async response handling is handled separately
            pass
        
        return None
    
    def route_to_capability(
        self,
        capability: str,
        message: OctoMessage,
        strategy: str = "round_robin"
    ) -> Optional[str]:
        """Route a message to an agent with a specific capability.
        
        Args:
            capability: Required capability
            message: Message to route
            strategy: Routing strategy ("round_robin", "least_busy", "random")
            
        Returns:
            Agent ID if routed successfully, None otherwise
        """
        agents = self._registry.find_agents_by_capability(capability)
        
        # Filter for available agents
        available = [a for a in agents if a.status == AgentStatus.IDLE]
        
        if not available:
            self._logger.warning(f"No available agents for capability: {capability}")
            return None
        
        # Select agent based on strategy
        selected = None
        if strategy == "round_robin":
            # Simple round-robin based on task count
            selected = min(available, key=lambda a: a.task_count)
        elif strategy == "least_busy":
            # Select agent with least current load
            selected = min(available, key=lambda a: a.task_count)
        elif strategy == "random":
            import random
            selected = random.choice(available)
        else:
            selected = available[0]
        
        # Route to selected agent
        self.route_to_agent(selected.agent_id, message)
        
        # Update agent status
        self._registry.update_agent_status(selected.agent_id, AgentStatus.BUSY)
        
        return selected.agent_id
    
    def broadcast_to_agents(
        self,
        agent_type: str,
        message: OctoMessage
    ) -> List[str]:
        """Broadcast a message to all agents of a specific type.
        
        Args:
            agent_type: Type of agents to broadcast to
            message: Message to broadcast
            
        Returns:
            List of agent IDs that received the message
        """
        agents = self._registry.find_agents_by_type(agent_type)
        agent_ids = []
        
        for agent in agents:
            message_copy = message.model_copy()
            message_copy.receiver = agent.agent_id
            # Would publish to message queue here
            agent_ids.append(agent.agent_id)
        
        self._logger.info(f"Broadcast to {len(agent_ids)} {agent_type} agents")
        return agent_ids
    
    def get_route_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent routing history.
        
        Args:
            limit: Maximum number of entries to return
            
        Returns:
            List of recent routes
        """
        return self._route_history[-limit:]


class WorkflowOrchestrator:
    """Orchestrates multi-step workflows across multiple agents.
    
    Manages the execution of complex workflows that require coordination
    between multiple agents, handling dependencies, retries, and error recovery.
    
    Example:
        >>> orchestrator = WorkflowOrchestrator(router, registry)
        >>> workflow = orchestrator.create_workflow("create_primitive", [
        ...     WorkflowStep(agent_type="CoderAgent", action="create_code", ...),
        ...     WorkflowStep(agent_type="SelfHealingAgent", action="test_code", ...),
        ... ])
        >>> result = await orchestrator.execute_workflow(workflow.workflow_id)
    """
    
    def __init__(
        self,
        router: MessageRouter,
        registry: AgentRegistry
    ) -> None:
        """Initialize the workflow orchestrator.
        
        Args:
            router: MessageRouter for inter-agent communication
            registry: AgentRegistry for agent discovery
        """
        self._router = router
        self._registry = registry
        self._logger = AgentLogger("WorkflowOrchestrator")
        self._workflows: Dict[UUID, Workflow] = {}
        self._active_tasks: Dict[UUID, WorkflowStep] = {}
    
    def create_workflow(
        self,
        name: str,
        description: str,
        steps: List[WorkflowStep]
    ) -> Workflow:
        """Create a new workflow definition.
        
        Args:
            name: Workflow name
            description: Workflow description
            steps: List of workflow steps
            
        Returns:
            Created workflow
        """
        workflow = Workflow(
            workflow_id=uuid4(),
            name=name,
            description=description,
            steps=steps
        )
        
        self._workflows[workflow.workflow_id] = workflow
        self._logger.info(f"Created workflow: {name} ({workflow.workflow_id})")
        
        return workflow
    
    async def execute_workflow(
        self,
        workflow_id: UUID,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Execute a workflow.
        
        Args:
            workflow_id: Workflow to execute
            context: Optional execution context
            
        Returns:
            Workflow execution results
        """
        if workflow_id not in self._workflows:
            raise ValueError(f"Workflow not found: {workflow_id}")
        
        workflow = self._workflows[workflow_id]
        workflow.status = TaskStatus.IN_PROGRESS
        
        self._logger.info(f"Starting workflow: {workflow.name}")
        
        try:
            # Build dependency graph
            completed_steps: Set[UUID] = set()
            failed_steps: Set[UUID] = set()
            
            while len(completed_steps) + len(failed_steps) < len(workflow.steps):
                # Find next executable steps (dependencies satisfied)
                executable = self._get_executable_steps(
                    workflow, completed_steps, failed_steps
                )
                
                if not executable:
                    if failed_steps:
                        # Some steps failed and blocked others
                        workflow.status = TaskStatus.FAILED
                        break
                    # Deadlock - no executable steps but not all completed
                    workflow.status = TaskStatus.FAILED
                    workflow.errors.append({
                        "error": "Workflow deadlock - dependencies cannot be satisfied"
                    })
                    break
                
                # Execute steps in parallel where possible
                tasks = [
                    self._execute_step(workflow, step, context)
                    for step in executable
                ]
                
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Process results
                for step, result in zip(executable, results):
                    if isinstance(result, Exception):
                        step.retry_count += 1
                        if step.retry_count >= step.max_retries:
                            failed_steps.add(step.step_id)
                            workflow.errors.append({
                                "step": step.step_id,
                                "error": str(result)
                            })
                        else:
                            self._logger.warning(
                                f"Step {step.step_id} failed, retry {step.retry_count}/{step.max_retries}"
                            )
                    else:
                        completed_steps.add(step.step_id)
                        workflow.results[step.step_id] = result
            
            # Determine final status
            if failed_steps:
                workflow.status = TaskStatus.FAILED
            else:
                workflow.status = TaskStatus.COMPLETED
            
            workflow.completed_at = datetime.utcnow().isoformat()
            
            self._logger.info(
                f"Workflow {workflow.name} completed with status: {workflow.status}"
            )
            
            return {
                "workflow_id": workflow_id,
                "status": workflow.status,
                "results": workflow.results,
                "errors": workflow.errors,
                "completed_at": workflow.completed_at
            }
            
        except Exception as e:
            workflow.status = TaskStatus.FAILED
            workflow.errors.append({"error": str(e)})
            workflow.completed_at = datetime.utcnow().isoformat()
            
            self._logger.error(f"Workflow execution failed: {e}")
            
            return {
                "workflow_id": workflow_id,
                "status": TaskStatus.FAILED,
                "error": str(e)
            }
    
    def _get_executable_steps(
        self,
        workflow: Workflow,
        completed: Set[UUID],
        failed: Set[UUID]
    ) -> List[WorkflowStep]:
        """Get steps that are ready to execute.
        
        Args:
            workflow: The workflow
            completed: Set of completed step IDs
            failed: Set of failed step IDs
            
        Returns:
            List of executable steps
        """
        executable = []
        
        for step in workflow.steps:
            # Skip already processed steps
            if step.step_id in completed or step.step_id in failed:
                continue
            
            # Check if dependencies are satisfied
            deps_satisfied = all(
                dep in completed for dep in step.depends_on
            )
            
            # Check if any dependency failed
            deps_failed = any(
                dep in failed for dep in step.depends_on
            )
            
            if deps_failed:
                # Mark as failed due to dependency failure
                failed.add(step.step_id)
                workflow.errors.append({
                    "step": step.step_id,
                    "error": "Dependency step failed"
                })
            elif deps_satisfied:
                executable.append(step)
        
        return executable
    
    async def _execute_step(
        self,
        workflow: Workflow,
        step: WorkflowStep,
        context: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Execute a single workflow step.
        
        Args:
            workflow: Parent workflow
            step: Step to execute
            context: Execution context
            
        Returns:
            Step execution results
        """
        workflow.current_step = step.step_id
        
        self._logger.info(
            f"Executing step {step.step_id}: {step.agent_type}.{step.action}"
        )
        
        # Find agent with required capability
        agent_type_map = {
            "CoderAgent": "code_generation",
            "SelfHealingAgent": "debugging",
            "Supervisor": "security_review"
        }
        
        capability = agent_type_map.get(step.agent_type, step.agent_type.lower())
        agents = self._registry.find_agents_by_capability(capability)
        
        if not agents:
            raise RuntimeError(f"No agent available for capability: {capability}")
        
        # Select available agent
        available = [a for a in agents if a.status == AgentStatus.IDLE]
        if not available:
            available = agents  # Use any agent if none are idle
        
        agent = min(available, key=lambda a: a.task_count)
        
        # Create task payload
        params = step.params.copy()
        if context:
            params["_context"] = context
            params["_workflow_id"] = str(workflow.workflow_id)
        
        task_payload = TaskPayload(
            action=step.action,
            params=params,
            priority=8  # High priority for workflow tasks
        )
        
        # Create message
        message = OctoMessage(
            sender="ManagerAgent",
            receiver=agent.agent_id,
            type=MessageType.TASK,
            payload=task_payload
        )
        
        # Update agent status
        self._registry.update_agent_status(agent.agent_id, AgentStatus.BUSY)
        agent.current_task = task_payload.task_id
        agent.task_count += 1
        
        # Track active task
        self._active_tasks[task_payload.task_id] = step
        
        try:
            # Dynamically get the agent singleton and execute
            if step.agent_type == "CoderAgent":
                from src.specialist.coder_agent import get_coder_agent
                agent_instance = get_coder_agent()
            elif step.agent_type == "SelfHealingAgent":
                from src.specialist.self_healing_agent import get_self_healing_agent
                agent_instance = get_self_healing_agent()
            elif step.agent_type == "Supervisor":
                from src.engine.supervisor import get_supervisor
                agent_instance = get_supervisor()
            else:
                raise RuntimeError(f"Unknown agent type: {step.agent_type}")
                
            execution_result = await agent_instance.execute_task(task_payload)
            
        except Exception as e:
            self._logger.error(f"Step execution failed: {e}")
            execution_result = {"status": "error", "message": str(e)}
        
        # Update agent status back to idle
        self._registry.update_agent_status(agent.agent_id, AgentStatus.IDLE)
        agent.current_task = None
        
        return {
            "step_id": step.step_id,
            "agent_id": agent.agent_id,
            "status": execution_result.get("status", "completed"),
            "result": execution_result
        }
    
    def get_workflow_status(self, workflow_id: UUID) -> Optional[Workflow]:
        """Get the current status of a workflow.
        
        Args:
            workflow_id: Workflow to check
            
        Returns:
            Workflow status if found
        """
        return self._workflows.get(workflow_id)
    
    def cancel_workflow(self, workflow_id: UUID) -> bool:
        """Cancel a running workflow.
        
        Args:
            workflow_id: Workflow to cancel
            
        Returns:
            True if cancelled successfully
        """
        if workflow_id not in self._workflows:
            return False
        
        workflow = self._workflows[workflow_id]
        
        if workflow.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
            return False
        
        workflow.status = TaskStatus.CANCELLED
        workflow.completed_at = datetime.utcnow().isoformat()
        
        self._logger.info(f"Cancelled workflow: {workflow.name}")
        
        return True


class ManagerAgent(BaseAgent):
    """Manager Agent - Coordinates specialist agents and workflows.
    
    The Manager Agent is responsible for:
    1. Routing messages between specialist agents (Coder, Self-Healing)
    2. Managing agent lifecycle (start, stop, restart)
    3. Monitoring agent health and status
    4. Orchestrating multi-agent workflows
    5. Load balancing between agent instances
    
    Example:
        >>> manager = ManagerAgent()
        >>> await manager.start()
        >>> 
        >>> # Execute a multi-agent workflow
        >>> result = await manager.execute_task(TaskPayload(
        ...     action="create_primitive_workflow",
        ...     params={"description": "Create S3 upload tool"}
        ... ))
    """
    
    def __init__(self, context: Optional[Any] = None) -> None:
        """Initialize the Manager Agent.
        
        Args:
            context: Shared agent context
        """
        super().__init__(name="ManagerAgent", context=context)
        self.agent_logger = AgentLogger("ManagerAgent")
        self._config = get_config()
        
        # Core components
        self._registry = AgentRegistry()
        self._router = MessageRouter(self._registry)
        self._orchestrator = WorkflowOrchestrator(self._router, self._registry)
        
        # Health monitoring
        self._health_check_task: Optional[asyncio.Task] = None
        self._health_check_interval = 30  # seconds
        
        # Known agent types and their configurations
        self._agent_configs: Dict[str, Dict[str, Any]] = {
            "CoderAgent": {
                "capabilities": ["code_generation", "code_modification", "debugging"],
                "module": "src.specialist.coder_agent",
                "class": "CoderAgent"
            },
            "SelfHealingAgent": {
                "capabilities": ["debugging", "error_analysis", "auto_repair"],
                "module": "src.specialist.self_healing_agent",
                "class": "SelfHealingAgent"
            }
        }
        
        self.agent_logger.info("ManagerAgent initialized")
    
    async def on_start(self) -> None:
        """Start health monitoring and register self."""
        # Register self in registry
        self._registry.register_agent(
            agent_id=self.name,
            agent_type="ManagerAgent",
            name="Manager Agent",
            capabilities=[
                "agent_management",
                "workflow_orchestration",
                "message_routing",
                "load_balancing"
            ]
        )
        
        # Start health monitoring
        self._health_check_task = asyncio.create_task(
            self._health_monitoring_loop()
        )
        
        self.agent_logger.info("ManagerAgent started with health monitoring")
    
    async def on_stop(self) -> None:
        """Stop health monitoring."""
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
        
        # Unregister self
        self._registry.unregister_agent(self.name)
        
        self.agent_logger.info("ManagerAgent stopped")
    
    async def execute_task(self, task: TaskPayload) -> Dict[str, Any]:
        """Execute a task assigned to the Manager Agent.
        
        Args:
            task: The task payload
            
        Returns:
            Task execution results
        """
        self.agent_logger.info(f"Executing task: {task.action}")
        
        try:
            if task.action == "create_primitive_workflow":
                return await self._handle_create_primitive_workflow(task.params)
            
            elif task.action == "route_message":
                return self._handle_route_message(task.params)
            
            elif task.action == "start_agent":
                return await self._handle_start_agent(task.params)
            
            elif task.action == "stop_agent":
                return await self._handle_stop_agent(task.params)
            
            elif task.action == "get_agent_status":
                return self._handle_get_agent_status(task.params)
            
            elif task.action == "get_health_summary":
                return self._handle_get_health_summary()
            
            elif task.action == "execute_workflow":
                return await self._handle_execute_workflow(task.params)
            
            elif task.action == "register_agent":
                return self._handle_register_agent(task.params)
            
            else:
                return {
                    "status": "error",
                    "error": f"Unknown task action: {task.action}"
                }
                
        except Exception as e:
            self.agent_logger.error(f"Task execution failed: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    async def _handle_create_primitive_workflow(
        self,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle the create primitive workflow.
        
        This workflow:
        1. Routes to CoderAgent to generate code
        2. Routes to SelfHealingAgent for testing
        3. Routes to Supervisor for approval
        4. Registers with IntentFinder on approval
        
        Args:
            params: Workflow parameters including description
            
        Returns:
            Workflow results
        """
        description = params.get("description", "")
        name = params.get("name", f"primitive_{uuid4().hex[:8]}")
        
        self.agent_logger.info(f"Creating primitive workflow: {name}")
        
        # Create workflow steps
        steps = [
            WorkflowStep(
                step_id=uuid4(),
                agent_type="CoderAgent",
                action="create_primitive",
                params={
                    "description": description,
                    "name": name,
                    "language": params.get("language", "python")
                }
            ),
            WorkflowStep(
                step_id=uuid4(),
                agent_type="SelfHealingAgent",
                action="test_code",
                params={},
                depends_on=[]  # Will be set after first step
            ),
            WorkflowStep(
                step_id=uuid4(),
                agent_type="Supervisor",
                action="review_and_approve",
                params={},
                depends_on=[]  # Will be set after second step
            )
        ]
        
        # Set up dependencies (linear workflow)
        steps[1].depends_on = [steps[0].step_id]
        steps[2].depends_on = [steps[1].step_id]
        
        # Create and execute workflow
        workflow = self._orchestrator.create_workflow(
            name=f"create_primitive_{name}",
            description=f"Create and approve primitive: {description}",
            steps=steps
        )
        
        result = await self._orchestrator.execute_workflow(workflow.workflow_id)
        
        return {
            "status": "success" if result["status"] == TaskStatus.COMPLETED else "error",
            "workflow_id": str(workflow.workflow_id),
            "result": result
        }
    
    def _handle_route_message(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle message routing request.
        
        Args:
            params: Routing parameters
            
        Returns:
            Routing result
        """
        target_agent = params.get("target_agent")
        target_capability = params.get("target_capability")
        message_data = params.get("message", {})
        
        # Reconstruct message (simplified)
        message = OctoMessage(
            sender=self.name,
            receiver=target_agent or "",
            type=MessageType.TASK,
            payload=message_data
        )
        
        if target_agent:
            self._router.route_to_agent(target_agent, message)
            return {"status": "success", "routed_to": target_agent}
        
        elif target_capability:
            agent_id = self._router.route_to_capability(target_capability, message)
            if agent_id:
                return {"status": "success", "routed_to": agent_id}
            else:
                return {"status": "error", "error": f"No agent for capability: {target_capability}"}
        
        return {"status": "error", "error": "No target specified"}
    
    async def _handle_start_agent(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle agent start request.
        
        Args:
            params: Agent configuration
            
        Returns:
            Start result
        """
        agent_type = params.get("agent_type")
        
        if agent_type not in self._agent_configs:
            return {"status": "error", "error": f"Unknown agent type: {agent_type}"}
        
        config = self._agent_configs[agent_type]
        agent_id = params.get("agent_id", f"{agent_type}_{uuid4().hex[:8]}")
        
        # Register agent
        self._registry.register_agent(
            agent_id=agent_id,
            agent_type=agent_type,
            name=params.get("name", agent_id),
            capabilities=config["capabilities"],
            metadata={"auto_started": True}
        )
        
        # In real implementation, this would:
        # 1. Dynamically import the agent class
        # 2. Instantiate and start the agent
        # 3. Return the agent instance
        
        self.agent_logger.info(f"Started agent: {agent_id} ({agent_type})")
        
        return {
            "status": "success",
            "agent_id": agent_id,
            "agent_type": agent_type
        }
    
    async def _handle_stop_agent(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle agent stop request.
        
        Args:
            params: Stop parameters
            
        Returns:
            Stop result
        """
        agent_id = params.get("agent_id")
        
        if not agent_id:
            return {"status": "error", "error": "agent_id required"}
        
        agent = self._registry.get_agent(agent_id)
        if not agent:
            return {"status": "error", "error": f"Agent not found: {agent_id}"}
        
        # Update status to stopping
        self._registry.update_agent_status(agent_id, AgentStatus.STOPPING)
        
        # In real implementation, this would:
        # 1. Send stop signal to agent
        # 2. Wait for graceful shutdown
        # 3. Unregister agent
        
        # Unregister
        self._registry.unregister_agent(agent_id)
        
        self.agent_logger.info(f"Stopped agent: {agent_id}")
        
        return {"status": "success", "agent_id": agent_id}
    
    def _handle_get_agent_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle agent status query.
        
        Args:
            params: Query parameters
            
        Returns:
            Agent status
        """
        agent_id = params.get("agent_id")
        
        if agent_id:
            agent = self._registry.get_agent(agent_id)
            if agent:
                return {
                    "status": "success",
                    "agent": {
                        "agent_id": agent.agent_id,
                        "agent_type": agent.agent_type,
                        "name": agent.name,
                        "status": agent.status,
                        "capabilities": agent.capabilities,
                        "task_count": agent.task_count,
                        "error_count": agent.error_count,
                        "last_heartbeat": agent.last_heartbeat
                    }
                }
            return {"status": "error", "error": f"Agent not found: {agent_id}"}
        
        # Return all agents
        agents = self._registry.get_all_agents()
        return {
            "status": "success",
            "agents": [
                {
                    "agent_id": a.agent_id,
                    "agent_type": a.agent_type,
                    "name": a.name,
                    "status": a.status
                }
                for a in agents
            ],
            "count": len(agents)
        }
    
    def _handle_get_health_summary(self) -> Dict[str, Any]:
        """Handle health summary request.
        
        Returns:
            Health summary
        """
        summary = self._registry.get_health_summary()
        return {
            "status": "success",
            "summary": summary,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    async def _handle_execute_workflow(
        self,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle workflow execution request.
        
        Args:
            params: Workflow parameters
            
        Returns:
            Execution results
        """
        workflow_id_param = params.get("workflow_id")
        
        if workflow_id_param:
            workflow_id = UUID(workflow_id_param)
            return await self._orchestrator.execute_workflow(workflow_id)
        
        # Create and execute new workflow
        steps_data = params.get("steps", [])
        steps = []
        
        for step_data in steps_data:
            step = WorkflowStep(
                step_id=uuid4(),
                agent_type=step_data["agent_type"],
                action=step_data["action"],
                params=step_data.get("params", {}),
                depends_on=[UUID(d) for d in step_data.get("depends_on", [])]
            )
            steps.append(step)
        
        workflow = self._orchestrator.create_workflow(
            name=params.get("name", "custom_workflow"),
            description=params.get("description", ""),
            steps=steps
        )
        
        result = await self._orchestrator.execute_workflow(workflow.workflow_id)
        
        return {
            "status": "success",
            "workflow_id": str(workflow.workflow_id),
            "result": result
        }
    
    def _handle_register_agent(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle agent registration request.
        
        Args:
            params: Agent registration parameters
            
        Returns:
            Registration result
        """
        agent_id = params.get("agent_id")
        agent_type = params.get("agent_type")
        name = params.get("name", agent_id)
        capabilities = params.get("capabilities", [])
        
        if not agent_id or not agent_type:
            return {"status": "error", "error": "agent_id and agent_type required"}
        
        agent = self._registry.register_agent(
            agent_id=agent_id,
            agent_type=agent_type,
            name=name,
            capabilities=capabilities,
            metadata=params.get("metadata", {})
        )
        
        return {
            "status": "success",
            "agent_id": agent.agent_id,
            "agent_type": agent.agent_type
        }
    
    async def _health_monitoring_loop(self) -> None:
        """Background task for health monitoring."""
        while True:
            try:
                await asyncio.sleep(self._health_check_interval)
                
                # Check all registered agents
                agents = self._registry.get_all_agents()
                current_time = datetime.utcnow()
                
                for agent in agents:
                    last_heartbeat = datetime.fromisoformat(agent.last_heartbeat)
                    time_since_heartbeat = (current_time - last_heartbeat).total_seconds()
                    
                    # Mark as offline if no heartbeat for 2 minutes
                    if time_since_heartbeat > 120:
                        if agent.status != AgentStatus.OFFLINE:
                            self._registry.update_agent_status(
                                agent.agent_id,
                                AgentStatus.OFFLINE
                            )
                            self.agent_logger.warning(
                                f"Agent {agent.agent_id} marked offline - no heartbeat for {time_since_heartbeat}s"
                            )
                    
                    # Check for stuck agents (busy for too long)
                    if agent.status == AgentStatus.BUSY and agent.current_task:
                        # Would check task duration here
                        pass
                
                # Log health summary periodically
                summary = self._registry.get_health_summary()
                if summary["error"] > 0 or summary["offline"] > 0:
                    self.agent_logger.warning(f"Health check: {summary}")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.agent_logger.error(f"Health monitoring error: {e}")
    
    def get_registry(self) -> AgentRegistry:
        """Get the agent registry.
        
        Returns:
            AgentRegistry instance
        """
        return self._registry
    
    def get_router(self) -> MessageRouter:
        """Get the message router.
        
        Returns:
            MessageRouter instance
        """
        return self._router
    
    def get_orchestrator(self) -> WorkflowOrchestrator:
        """Get the workflow orchestrator.
        
        Returns:
            WorkflowOrchestrator instance
        """
        return self._orchestrator


# Singleton instance for easy access
_manager_agent: Optional[ManagerAgent] = None


def get_manager_agent() -> ManagerAgent:
    """Get or create the singleton ManagerAgent instance.
    
    Returns:
        ManagerAgent singleton instance
    """
    global _manager_agent
    if _manager_agent is None:
        _manager_agent = ManagerAgent()
    return _manager_agent
