"""Unit tests for specialist/self_healing_agent.py module.

This module tests the SelfHealingAgent class for error handling and automatic debugging.
"""

import json
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from uuid import UUID, uuid4

from src.specialist.self_healing_agent import (
    ErrorAnalysis,
    SelfHealingAgent
)
from src.engine.message import (
    ErrorPayload,
    ErrorSeverity,
    TaskPayload
)


class TestErrorAnalysis:
    """Test ErrorAnalysis dataclass."""
    
    def test_create_error_analysis(self):
        """Test creating an ErrorAnalysis object."""
        analysis = ErrorAnalysis(
            error_type="SyntaxError",
            root_cause="Missing colon",
            severity=ErrorSeverity.LOW,
            suggested_fix="Add colon at end of line",
            auto_repairable=True,
            confidence=0.95
        )
        
        assert analysis.error_type == "SyntaxError"
        assert analysis.root_cause == "Missing colon"
        assert analysis.severity == ErrorSeverity.LOW
        assert analysis.suggested_fix == "Add colon at end of line"
        assert analysis.auto_repairable is True
        assert analysis.confidence == 0.95


class TestSelfHealingAgentInitialization:
    """Test SelfHealingAgent initialization."""
    
    @patch("src.specialist.self_healing_agent.get_config")
    def test_init_default(self, mock_get_config):
        """Test SelfHealingAgent initialization with defaults."""
        mock_config = MagicMock()
        mock_get_config.return_value = mock_config
        
        agent = SelfHealingAgent()
        
        assert agent.name == "SelfHealingAgent"
        assert agent._bedrock_client is None
        assert agent._error_history == []
        assert agent._config == mock_config
    
    @patch("src.specialist.self_healing_agent.get_config")
    def test_init_with_context(self, mock_get_config):
        """Test SelfHealingAgent initialization with context."""
        mock_config = MagicMock()
        mock_get_config.return_value = mock_config
        
        from src.engine.message import AgentContext
        context = AgentContext(
            workspace_path="/tmp/test",
            session_id=uuid4(),
            user_id="test_user"
        )
        
        agent = SelfHealingAgent(context=context)
        
        assert agent.context == context
    
    @pytest.mark.asyncio
    @patch("src.specialist.self_healing_agent.get_config")
    @patch("src.specialist.self_healing_agent.get_bedrock_client")
    async def test_on_start_success(self, mock_get_bedrock, mock_get_config):
        """Test successful agent startup."""
        mock_config = MagicMock()
        mock_get_config.return_value = mock_config
        
        mock_bedrock = MagicMock()
        mock_get_bedrock.return_value = mock_bedrock
        
        agent = SelfHealingAgent()
        await agent.on_start()
        
        assert agent._bedrock_client == mock_bedrock
    
    @pytest.mark.asyncio
    @patch("src.specialist.self_healing_agent.get_config")
    @patch("src.specialist.self_healing_agent.get_bedrock_client")
    async def test_on_start_failure(self, mock_get_bedrock, mock_get_config):
        """Test agent startup failure."""
        mock_config = MagicMock()
        mock_get_config.return_value = mock_config
        
        mock_get_bedrock.side_effect = Exception("AWS connection failed")
        
        agent = SelfHealingAgent()
        
        with pytest.raises(Exception, match="AWS connection failed"):
            await agent.on_start()


class TestSelfHealingAgentTaskExecution:
    """Test SelfHealingAgent task execution."""
    
    @pytest.fixture
    def mock_agent(self):
        """Create a mock SelfHealingAgent for testing."""
        with patch("src.specialist.self_healing_agent.get_config") as mock_get_config:
            mock_config = MagicMock()
            mock_config.aws.model_nova_pro = "test-model"
            mock_get_config.return_value = mock_config
            
            agent = SelfHealingAgent()
            agent._bedrock_client = MagicMock()
            return agent
    
    @pytest.mark.asyncio
    async def test_execute_task_debug_error(self, mock_agent):
        """Test executing debug_error task."""
        task = TaskPayload(
            task_id=uuid4(),
            action="debug_error",
            params={
                "error_description": "SyntaxError: invalid syntax",
                "code": "def test()\n    pass",
                "stack_trace": "File test.py, line 1"
            }
        )
        
        mock_agent.debug_error = AsyncMock(return_value={
            "status": "analysis_complete",
            "analysis": {"error_type": "SyntaxError"}
        })
        
        result = await mock_agent.execute_task(task)
        
        mock_agent.debug_error.assert_called_once_with(
            "SyntaxError: invalid syntax",
            "def test()\n    pass",
            "File test.py, line 1"
        )
        assert result["status"] == "analysis_complete"
    
    @pytest.mark.asyncio
    async def test_execute_task_analyze_failure(self, mock_agent):
        """Test executing analyze_failure task."""
        task = TaskPayload(
            task_id=uuid4(),
            action="analyze_failure",
            params={
                "failure_data": {"type": "sandbox_failure", "context": {}}
            }
        )
        
        mock_agent.analyze_failure = AsyncMock(return_value={
            "status": "identified",
            "issue": "disk_full"
        })
        
        result = await mock_agent.execute_task(task)
        
        mock_agent.analyze_failure.assert_called_once()
        assert result["status"] == "identified"

    @pytest.mark.asyncio
    async def test_execute_task_analyze_error(self, mock_agent):
        """Test executing analyze_error task."""
        task = TaskPayload(
            task_id=uuid4(),
            action="analyze_error",
            params={
                "error_type": "RuntimeError",
                "error_message": "boom",
                "original_message": {"payload": "x"},
                "agent_name": "MainBrain",
            }
        )

        mock_agent.analyze_error_entry = AsyncMock(return_value={
            "status": "analyzed",
            "can_recover": True,
        })

        result = await mock_agent.execute_task(task)

        mock_agent.analyze_error_entry.assert_called_once_with(
            error_type="RuntimeError",
            error_message="boom",
            original_message={"payload": "x"},
            agent_name="MainBrain",
        )
        assert result["status"] == "analyzed"
    
    @pytest.mark.asyncio
    async def test_execute_task_attempt_repair(self, mock_agent):
        """Test executing attempt_repair task."""
        task = TaskPayload(
            task_id=uuid4(),
            action="attempt_repair",
            params={
                "code": "def broken(): pass",
                "fix_suggestion": "Add return statement"
            }
        )
        
        mock_agent.attempt_repair = AsyncMock(return_value={
            "success": True,
            "repaired_code": "def fixed(): return True"
        })
        
        result = await mock_agent.execute_task(task)
        
        mock_agent.attempt_repair.assert_called_once_with(
            "def broken(): pass",
            "Add return statement"
        )
    
    @pytest.mark.asyncio
    async def test_execute_task_fix_sandbox(self, mock_agent):
        """Test executing fix_sandbox task."""
        task = TaskPayload(
            task_id=uuid4(),
            action="fix_sandbox",
            params={"issue": "disk_full"}
        )
        
        mock_agent.fix_sandbox = AsyncMock(return_value={
            "status": "identified",
            "suggested_fix": "Clean up files"
        })
        
        result = await mock_agent.execute_task(task)
        
        mock_agent.fix_sandbox.assert_called_once_with("disk_full")
    
    @pytest.mark.asyncio
    async def test_execute_task_unknown_action(self, mock_agent):
        """Test executing unknown task action."""
        task = TaskPayload(
            task_id=uuid4(),
            action="unknown_action",
            params={}
        )
        
        result = await mock_agent.execute_task(task)
        
        assert result["status"] == "error"
        assert "Unknown action" in result["message"]


class TestSelfHealingAgentDebugError:
    """Test SelfHealingAgent error debugging."""
    
    @pytest.fixture
    def mock_agent(self):
        """Create a mock SelfHealingAgent for testing."""
        with patch("src.specialist.self_healing_agent.get_config") as mock_get_config:
            mock_config = MagicMock()
            mock_config.aws.model_nova_pro = "test-model"
            mock_get_config.return_value = mock_config
            
            agent = SelfHealingAgent()
            agent._bedrock_client = MagicMock()
            return agent
    
    @pytest.mark.asyncio
    async def test_debug_error_auto_repairable(self, mock_agent):
        """Test debugging an auto-repairable error."""
        mock_analysis = ErrorAnalysis(
            error_type="SyntaxError",
            root_cause="Missing colon",
            severity=ErrorSeverity.LOW,
            suggested_fix="Add colon",
            auto_repairable=True,
            confidence=0.95
        )
        
        mock_agent._analyze_error = AsyncMock(return_value=mock_analysis)
        mock_agent.attempt_repair = AsyncMock(return_value={
            "success": True,
            "message": "Code repaired"
        })
        
        result = await mock_agent.debug_error(
            error_description="SyntaxError",
            code="def test()\n    pass",
            stack_trace=""
        )
        
        assert result["status"] == "repaired"
        assert result["auto_repair_attempted"] is True
        mock_agent.attempt_repair.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_debug_error_not_auto_repairable(self, mock_agent):
        """Test debugging a non-auto-repairable error."""
        mock_analysis = ErrorAnalysis(
            error_type="LogicError",
            root_cause="Algorithm issue",
            severity=ErrorSeverity.HIGH,
            suggested_fix="Redesign algorithm",
            auto_repairable=False,
            confidence=0.7
        )
        
        mock_agent._analyze_error = AsyncMock(return_value=mock_analysis)
        
        result = await mock_agent.debug_error(
            error_description="LogicError",
            code="",
            stack_trace=""
        )
        
        assert result["status"] == "analysis_complete"
        assert result["auto_repairable"] is False
        assert result["requires_manual_fix"] is True
    
    @pytest.mark.asyncio
    async def test_debug_error_low_confidence(self, mock_agent):
        """Test debugging error with low confidence."""
        mock_analysis = ErrorAnalysis(
            error_type="UnknownError",
            root_cause="Unclear",
            severity=ErrorSeverity.MEDIUM,
            suggested_fix="Investigate further",
            auto_repairable=True,
            confidence=0.5  # Below threshold
        )
        
        mock_agent._analyze_error = AsyncMock(return_value=mock_analysis)
        
        result = await mock_agent.debug_error(
            error_description="Unknown",
            code="some code",
            stack_trace=""
        )
        
        assert result["status"] == "analysis_complete"
        assert "repair_result" not in result  # No repair attempted


class TestSelfHealingAgentAnalyzeError:
    """Test SelfHealingAgent error analysis."""
    
    @pytest.fixture
    def mock_agent(self):
        """Create a mock SelfHealingAgent for testing."""
        with patch("src.specialist.self_healing_agent.get_config") as mock_get_config:
            mock_config = MagicMock()
            mock_config.aws.model_nova_pro = "test-model"
            mock_get_config.return_value = mock_config
            
            agent = SelfHealingAgent()
            agent._bedrock_client = MagicMock()
            return agent
    
    @pytest.mark.asyncio
    async def test_analyze_error_success(self, mock_agent):
        """Test successful error analysis."""
        mock_agent._bedrock_client.converse.return_value = {
            'output': {
                'message': {
                    'content': [{
                        'text': json.dumps({
                            "error_type": "SyntaxError",
                            "root_cause": "Missing colon",
                            "severity": "low",
                            "suggested_fix": "Add colon",
                            "auto_repairable": True,
                            "confidence": 0.95
                        })
                    }]
                }
            }
        }
        
        analysis = await mock_agent._analyze_error(
            error_description="SyntaxError",
            code="def test()\n    pass",
            stack_trace="File test.py, line 1"
        )
        
        assert analysis.error_type == "SyntaxError"
        assert analysis.root_cause == "Missing colon"
        assert analysis.severity == ErrorSeverity.LOW
        assert analysis.auto_repairable is True
        assert analysis.confidence == 0.95
    
    @pytest.mark.asyncio
    async def test_analyze_error_with_markdown(self, mock_agent):
        """Test extracting analysis from markdown response."""
        mock_agent._bedrock_client.converse.return_value = {
            'output': {
                'message': {
                    'content': [{
                        'text': '''```json
{
    "error_type": "TypeError",
    "root_cause": "Type mismatch",
    "severity": "medium",
    "suggested_fix": "Check types",
    "auto_repairable": false,
    "confidence": 0.8
}
```'''
                    }]
                }
            }
        }
        
        analysis = await mock_agent._analyze_error(
            error_description="TypeError",
            code="",
            stack_trace=""
        )
        
        assert analysis.error_type == "TypeError"
        assert analysis.severity == ErrorSeverity.MEDIUM
    
    @pytest.mark.asyncio
    async def test_analyze_error_api_failure(self, mock_agent):
        """Test error analysis when API fails."""
        mock_agent._bedrock_client.converse.side_effect = Exception("API error")
        
        analysis = await mock_agent._analyze_error(
            error_description="Error",
            code="",
            stack_trace=""
        )
        
        assert analysis.error_type == "Unknown"
        assert analysis.auto_repairable is False
        assert analysis.confidence == 0.0


class TestSelfHealingAgentAttemptRepair:
    """Test SelfHealingAgent repair attempts."""
    
    @pytest.fixture
    def mock_agent(self):
        """Create a mock SelfHealingAgent for testing."""
        with patch("src.specialist.self_healing_agent.get_config") as mock_get_config:
            mock_config = MagicMock()
            mock_config.aws.model_nova_pro = "test-model"
            mock_get_config.return_value = mock_config
            
            agent = SelfHealingAgent()
            agent._bedrock_client = MagicMock()
            return agent
    
    @pytest.mark.asyncio
    async def test_attempt_repair_success(self, mock_agent):
        """Test successful code repair."""
        mock_agent._bedrock_client.converse.return_value = {
            'output': {
                'message': {
                    'content': [{'text': 'def fixed():\n    return True'}]
                }
            }
        }
        
        result = await mock_agent.attempt_repair(
            code="def broken():\n    pass",
            fix_suggestion="Add return True"
        )
        
        assert result["success"] is True
        assert result["changes_made"] is True
        assert "repaired_code" in result
    
    @pytest.mark.asyncio
    async def test_attempt_repair_no_change(self, mock_agent):
        """Test repair when code doesn't change."""
        original_code = "def same():\n    pass"
        
        mock_agent._bedrock_client.converse.return_value = {
            'output': {
                'message': {
                    'content': [{'text': original_code}]
                }
            }
        }
        
        result = await mock_agent.attempt_repair(
            code=original_code,
            fix_suggestion="Do nothing"
        )
        
        assert result["success"] is False
        assert "Code unchanged" in result["message"]
    
    @pytest.mark.asyncio
    async def test_attempt_repair_api_failure(self, mock_agent):
        """Test repair when API fails."""
        mock_agent._bedrock_client.converse.side_effect = Exception("API error")
        
        result = await mock_agent.attempt_repair(
            code="def broken(): pass",
            fix_suggestion="Fix it"
        )
        
        assert result["success"] is False
        assert "Repair failed" in result["message"]


class TestSelfHealingAgentAnalyzeFailure:
    """Test SelfHealingAgent failure analysis."""
    
    @pytest.fixture
    def mock_agent(self):
        """Create a mock SelfHealingAgent for testing."""
        with patch("src.specialist.self_healing_agent.get_config") as mock_get_config:
            mock_config = MagicMock()
            mock_get_config.return_value = mock_config
            
            agent = SelfHealingAgent()
            agent._bedrock_client = MagicMock()
            return agent
    
    @pytest.mark.asyncio
    async def test_analyze_sandbox_failure(self, mock_agent):
        """Test analyzing sandbox failure."""
        mock_agent.fix_sandbox = AsyncMock(return_value={
            "status": "identified",
            "suggested_fix": "Clean up files"
        })
        
        result = await mock_agent.analyze_failure({
            "type": "sandbox_failure",
            "context": {"issue": "disk_full"}
        })
        
        assert result["status"] == "identified"
        mock_agent.fix_sandbox.assert_called_once_with("disk_full")
    
    @pytest.mark.asyncio
    async def test_analyze_task_failure(self, mock_agent):
        """Test analyzing task failure."""
        mock_agent._analyze_error = AsyncMock(return_value=ErrorAnalysis(
            error_type="RuntimeError",
            root_cause="Repeated tool failure",
            severity=ErrorSeverity.MEDIUM,
            suggested_fix="Use fallback",
            auto_repairable=False,
            confidence=0.7,
        ))
        
        result = await mock_agent.analyze_failure({
            "type": "task_failure",
            "context": {
                "error": "Error message",
                "code": "def test(): pass",
                "stack_trace": "Traceback..."
            }
        })
        
        mock_agent._analyze_error.assert_called_once_with(
            "Error message",
            "def test(): pass",
            "Traceback..."
        )
        assert result["status"] == "analyzed"
        assert result["can_recover"] is True
    
    @pytest.mark.asyncio
    async def test_analyze_connection_failure(self, mock_agent):
        """Test analyzing connection failure."""
        mock_agent._handle_connection_failure = AsyncMock(return_value={
            "status": "retry_suggested"
        })
        
        result = await mock_agent.analyze_failure({
            "type": "connection_failure",
            "context": {"service": "AWS"}
        })
        
        mock_agent._handle_connection_failure.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_analyze_unknown_failure(self, mock_agent):
        """Test analyzing unknown failure type."""
        result = await mock_agent.analyze_failure({
            "type": "unknown_type",
            "context": {}
        })
        
        assert result["status"] == "unknown_failure_type"


class TestSelfHealingAgentFixSandbox:
    """Test SelfHealingAgent sandbox fixing."""
    
    @pytest.fixture
    def mock_agent(self):
        """Create a mock SelfHealingAgent for testing."""
        with patch("src.specialist.self_healing_agent.get_config") as mock_get_config:
            mock_config = MagicMock()
            mock_config.aws.model_nova_lite = "test-lite-model"
            mock_get_config.return_value = mock_config
            
            agent = SelfHealingAgent()
            agent._bedrock_client = MagicMock()
            return agent
    
    @pytest.mark.asyncio
    async def test_fix_sandbox_disk_full(self, mock_agent):
        """Test fixing disk full issue."""
        result = await mock_agent.fix_sandbox("disk_full")
        
        assert result["status"] == "identified"
        assert "disk_full" in result["issue"]
        assert "Clean up" in result["suggested_fix"]
        assert result["auto_fixable"] is False
    
    @pytest.mark.asyncio
    async def test_fix_sandbox_memory_exceeded(self, mock_agent):
        """Test fixing memory exceeded issue."""
        result = await mock_agent.fix_sandbox("memory_exceeded")
        
        assert result["status"] == "identified"
        assert "Restart sandbox" in result["suggested_fix"]
    
    @pytest.mark.asyncio
    async def test_fix_sandbox_container_crashed(self, mock_agent):
        """Test fixing container crashed issue."""
        result = await mock_agent.fix_sandbox("container_crashed")
        
        assert result["status"] == "identified"
        assert "Restart container" in result["suggested_fix"]
    
    @pytest.mark.asyncio
    async def test_fix_sandbox_unknown_issue(self, mock_agent):
        """Test fixing unknown sandbox issue."""
        mock_agent._bedrock_client.converse.return_value = {
            'output': {
                'message': {
                    'content': [{'text': 'Check container logs'}]
                }
            }
        }
        
        result = await mock_agent.fix_sandbox("some_random_issue")
        
        assert result["status"] == "analyzed"
        assert result["suggested_fix"] == "Check container logs"
    
    @pytest.mark.asyncio
    async def test_fix_sandbox_api_failure(self, mock_agent):
        """Test fixing sandbox when API fails."""
        mock_agent._bedrock_client.converse.side_effect = Exception("API error")
        
        result = await mock_agent.fix_sandbox("unknown_issue")
        
        assert result["status"] == "analysis_failed"


class TestSelfHealingAgentErrorHistory:
    """Test SelfHealingAgent error history tracking."""
    
    @pytest.fixture
    def mock_agent(self):
        """Create a mock SelfHealingAgent for testing."""
        with patch("src.specialist.self_healing_agent.get_config") as mock_get_config:
            mock_config = MagicMock()
            mock_config.aws.model_nova_pro = "test-model"
            mock_get_config.return_value = mock_config
            
            agent = SelfHealingAgent()
            agent._bedrock_client = MagicMock()
            agent._analyze_error = AsyncMock(return_value=ErrorAnalysis(
                error_type="TestError",
                root_cause="Test",
                severity=ErrorSeverity.LOW,
                suggested_fix="Fix",
                auto_repairable=False,
                confidence=0.5
            ))
            return agent
    
    @pytest.mark.asyncio
    async def test_error_added_to_history(self, mock_agent):
        """Test that errors are added to history after debugging."""
        assert len(mock_agent._error_history) == 0
        
        await mock_agent.debug_error("Error", "code", "trace")
        
        assert len(mock_agent._error_history) == 1
        assert mock_agent._error_history[0]["error"] == "Error"
