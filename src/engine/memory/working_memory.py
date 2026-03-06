"""Working Memory - Short-term memory for current session context.

This module implements the short-term (working) memory that:
- Maintains current conversation context
- Tracks session variables and state
- Manages conversation history within the current session
- Provides temporary storage for intermediate results
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from src.utils.config import get_config
from src.utils.logger import get_logger

logger = get_logger()


@dataclass
class ConversationTurn:
    """A single turn in the conversation."""
    
    role: str  # "user" or "assistant"
    content: str
    timestamp: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    intent_type: Optional[str] = None
    actions_taken: List[str] = field(default_factory=list)


@dataclass
class SessionVariable:
    """A session-scoped variable."""
    
    name: str
    value: Any
    scope: str  # "global", "task", "user"
    timestamp: str
    ttl: Optional[int] = None  # Time to live in seconds


@dataclass
class ContextSnapshot:
    """A snapshot of the current context."""
    
    session_id: str
    timestamp: str
    conversation_history: List[ConversationTurn]
    variables: Dict[str, Any]
    active_task: Optional[str] = None
    user_preferences: Dict[str, Any] = field(default_factory=dict)


class WorkingMemory:
    """Short-term working memory for the current session.
    
    Manages conversation flow, session variables, and immediate context
    that is only relevant for the current session. Data is lost when
    the session ends.
    
    Example:
        >>> memory = WorkingMemory(session_id="session_123")
        >>> memory.add_user_message("Create a Python script")
        >>> memory.set_variable("current_project", "my_project")
        >>> context = memory.get_context_snapshot()
    """
    
    def __init__(
        self,
        session_id: str,
        max_history: int = 50,
        max_context_tokens: int = 4000
    ) -> None:
        """Initialize working memory.
        
        Args:
            session_id: Unique session identifier
            max_history: Maximum conversation turns to retain
            max_context_tokens: Approximate token limit for context
        """
        self._session_id = session_id
        self._max_history = max_history
        self._max_context_tokens = max_context_tokens
        
        # Conversation history
        self._conversation_history: List[ConversationTurn] = []
        
        # Session variables
        self._variables: Dict[str, SessionVariable] = {}
        
        # Current session state
        self._active_task: Optional[str] = None
        self._user_context: Dict[str, Any] = {}
        
        # Timestamps
        self._created_at = datetime.utcnow().isoformat()
        self._last_activity = self._created_at
        
        logger.info(f"WorkingMemory initialized for session: {session_id}")
    
    @property
    def session_id(self) -> str:
        """Get session ID."""
        return self._session_id
    
    @property
    def created_at(self) -> str:
        """Get creation timestamp."""
        return self._created_at
    
    def add_user_message(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        intent_type: Optional[str] = None
    ) -> None:
        """Add a user message to conversation history.
        
        Args:
            content: Message content
            metadata: Additional metadata
            intent_type: Classified intent type
        """
        turn = ConversationTurn(
            role="user",
            content=content,
            timestamp=datetime.utcnow().isoformat(),
            metadata=metadata or {},
            intent_type=intent_type
        )
        self._conversation_history.append(turn)
        self._trim_history()
        self._update_activity()
        
        logger.debug(f"Added user message: {content[:50]}...")
    
    def add_assistant_message(
        self,
        content: str,
        actions_taken: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Add an assistant message to conversation history.
        
        Args:
            content: Message content
            actions_taken: List of actions performed
            metadata: Additional metadata
        """
        turn = ConversationTurn(
            role="assistant",
            content=content,
            timestamp=datetime.utcnow().isoformat(),
            metadata=metadata or {},
            actions_taken=actions_taken or []
        )
        self._conversation_history.append(turn)
        self._trim_history()
        self._update_activity()
        
        logger.debug(f"Added assistant message: {content[:50]}...")
    
    def add_system_message(self, content: str) -> None:
        """Add a system message (not counted in history limit).
        
        Args:
            content: System message content
        """
        turn = ConversationTurn(
            role="system",
            content=content,
            timestamp=datetime.utcnow().isoformat()
        )
        # Insert at beginning so it's always included
        self._conversation_history.insert(0, turn)
        logger.debug(f"Added system message: {content[:50]}...")
    
    def get_conversation_history(
        self,
        last_n: Optional[int] = None,
        include_system: bool = True
    ) -> List[ConversationTurn]:
        """Get conversation history.
        
        Args:
            last_n: Number of most recent turns to return
            include_system: Whether to include system messages
            
        Returns:
            List of conversation turns
        """
        history = self._conversation_history
        
        if not include_system:
            history = [t for t in history if t.role != "system"]
        
        if last_n:
            return history[-last_n:]
        return history
    
    def get_last_n_messages(self, n: int = 5) -> List[Dict[str, str]]:
        """Get last N messages as simple dicts.
        
        Args:
            n: Number of messages
            
        Returns:
            List of {role, content} dicts
        """
        return [
            {"role": turn.role, "content": turn.content}
            for turn in self._conversation_history[-n:]
            if turn.role in ("user", "assistant")
        ]
    
    def set_variable(
        self,
        name: str,
        value: Any,
        scope: str = "session",
        ttl: Optional[int] = None
    ) -> None:
        """Set a session variable.
        
        Args:
            name: Variable name
            value: Variable value
            scope: Variable scope ("session", "task", "global")
            ttl: Time to live in seconds
        """
        self._variables[name] = SessionVariable(
            name=name,
            value=value,
            scope=scope,
            timestamp=datetime.utcnow().isoformat(),
            ttl=ttl
        )
        logger.debug(f"Set variable {name} = {value}")
    
    def get_variable(self, name: str, default: Any = None) -> Any:
        """Get a session variable.
        
        Args:
            name: Variable name
            default: Default value if not found
            
        Returns:
            Variable value or default
        """
        if name in self._variables:
            var = self._variables[name]
            # Check TTL
            if var.ttl:
                age = (datetime.utcnow() - datetime.fromisoformat(var.timestamp)).total_seconds()
                if age > var.ttl:
                    del self._variables[name]
                    return default
            return var.value
        return default
    
    def has_variable(self, name: str) -> bool:
        """Check if a variable exists.
        
        Args:
            name: Variable name
            
        Returns:
            True if variable exists
        """
        return name in self._variables
    
    def delete_variable(self, name: str) -> bool:
        """Delete a session variable.
        
        Args:
            name: Variable name
            
        Returns:
            True if deleted
        """
        if name in self._variables:
            del self._variables[name]
            return True
        return False
    
    def get_all_variables(self, scope: Optional[str] = None) -> Dict[str, Any]:
        """Get all session variables.
        
        Args:
            scope: Filter by scope
            
        Returns:
            Dictionary of variables
        """
        if scope:
            return {
                name: var.value
                for name, var in self._variables.items()
                if var.scope == scope
            }
        return {name: var.value for name, var in self._variables.items()}
    
    def set_active_task(self, task_id: str) -> None:
        """Set the currently active task.
        
        Args:
            task_id: Task identifier
        """
        self._active_task = task_id
        logger.debug(f"Set active task: {task_id}")
    
    def get_active_task(self) -> Optional[str]:
        """Get the currently active task.
        
        Returns:
            Task ID or None
        """
        return self._active_task
    
    def clear_active_task(self) -> None:
        """Clear the active task."""
        self._active_task = None
    
    def set_user_context(self, key: str, value: Any) -> None:
        """Set user context information.
        
        Args:
            key: Context key
            value: Context value
        """
        self._user_context[key] = value
    
    def get_user_context(self, key: str, default: Any = None) -> Any:
        """Get user context information.
        
        Args:
            key: Context key
            default: Default value
            
        Returns:
            Context value or default
        """
        return self._user_context.get(key, default)
    
    def get_context_snapshot(self) -> ContextSnapshot:
        """Get a snapshot of current context.
        
        Returns:
            ContextSnapshot with current state
        """
        return ContextSnapshot(
            session_id=self._session_id,
            timestamp=datetime.utcnow().isoformat(),
            conversation_history=self._conversation_history.copy(),
            variables=self.get_all_variables(),
            active_task=self._active_task,
            user_preferences=self._user_context.copy()
        )
    
    def format_for_llm(self, max_tokens: Optional[int] = None) -> str:
        """Format conversation history for LLM context.
        
        Args:
            max_tokens: Maximum tokens to include
            
        Returns:
            Formatted context string
        """
        max_tokens = max_tokens or self._max_context_tokens
        
        parts = []
        current_tokens = 0
        
        # Add conversation history (most recent first)
        for turn in reversed(self._conversation_history):
            turn_text = f"{turn.role.upper()}: {turn.content}\n\n"
            turn_tokens = len(turn_text) // 4  # Rough estimate
            
            if current_tokens + turn_tokens > max_tokens:
                break
            
            parts.insert(0, turn_text)
            current_tokens += turn_tokens
        
        # Add active context
        if self._active_task:
            parts.append(f"[Active Task: {self._active_task}]\n")
        
        # Add relevant variables (simplified)
        relevant_vars = {
            k: v for k, v in self.get_all_variables().items()
            if not k.startswith("_")
        }
        if relevant_vars:
            parts.append(f"[Context: {relevant_vars}]\n")
        
        return "".join(parts)
    
    def clear(self) -> None:
        """Clear all working memory."""
        self._conversation_history.clear()
        self._variables.clear()
        self._active_task = None
        self._user_context.clear()
        logger.info(f"Cleared working memory for session: {self._session_id}")
    
    def _trim_history(self) -> None:
        """Trim conversation history to max size."""
        # Keep system messages, trim others
        system_msgs = [t for t in self._conversation_history if t.role == "system"]
        other_msgs = [t for t in self._conversation_history if t.role != "system"]
        
        if len(other_msgs) > self._max_history:
            other_msgs = other_msgs[-self._max_history:]
        
        self._conversation_history = system_msgs + other_msgs
    
    def _update_activity(self) -> None:
        """Update last activity timestamp."""
        self._last_activity = datetime.utcnow().isoformat()


# Global working memory registry
_working_memories: Dict[str, WorkingMemory] = {}


def get_working_memory(session_id: str) -> WorkingMemory:
    """Get or create working memory for a session.
    
    Args:
        session_id: Session identifier
        
    Returns:
        WorkingMemory instance
    """
    if session_id not in _working_memories:
        _working_memories[session_id] = WorkingMemory(session_id)
    return _working_memories[session_id]


def clear_working_memory(session_id: str) -> bool:
    """Clear working memory for a session.
    
    Args:
        session_id: Session identifier
        
    Returns:
        True if cleared
    """
    if session_id in _working_memories:
        _working_memories[session_id].clear()
        del _working_memories[session_id]
        return True
    return False


def get_active_sessions() -> List[str]:
    """Get list of active session IDs.
    
    Returns:
        List of session IDs
    """
    return list(_working_memories.keys())
