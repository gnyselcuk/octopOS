"""Unit tests for engine/memory/working_memory.py module.

This module tests the WorkingMemory class for short-term session context.
"""

import pytest
from datetime import datetime

from src.engine.memory.working_memory import (
    ConversationTurn,
    ContextSnapshot,
    SessionVariable,
    WorkingMemory,
)


class TestConversationTurn:
    """Test ConversationTurn dataclass."""
    
    def test_create_conversation_turn(self):
        """Test creating a conversation turn."""
        turn = ConversationTurn(
            role="user",
            content="Hello",
            timestamp="2024-01-01T00:00:00",
            metadata={"key": "value"},
            intent_type="greeting",
            actions_taken=[]
        )
        
        assert turn.role == "user"
        assert turn.content == "Hello"
        assert turn.timestamp == "2024-01-01T00:00:00"
        assert turn.metadata == {"key": "value"}
        assert turn.intent_type == "greeting"
        assert turn.actions_taken == []
    
    def test_conversation_turn_defaults(self):
        """Test ConversationTurn default values."""
        turn = ConversationTurn(
            role="assistant",
            content="Hi",
            timestamp="2024-01-01T00:00:00"
        )
        
        assert turn.metadata == {}
        assert turn.intent_type is None
        assert turn.actions_taken == []


class TestSessionVariable:
    """Test SessionVariable dataclass."""
    
    def test_create_session_variable(self):
        """Test creating a session variable."""
        var = SessionVariable(
            name="test_var",
            value="test_value",
            scope="session",
            timestamp="2024-01-01T00:00:00",
            ttl=3600
        )
        
        assert var.name == "test_var"
        assert var.value == "test_value"
        assert var.scope == "session"
        assert var.timestamp == "2024-01-01T00:00:00"
        assert var.ttl == 3600
    
    def test_session_variable_defaults(self):
        """Test SessionVariable default values."""
        var = SessionVariable(
            name="test",
            value=123,
            scope="global",
            timestamp="2024-01-01T00:00:00"
        )
        
        assert var.ttl is None


class TestContextSnapshot:
    """Test ContextSnapshot dataclass."""
    
    def test_create_context_snapshot(self):
        """Test creating a context snapshot."""
        snapshot = ContextSnapshot(
            session_id="session_123",
            timestamp="2024-01-01T00:00:00",
            conversation_history=[],
            variables={},
            active_task="task_1",
            user_preferences={"theme": "dark"}
        )
        
        assert snapshot.session_id == "session_123"
        assert snapshot.active_task == "task_1"
        assert snapshot.user_preferences == {"theme": "dark"}


class TestWorkingMemoryInitialization:
    """Test WorkingMemory initialization."""
    
    def test_working_memory_init_defaults(self):
        """Test WorkingMemory initialization with defaults."""
        memory = WorkingMemory(session_id="session_123")
        
        assert memory.session_id == "session_123"
        assert memory._max_history == 50
        assert memory._max_context_tokens == 4000
        assert memory._conversation_history == []
        assert memory._variables == {}
        assert memory._active_task is None
    
    def test_working_memory_init_custom(self):
        """Test WorkingMemory initialization with custom values."""
        memory = WorkingMemory(
            session_id="session_456",
            max_history=100,
            max_context_tokens=8000
        )
        
        assert memory.session_id == "session_456"
        assert memory._max_history == 100
        assert memory._max_context_tokens == 8000
    
    def test_session_id_property(self):
        """Test session_id property."""
        memory = WorkingMemory(session_id="test_session")
        assert memory.session_id == "test_session"
    
    def test_created_at_property(self):
        """Test created_at property."""
        memory = WorkingMemory(session_id="test")
        assert memory.created_at is not None
        assert isinstance(memory.created_at, str)


class TestWorkingMemoryConversation:
    """Test WorkingMemory conversation management."""
    
    @pytest.fixture
    def memory(self):
        """Create a WorkingMemory instance for testing."""
        return WorkingMemory(session_id="test_session")
    
    def test_add_user_message(self, memory):
        """Test adding user message."""
        memory.add_user_message("Hello", metadata={"intent": "greeting"})
        
        history = memory.get_conversation_history()
        assert len(history) == 1
        assert history[0].role == "user"
        assert history[0].content == "Hello"
        assert history[0].metadata == {"intent": "greeting"}
    
    def test_add_assistant_message(self, memory):
        """Test adding assistant message."""
        memory.add_assistant_message("Hi there!", actions_taken=["greet"])
        
        history = memory.get_conversation_history()
        assert len(history) == 1
        assert history[0].role == "assistant"
        assert history[0].content == "Hi there!"
        assert history[0].actions_taken == ["greet"]
    
    def test_add_system_message(self, memory):
        """Test adding system message."""
        memory.add_user_message("Hello")
        memory.add_system_message("System initialized")
        
        history = memory.get_conversation_history()
        # System message inserted at beginning
        assert history[0].role == "system"
        assert history[0].content == "System initialized"
    
    def test_get_conversation_history_last_n(self, memory):
        """Test getting last N conversation turns."""
        for i in range(10):
            memory.add_user_message(f"Message {i}")
            memory.add_assistant_message(f"Response {i}")
        
        history = memory.get_conversation_history(last_n=5)
        assert len(history) == 5
        assert history[-1].content == "Response 9"
    
    def test_get_conversation_history_exclude_system(self, memory):
        """Test getting history excluding system messages."""
        memory.add_system_message("System message")
        memory.add_user_message("User message")
        memory.add_assistant_message("Assistant message")
        
        history = memory.get_conversation_history(include_system=False)
        assert len(history) == 2
        assert all(t.role != "system" for t in history)
    
    def test_get_last_n_messages(self, memory):
        """Test getting last N messages as dicts."""
        memory.add_user_message("Hello")
        memory.add_assistant_message("Hi")
        memory.add_system_message("System")
        memory.add_user_message("How are you?")
        
        messages = memory.get_last_n_messages(2)
        assert len(messages) == 2
        assert messages[0]["role"] == "assistant"
        assert messages[0]["content"] == "Hi"
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "How are you?"
    
    def test_conversation_history_trim(self, memory):
        """Test that conversation history is trimmed."""
        # Add more messages than max_history
        for i in range(60):
            memory.add_user_message(f"Message {i}")
        
        history = memory.get_conversation_history()
        # Should be trimmed to max_history
        assert len(history) <= memory._max_history


class TestWorkingMemoryVariables:
    """Test WorkingMemory variable management."""
    
    @pytest.fixture
    def memory(self):
        """Create a WorkingMemory instance for testing."""
        return WorkingMemory(session_id="test_session")
    
    def test_set_variable(self, memory):
        """Test setting a session variable."""
        memory.set_variable("test_var", "test_value")
        
        assert "test_var" in memory._variables
        assert memory._variables["test_var"].value == "test_value"
        assert memory._variables["test_var"].scope == "session"
    
    def test_set_variable_with_scope(self, memory):
        """Test setting variable with scope."""
        memory.set_variable("global_var", 123, scope="global")
        
        assert memory._variables["global_var"].scope == "global"
    
    def test_get_variable(self, memory):
        """Test getting a session variable."""
        memory.set_variable("test_var", "test_value")
        
        value = memory.get_variable("test_var")
        assert value == "test_value"
    
    def test_get_variable_default(self, memory):
        """Test getting variable with default."""
        value = memory.get_variable("nonexistent", default="default_value")
        assert value == "default_value"
    
    def test_get_variable_with_ttl(self, memory):
        """Test variable with TTL."""
        # Set variable with very short TTL
        memory.set_variable("temp_var", "temp_value", ttl=-1)
        
        # Should be expired and return default
        value = memory.get_variable("temp_var", default="expired")
        assert value == "expired"
    
    def test_has_variable(self, memory):
        """Test checking if variable exists."""
        memory.set_variable("exists", "value")
        
        assert memory.has_variable("exists") is True
        assert memory.has_variable("not_exists") is False
    
    def test_delete_variable(self, memory):
        """Test deleting a variable."""
        memory.set_variable("to_delete", "value")
        
        result = memory.delete_variable("to_delete")
        assert result is True
        assert "to_delete" not in memory._variables
    
    def test_delete_variable_nonexistent(self, memory):
        """Test deleting non-existent variable."""
        result = memory.delete_variable("nonexistent")
        assert result is False
    
    def test_get_all_variables(self, memory):
        """Test getting all variables."""
        memory.set_variable("var1", "value1", scope="session")
        memory.set_variable("var2", "value2", scope="task")
        memory.set_variable("var3", "value3", scope="global")
        
        all_vars = memory.get_all_variables()
        assert len(all_vars) == 3
        assert all_vars["var1"] == "value1"
    
    def test_get_all_variables_filtered(self, memory):
        """Test getting variables filtered by scope."""
        memory.set_variable("var1", "value1", scope="session")
        memory.set_variable("var2", "value2", scope="task")
        memory.set_variable("var3", "value3", scope="session")
        
        session_vars = memory.get_all_variables(scope="session")
        assert len(session_vars) == 2
        assert "var1" in session_vars
        assert "var3" in session_vars


class TestWorkingMemoryTaskManagement:
    """Test WorkingMemory task management."""
    
    @pytest.fixture
    def memory(self):
        """Create a WorkingMemory instance for testing."""
        return WorkingMemory(session_id="test_session")
    
    def test_set_active_task(self, memory):
        """Test setting active task."""
        memory.set_active_task("task_123")
        
        assert memory._active_task == "task_123"
    
    def test_get_active_task(self, memory):
        """Test getting active task."""
        memory.set_active_task("task_456")
        
        task = memory.get_active_task()
        assert task == "task_456"
    
    def test_get_active_task_none(self, memory):
        """Test getting active task when none set."""
        task = memory.get_active_task()
        assert task is None
    
    def test_clear_active_task(self, memory):
        """Test clearing active task."""
        memory.set_active_task("task_789")
        memory.clear_active_task()
        
        assert memory._active_task is None


class TestWorkingMemoryUserContext:
    """Test WorkingMemory user context management."""
    
    @pytest.fixture
    def memory(self):
        """Create a WorkingMemory instance for testing."""
        return WorkingMemory(session_id="test_session")
    
    def test_set_user_context(self, memory):
        """Test setting user context."""
        memory.set_user_context("preference", "dark_mode")
        
        assert memory._user_context["preference"] == "dark_mode"
    
    def test_get_user_context(self, memory):
        """Test getting user context."""
        memory.set_user_context("language", "en")
        
        value = memory.get_user_context("language")
        assert value == "en"
    
    def test_get_user_context_default(self, memory):
        """Test getting user context with default."""
        value = memory.get_user_context("nonexistent", default="default")
        assert value == "default"


class TestWorkingMemorySnapshot:
    """Test WorkingMemory context snapshot."""
    
    @pytest.fixture
    def memory(self):
        """Create a WorkingMemory instance for testing."""
        return WorkingMemory(session_id="test_session")
    
    def test_get_context_snapshot(self, memory):
        """Test getting context snapshot."""
        memory.add_user_message("Hello")
        memory.set_variable("test_var", "test_value")
        memory.set_active_task("task_1")
        memory.set_user_context("theme", "dark")
        
        snapshot = memory.get_context_snapshot()
        
        assert isinstance(snapshot, ContextSnapshot)
        assert snapshot.session_id == "test_session"
        assert len(snapshot.conversation_history) == 1
        assert snapshot.variables["test_var"] == "test_value"
        assert snapshot.active_task == "task_1"
        assert snapshot.user_preferences["theme"] == "dark"
