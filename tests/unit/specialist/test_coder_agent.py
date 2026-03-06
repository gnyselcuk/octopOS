"""Unit tests for specialist/coder_agent.py module.

This module tests the CoderAgent class for code generation and primitive creation.
"""

import json
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from uuid import UUID, uuid4

from src.specialist.coder_agent import CoderAgent
from src.engine.message import TaskPayload, TaskStatus


class TestCoderAgentInitialization:
    """Test CoderAgent initialization."""
    
    @patch("src.specialist.coder_agent.get_config")
    def test_init_default(self, mock_get_config):
        """Test CoderAgent initialization with defaults."""
        mock_config = MagicMock()
        mock_get_config.return_value = mock_config
        
        agent = CoderAgent()
        
        assert agent.name == "CoderAgent"
        assert agent._bedrock_client is None
        assert agent._pending_reviews == {}
        assert agent._config == mock_config
    
    @patch("src.specialist.coder_agent.get_config")
    def test_init_with_context(self, mock_get_config):
        """Test CoderAgent initialization with context."""
        mock_config = MagicMock()
        mock_get_config.return_value = mock_config
        
        from src.engine.message import AgentContext
        context = AgentContext(
            workspace_path="/tmp/test",
            session_id=uuid4(),
            user_id="test_user"
        )
        
        agent = CoderAgent(context=context)
        
        assert agent.context == context
    
    @pytest.mark.asyncio
    @patch("src.specialist.coder_agent.get_config")
    @patch("src.specialist.coder_agent.get_bedrock_client")
    async def test_on_start_success(self, mock_get_bedrock, mock_get_config):
        """Test successful agent startup."""
        mock_config = MagicMock()
        mock_get_config.return_value = mock_config
        
        mock_bedrock = MagicMock()
        mock_get_bedrock.return_value = mock_bedrock
        
        agent = CoderAgent()
        await agent.on_start()
        
        assert agent._bedrock_client == mock_bedrock
        mock_get_bedrock.assert_called_once()
    
    @pytest.mark.asyncio
    @patch("src.specialist.coder_agent.get_config")
    @patch("src.specialist.coder_agent.get_bedrock_client")
    async def test_on_start_failure(self, mock_get_bedrock, mock_get_config):
        """Test agent startup failure."""
        mock_config = MagicMock()
        mock_get_config.return_value = mock_config
        
        mock_get_bedrock.side_effect = Exception("AWS connection failed")
        
        agent = CoderAgent()
        
        with pytest.raises(Exception, match="AWS connection failed"):
            await agent.on_start()


class TestCoderAgentTaskExecution:
    """Test CoderAgent task execution."""
    
    @pytest.fixture
    def mock_agent(self):
        """Create a mock CoderAgent for testing."""
        with patch("src.specialist.coder_agent.get_config") as mock_get_config:
            mock_config = MagicMock()
            mock_config.aws.model_nova_pro = "test-model"
            mock_get_config.return_value = mock_config
            
            agent = CoderAgent()
            agent._bedrock_client = MagicMock()
            return agent
    
    @pytest.mark.asyncio
    async def test_execute_task_create_primitive(self, mock_agent):
        """Test executing create_primitive task."""
        task = TaskPayload(
            task_id=uuid4(),
            action="create_primitive",
            params={
                "description": "Create a tool that calculates fibonacci numbers",
                "name": "fibonacci_calculator",
                "language": "python"
            }
        )
        
        # Mock the create_primitive method
        mock_agent.create_primitive = AsyncMock(return_value={
            "status": "pending_review",
            "name": "fibonacci_calculator"
        })
        
        result = await mock_agent.execute_task(task)
        
        mock_agent.create_primitive.assert_called_once_with(
            "Create a tool that calculates fibonacci numbers",
            "fibonacci_calculator",
            "python"
        )
        assert result["status"] == "pending_review"
    
    @pytest.mark.asyncio
    async def test_execute_task_modify_primitive(self, mock_agent):
        """Test executing modify_primitive task."""
        task = TaskPayload(
            task_id=uuid4(),
            action="modify_primitive",
            params={
                "name": "fibonacci_calculator",
                "changes": "Add memoization",
                "current_code": "def fib(n): pass"
            }
        )
        
        mock_agent.modify_primitive = AsyncMock(return_value={
            "status": "pending_review"
        })
        
        result = await mock_agent.execute_task(task)
        
        mock_agent.modify_primitive.assert_called_once_with(
            "fibonacci_calculator",
            "def fib(n): pass",
            "Add memoization"
        )
    
    @pytest.mark.asyncio
    async def test_execute_task_fix_code(self, mock_agent):
        """Test executing fix_code task."""
        task = TaskPayload(
            task_id=uuid4(),
            action="fix_code",
            params={
                "code": "def broken(): pass",
                "error": "SyntaxError"
            }
        )
        
        mock_agent.fix_code = AsyncMock(return_value={
            "status": "success",
            "fixed_code": "def fixed(): pass"
        })
        
        result = await mock_agent.execute_task(task)
        
        mock_agent.fix_code.assert_called_once_with(
            "def broken(): pass",
            "SyntaxError"
        )
    
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


class TestCoderAgentCreatePrimitive:
    """Test CoderAgent primitive creation."""
    
    @pytest.fixture
    def mock_agent(self):
        """Create a mock CoderAgent for testing."""
        with patch("src.specialist.coder_agent.get_config") as mock_get_config:
            mock_config = MagicMock()
            mock_config.aws.model_nova_pro = "test-model"
            mock_get_config.return_value = mock_config
            
            agent = CoderAgent()
            agent._bedrock_client = MagicMock()
            agent.request_approval = MagicMock()
            return agent
    
    @pytest.mark.asyncio
    async def test_create_primitive_success(self, mock_agent):
        """Test successful primitive creation."""
        # Mock _generate_code
        mock_agent._generate_code = AsyncMock(return_value="""
def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)
""")
        
        # Mock _generate_documentation
        mock_agent._generate_documentation = AsyncMock(return_value={
            "summary": "Fibonacci calculator",
            "description": "Calculates fibonacci numbers"
        })
        
        result = await mock_agent.create_primitive(
            description="Create a fibonacci calculator",
            name="fibonacci_calculator",
            language="python"
        )
        
        assert result["status"] == "pending_review"
        assert result["name"] == "fibonacci_calculator"
        assert "approval_id" in result
        mock_agent.request_approval.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_create_primitive_no_name_provided(self, mock_agent):
        """Test primitive creation without provided name."""
        mock_agent._generate_code = AsyncMock(return_value="def test(): pass")
        mock_agent._generate_documentation = AsyncMock(return_value={
            "summary": "Test function"
        })
        mock_agent._extract_name_from_description = MagicMock(return_value="extracted_name")
        
        result = await mock_agent.create_primitive(
            description="Create a test function"
        )
        
        mock_agent._extract_name_from_description.assert_called_once_with("Create a test function")
        assert result["name"] == "extracted_name"
    
    @pytest.mark.asyncio
    async def test_create_primitive_generation_failure(self, mock_agent):
        """Test primitive creation when code generation fails."""
        mock_agent._generate_code = AsyncMock(return_value="")
        
        result = await mock_agent.create_primitive(
            description="Create something impossible"
        )
        
        assert result["status"] == "error"
        assert "Failed to generate code" in result["message"]


class TestCoderAgentGenerateCode:
    """Test CoderAgent code generation."""
    
    @pytest.fixture
    def mock_agent(self):
        """Create a mock CoderAgent for testing."""
        with patch("src.specialist.coder_agent.get_config") as mock_get_config:
            mock_config = MagicMock()
            mock_config.aws.model_nova_pro = "test-model"
            mock_get_config.return_value = mock_config
            
            agent = CoderAgent()
            agent._bedrock_client = MagicMock()
            return agent
    
    @pytest.mark.asyncio
    async def test_generate_code_success(self, mock_agent):
        """Test successful code generation."""
        mock_agent._bedrock_client.converse.return_value = {
            'output': {
                'message': {
                    'content': [{'text': 'def hello():\n    return "world"'}]
                }
            }
        }
        
        code = await mock_agent._generate_code(
            description="Create a hello function",
            name="hello_function",
            language="python"
        )
        
        assert "def hello():" in code
        mock_agent._bedrock_client.converse.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_generate_code_with_markdown(self, mock_agent):
        """Test extracting code from markdown response."""
        mock_agent._bedrock_client.converse.return_value = {
            'output': {
                'message': {
                    'content': [{'text': '```python\ndef test():\n    pass\n```'}]
                }
            }
        }
        
        code = await mock_agent._generate_code(
            description="Create a test function",
            name=None,
            language="python"
        )
        
        assert code.strip() == "def test():\n    pass"
    
    @pytest.mark.asyncio
    async def test_generate_code_failure(self, mock_agent):
        """Test code generation failure."""
        mock_agent._bedrock_client.converse.side_effect = Exception("Bedrock error")
        
        code = await mock_agent._generate_code(
            description="Create something",
            name=None,
            language="python"
        )
        
        assert code == ""


class TestCoderAgentDocumentation:
    """Test CoderAgent documentation generation."""
    
    @pytest.fixture
    def mock_agent(self):
        """Create a mock CoderAgent for testing."""
        with patch("src.specialist.coder_agent.get_config") as mock_get_config:
            mock_config = MagicMock()
            mock_config.aws.model_nova_lite = "test-lite-model"
            mock_get_config.return_value = mock_config
            
            agent = CoderAgent()
            agent._bedrock_client = MagicMock()
            return agent
    
    @pytest.mark.asyncio
    async def test_generate_documentation_success(self, mock_agent):
        """Test successful documentation generation."""
        mock_agent._bedrock_client.converse.return_value = {
            'output': {
                'message': {
                    'content': [{
                        'text': json.dumps({
                            "summary": "A test function",
                            "description": "Does testing",
                            "parameters": "None",
                            "returns": "None",
                            "examples": "test()"
                        })
                    }]
                }
            }
        }
        
        docs = await mock_agent._generate_documentation(
            code="def test(): pass",
            description="A test function"
        )
        
        assert docs["summary"] == "A test function"
        assert docs["description"] == "Does testing"
    
    @pytest.mark.asyncio
    async def test_generate_documentation_failure(self, mock_agent):
        """Test documentation generation failure."""
        mock_agent._bedrock_client.converse.side_effect = Exception("API error")
        
        docs = await mock_agent._generate_documentation(
            code="def test(): pass",
            description="Test"
        )
        
        assert docs["summary"] == "Auto-generated primitive"
        assert docs["description"] == "Test"


class TestCoderAgentNameExtraction:
    """Test CoderAgent name extraction."""
    
    @pytest.fixture
    def mock_agent(self):
        """Create a mock CoderAgent for testing."""
        with patch("src.specialist.coder_agent.get_config") as mock_get_config:
            mock_config = MagicMock()
            mock_get_config.return_value = mock_config
            return CoderAgent()
    
    def test_extract_name_simple(self, mock_agent):
        """Test extracting name from simple description."""
        name = mock_agent._extract_name_from_description(
            "Create a fibonacci calculator"
        )
        
        assert "fibonacci" in name
        assert "calculator" in name
    
    def test_extract_name_removes_common_words(self, mock_agent):
        """Test that common words are removed from name."""
        name = mock_agent._extract_name_from_description(
            "Create a tool to calculate the sum"
        )
        
        assert "create" not in name
        assert "a" not in name
        assert "to" not in name
    
    def test_extract_name_limits_length(self, mock_agent):
        """Test that extracted name is limited in length."""
        name = mock_agent._extract_name_from_description(
            "Create a very long description with many words to test"
        )
        
        assert len(name) <= 50
    
    def test_extract_name_handles_special_chars(self, mock_agent):
        """Test handling special characters in description."""
        name = mock_agent._extract_name_from_description(
            "Create @ tool # with $ special % chars"
        )
        
        assert "@" not in name
        assert "#" not in name
        assert "$" not in name


class TestCoderAgentModifyPrimitive:
    """Test CoderAgent primitive modification."""
    
    @pytest.fixture
    def mock_agent(self):
        """Create a mock CoderAgent for testing."""
        with patch("src.specialist.coder_agent.get_config") as mock_get_config:
            mock_config = MagicMock()
            mock_config.aws.model_nova_pro = "test-model"
            mock_get_config.return_value = mock_config
            
            agent = CoderAgent()
            agent._bedrock_client = MagicMock()
            agent.request_approval = MagicMock()
            return agent
    
    @pytest.mark.asyncio
    async def test_modify_primitive_success(self, mock_agent):
        """Test successful primitive modification."""
        mock_agent._bedrock_client.converse.return_value = {
            'output': {
                'message': {
                    'content': [{'text': 'def modified():\n    pass'}]
                }
            }
        }
        
        result = await mock_agent.modify_primitive(
            name="test_primitive",
            current_code="def test(): pass",
            changes="Add docstring"
        )
        
        assert result["status"] == "pending_review"
        assert "approval_id" in result
    
    @pytest.mark.asyncio
    async def test_modify_primitive_failure(self, mock_agent):
        """Test primitive modification failure."""
        mock_agent._bedrock_client.converse.side_effect = Exception("Bedrock error")
        
        result = await mock_agent.modify_primitive(
            name="test",
            current_code="def test(): pass",
            changes="Fix it"
        )
        
        assert result["status"] == "error"


class TestCoderAgentFixCode:
    """Test CoderAgent code fixing."""
    
    @pytest.fixture
    def mock_agent(self):
        """Create a mock CoderAgent for testing."""
        with patch("src.specialist.coder_agent.get_config") as mock_get_config:
            mock_config = MagicMock()
            mock_config.aws.model_nova_pro = "test-model"
            mock_get_config.return_value = mock_config
            
            agent = CoderAgent()
            agent._bedrock_client = MagicMock()
            return agent
    
    @pytest.mark.asyncio
    async def test_fix_code_success(self, mock_agent):
        """Test successful code fixing."""
        mock_agent._bedrock_client.converse.return_value = {
            'output': {
                'message': {
                    'content': [{'text': 'def fixed():\n    return True'}]
                }
            }
        }
        
        result = await mock_agent.fix_code(
            code="def broken():\n    return Fals",
            error="SyntaxError: invalid syntax"
        )
        
        assert result["status"] == "success"
        assert "fixed_code" in result
    
    @pytest.mark.asyncio
    async def test_fix_code_with_markdown(self, mock_agent):
        """Test extracting fixed code from markdown."""
        mock_agent._bedrock_client.converse.return_value = {
            'output': {
                'message': {
                    'content': [{'text': '```python\ndef fixed(): pass\n```'}]
                }
            }
        }
        
        result = await mock_agent.fix_code(
            code="def broken(): pass",
            error="Error"
        )
        
        assert result["fixed_code"] == "def fixed(): pass"
    
    @pytest.mark.asyncio
    async def test_fix_code_failure(self, mock_agent):
        """Test code fixing failure."""
        mock_agent._bedrock_client.converse.side_effect = Exception("API error")
        
        result = await mock_agent.fix_code(
            code="def broken(): pass",
            error="SyntaxError"
        )
        
        assert result["status"] == "error"
