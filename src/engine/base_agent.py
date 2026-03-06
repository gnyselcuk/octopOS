"""Base Agent - Abstract base class for all octopOS agents.

This module provides the foundational class that all agents in the octopOS
system inherit from. It defines the common interface for agent lifecycle,
messaging, and task execution.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from uuid import UUID

from src.engine.message import (
    AgentContext,
    ErrorPayload,
    ErrorSeverity,
    MessageType,
    OctoMessage,
    TaskPayload,
    TaskStatus,
    get_message_queue,
)


class BaseAgent(ABC):
    """Abstract base class for all octopOS agents.
    
    All agents in the system (MainBrain, CoderAgent, etc.) inherit from this
    class. It provides common functionality for:
    - Message sending/receiving via OctoMessage protocol
    - Lifecycle management (start, stop, pause)
    - State tracking
    - Error handling and reporting
    
    Example:
        >>> class MyAgent(BaseAgent):
        ...     async def execute_task(self, task: TaskPayload) -> Dict[str, Any]:
        ...         # Task implementation
        ...         return {"status": "success"}
    """
    
    def __init__(
        self,
        name: str,
        context: Optional[AgentContext] = None
    ) -> None:
        """Initialize the agent.
        
        Args:
            name: Unique identifier for this agent
            context: Shared agent context (workspace, region, etc.)
        """
        self.name = name
        self.context = context or AgentContext()
        self._state: TaskStatus = TaskStatus.PENDING
        self._current_task: Optional[TaskPayload] = None
        self._message_queue = get_message_queue()
        self._is_running: bool = False
        
        # Subscribe to messages
        self._message_queue.subscribe(self.name, self._on_message)
    
    @property
    def state(self) -> TaskStatus:
        """Get current agent state."""
        return self._state
    
    @property
    def is_running(self) -> bool:
        """Check if agent is currently running."""
        return self._is_running
    
    @abstractmethod
    async def execute_task(self, task: TaskPayload) -> Dict[str, Any]:
        """Execute a task assigned to this agent.
        
        This is the main method that subclasses must implement. It contains
        the agent-specific logic for processing tasks.
        
        Args:
            task: The task payload containing action and parameters
            
        Returns:
            Dictionary containing task results
            
        Raises:
            NotImplementedError: Must be implemented by subclasses
        """
        raise NotImplementedError("Subclasses must implement execute_task()")
    
    async def start(self) -> None:
        """Start the agent and begin processing messages.
        
        This method initializes the agent and sets its state to ready.
        Subclasses can override this to add custom startup logic.
        """
        self._is_running = True
        self._state = TaskStatus.IN_PROGRESS
        await self.on_start()
    
    async def stop(self) -> None:
        """Stop the agent gracefully.
        
        This method shuts down the agent and sets its state to completed.
        Subclasses should override on_stop() for custom cleanup.
        """
        self._is_running = False
        self._state = TaskStatus.COMPLETED
        await self.on_stop()
    
    async def pause(self) -> None:
        """Pause the agent temporarily.
        
        The agent will stop processing new tasks but maintains its state.
        Can be resumed with resume().
        """
        self._state = TaskStatus.PAUSED
        await self.on_pause()
    
    async def resume(self) -> None:
        """Resume a paused agent."""
        if self._state == TaskStatus.PAUSED:
            self._state = TaskStatus.IN_PROGRESS
            await self.on_resume()
    
    async def on_start(self) -> None:
        """Hook called when agent starts. Override in subclasses."""
        pass
    
    async def on_stop(self) -> None:
        """Hook called when agent stops. Override in subclasses."""
        pass
    
    async def on_pause(self) -> None:
        """Hook called when agent pauses. Override in subclasses."""
        pass
    
    async def on_resume(self) -> None:
        """Hook called when agent resumes. Override in subclasses."""
        pass
    
    def send_message(
        self,
        receiver: str,
        msg_type: MessageType,
        payload: Any,
        correlation_id: Optional[UUID] = None
    ) -> OctoMessage:
        """Send a message to another agent.
        
        Args:
            receiver: Name of the target agent
            msg_type: Type of message (TASK, ERROR, etc.)
            payload: Message payload
            correlation_id: Optional correlation ID for related messages
            
        Returns:
            The sent OctoMessage
        """
        message = OctoMessage(
            sender=self.name,
            receiver=receiver,
            type=msg_type,
            payload=payload,
            context=self.context,
            correlation_id=correlation_id
        )
        self._message_queue.publish(message)
        return message
    
    def send_error(
        self,
        receiver: str,
        error_type: str,
        error_message: str,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        suggestion: Optional[str] = None,
        correlation_id: Optional[UUID] = None
    ) -> OctoMessage:
        """Send an error message to another agent (typically Self-Healing).
        
        Args:
            receiver: Name of the agent to receive the error
            error_type: Classification of the error
            error_message: Human-readable description
            severity: Error severity level
            suggestion: Suggested fix or workaround
            correlation_id: Optional correlation ID
            
        Returns:
            The sent error OctoMessage
        """
        error_payload = ErrorPayload(
            error_type=error_type,
            error_message=error_message,
            severity=severity,
            suggestion=suggestion
        )
        return self.send_message(
            receiver=receiver,
            msg_type=MessageType.ERROR,
            payload=error_payload,
            correlation_id=correlation_id
        )
    
    def request_approval(
        self,
        action_type: str,
        action_description: str,
        security_scan: Optional[Dict[str, Any]] = None,
        code_changes: Optional[str] = None
    ) -> OctoMessage:
        """Request approval from the Supervisor agent.
        
        Used when an agent needs authorization for sensitive operations
        like creating new primitives or making system changes.
        
        Args:
            action_type: Type of action requiring approval
            action_description: Human-readable description
            security_scan: Optional security scan results
            code_changes: Optional code changes for review
            
        Returns:
            The sent approval request message
        """
        from src.engine.message import ApprovalPayload
        
        approval_payload = ApprovalPayload(
            action_type=action_type,
            action_description=action_description,
            security_scan=security_scan,
            code_changes=code_changes
        )
        return self.send_message(
            receiver="Supervisor",
            msg_type=MessageType.APPROVAL_REQUEST,
            payload=approval_payload
        )
    
    def _on_message(self, message: OctoMessage) -> None:
        """Handle incoming messages.
        
        This internal method processes messages from the queue. It routes
        TASK messages to execute_task() and handles other message types.
        
        Args:
            message: The received OctoMessage
        """
        if message.type == MessageType.TASK and isinstance(message.payload, TaskPayload):
            self._current_task = message.payload
            # Note: In async context, this would be awaited
            # For now, we store it for later processing
        elif message.type == MessageType.SYSTEM:
            self._handle_system_message(message)
    
    def _handle_system_message(self, message: OctoMessage) -> None:
        """Handle system-level messages.
        
        Args:
            message: System message to process
        """
        # Override in subclasses for system message handling
        pass
    
    def get_pending_messages(self) -> List[OctoMessage]:
        """Get all pending messages for this agent.
        
        Returns:
            List of messages addressed to this agent
        """
        return self._message_queue.get_messages_for(self.name)
    
    def report_status(
        self,
        task_id: UUID,
        status: TaskStatus,
        progress: float = 0.0,
        message: Optional[str] = None,
        result: Optional[Dict[str, Any]] = None
    ) -> None:
        """Report task status update.
        
        Args:
            task_id: ID of the task being reported
            status: Current task status
            progress: Progress percentage (0-100)
            message: Status description
            result: Partial or final results
        """
        from src.engine.message import StatusPayload
        
        status_payload = StatusPayload(
            task_id=task_id,
            status=status,
            progress=progress,
            message=message,
            result=result
        )
        # Send to parent/Manager agent
        self.send_message(
            receiver="ManagerAgent",
            msg_type=MessageType.STATUS_UPDATE,
            payload=status_payload
        )
    
    def __repr__(self) -> str:
        """String representation of the agent."""
        return f"{self.__class__.__name__}(name='{self.name}', state={self.state})"
