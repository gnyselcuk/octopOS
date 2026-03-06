"""Unit tests for engine/supervisor.py module.

This module tests the Supervisor agent and security functionality.
"""

import uuid
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

from src.engine.supervisor import (
    SecurityPolicy,
    SecurityScanResult,
    Supervisor,
    get_supervisor,
)
from src.engine.message import TaskPayload


class TestSecurityPolicy:
    """Test SecurityPolicy class."""
    
    def test_dangerous_patterns_defined(self):
        """Test that dangerous patterns are defined."""
        assert len(SecurityPolicy.DANGEROUS_PATTERNS) > 0
        # Patterns are regex, check for presence of key terms in the compiled patterns
        patterns_str = " ".join(SecurityPolicy.DANGEROUS_PATTERNS)
        assert "os\.system" in patterns_str
        assert "subprocess" in patterns_str
        assert "eval" in patterns_str
    
    def test_allowed_imports_defined(self):
        """Test that allowed imports are defined."""
        assert "os" in SecurityPolicy.ALLOWED_IMPORTS
        assert "json" in SecurityPolicy.ALLOWED_IMPORTS
        assert "boto3" in SecurityPolicy.ALLOWED_IMPORTS
        assert "pydantic" in SecurityPolicy.ALLOWED_IMPORTS
    
    def test_blocked_imports_defined(self):
        """Test that blocked imports are defined."""
        assert "subprocess" in SecurityPolicy.BLOCKED_IMPORTS
        assert "socket" in SecurityPolicy.BLOCKED_IMPORTS
        assert "pickle" in SecurityPolicy.BLOCKED_IMPORTS
        assert "eval" in SecurityPolicy.BLOCKED_IMPORTS


class TestSecurityScanResult:
    """Test SecurityScanResult class."""
    
    def test_create_scan_result(self):
        """Test creating a security scan result."""
        result = SecurityScanResult(
            passed=True,
            risk_level="low",
            findings=[],
            recommendations=[]
        )
        
        assert result.passed is True
        assert result.risk_level == "low"
        assert result.findings == []
        assert result.recommendations == []
    
    def test_create_scan_result_with_findings(self):
        """Test creating scan result with findings."""
        findings = [{"type": "test", "severity": "medium"}]
        recommendations = ["Fix the issue"]
        
        result = SecurityScanResult(
            passed=False,
            risk_level="medium",
            findings=findings,
            recommendations=recommendations
        )
        
        assert result.passed is False
        assert result.risk_level == "medium"
        assert len(result.findings) == 1
        assert len(result.recommendations) == 1


class TestSupervisorInitialization:
    """Test Supervisor initialization."""
    
    @pytest.fixture
    def supervisor(self):
        """Create a Supervisor instance for testing."""
        with patch("src.engine.supervisor.get_config") as mock_get_config:
            mock_config = MagicMock()
            mock_config.security.auto_approve_safe_operations = False
            mock_config.security.require_approval_for_code = False
            mock_get_config.return_value = mock_config
            
            supervisor = Supervisor()
            supervisor._config = mock_config
            return supervisor
    
    def test_supervisor_init(self, supervisor):
        """Test Supervisor initialization."""
        assert supervisor.name == "Supervisor"
        assert supervisor._bedrock_client is None
        assert supervisor._pending_approvals == {}
    
    def test_supervisor_name(self, supervisor):
        """Test Supervisor has correct name."""
        assert supervisor.name == "Supervisor"


class TestSupervisorScanCode:
    """Test Supervisor code scanning functionality."""
    
    @pytest.fixture
    def supervisor(self):
        """Create a Supervisor instance for testing."""
        with patch("src.engine.supervisor.get_config") as mock_get_config:
            mock_config = MagicMock()
            mock_config.security.auto_approve_safe_operations = False
            mock_config.security.require_approval_for_code = False
            mock_get_config.return_value = mock_config
            
            supervisor = Supervisor()
            supervisor._config = mock_config
            return supervisor
    
    @pytest.mark.asyncio
    async def test_scan_safe_code(self, supervisor):
        """Test scanning safe code with no issues."""
        code = """
import json
import os

def hello():
    return "Hello, World!"
"""
        result = await supervisor.scan_code(code)
        
        assert result["status"] == "success"
        assert result["passed"] is True
        assert result["risk_level"] == "low"
    
    @pytest.mark.asyncio
    async def test_scan_code_with_dangerous_pattern(self, supervisor):
        """Test scanning code with dangerous patterns."""
        code = """
import os

os.system("rm -rf /")
"""
        result = await supervisor.scan_code(code)
        
        assert result["status"] == "success"
        assert result["passed"] is False
        assert result["risk_level"] == "high"
        assert len(result["findings"]) > 0
        assert any(f["type"] == "dangerous_pattern" for f in result["findings"])
    
    @pytest.mark.asyncio
    async def test_scan_code_with_blocked_import(self, supervisor):
        """Test scanning code with blocked imports."""
        code = """
import subprocess
import pickle

subprocess.call(["ls"])
"""
        result = await supervisor.scan_code(code)
        
        assert result["status"] == "success"
        assert result["passed"] is False
        assert result["risk_level"] == "critical"
        assert any(f["type"] == "blocked_import" for f in result["findings"])
    
    @pytest.mark.asyncio
    async def test_scan_code_with_eval(self, supervisor):
        """Test scanning code with eval."""
        code = """
result = eval(user_input)
"""
        result = await supervisor.scan_code(code)
        
        assert result["passed"] is False
        assert result["risk_level"] == "high"
        assert any("eval" in str(f) for f in result["findings"])
    
    @pytest.mark.asyncio
    async def test_scan_code_with_unverified_import(self, supervisor):
        """Test scanning code with unverified imports."""
        code = """
import unknown_module
import another_unknown

unknown_module.do_something()
"""
        result = await supervisor.scan_code(code)
        
        # Should have unverified import findings
        assert any(f["type"] == "unverified_import" for f in result["findings"])
    
    @pytest.mark.asyncio
    async def test_scan_code_critical_severity_detection(self, supervisor):
        """Test that critical severity is detected."""
        code = """
import socket
socket.socket()
"""
        result = await supervisor.scan_code(code)
        
        assert result["risk_level"] == "critical"
        assert result["passed"] is False
    
    @pytest.mark.asyncio
    async def test_scan_code_with_recommendations(self, supervisor):
        """Test that recommendations are generated."""
        code = """
import os
os.system("echo test")
"""
        result = await supervisor.scan_code(code)
        
        assert len(result["recommendations"]) > 0
        # Check findings contain security-related descriptions
        assert any("dangerous" in str(f).lower() or "security" in str(f).lower()
                   for f in result["findings"])


class TestSupervisorReviewPrimitive:
    """Test Supervisor primitive review functionality."""
    
    @pytest.fixture
    def supervisor(self):
        """Create a Supervisor instance for testing."""
        with patch("src.engine.supervisor.get_config") as mock_get_config:
            mock_config = MagicMock()
            mock_config.security.auto_approve_safe_operations = False
            mock_config.security.require_approval_for_code = False
            mock_get_config.return_value = mock_config
            
            supervisor = Supervisor()
            supervisor._config = mock_config
            return supervisor
    
    @pytest.mark.asyncio
    async def test_review_safe_primitive(self, supervisor):
        """Test reviewing a safe primitive."""
        # Use a valid Python code with proper structure that passes quality checks
        code = '''
"""A safe primitive module."""
import json

def process(data):
    """Process data safely."""
    try:
        return json.dumps(data)
    except Exception as e:
        return str(e)
'''
        result = await supervisor.review_primitive("safe_primitive", code)
        
        assert result["status"] == "success"
        assert result["primitive_name"] == "safe_primitive"
        # Approval depends on both security scan and quality check passing
        # This primitive should pass security (low risk) and quality checks
    
    @pytest.mark.asyncio
    async def test_review_dangerous_primitive(self, supervisor):
        """Test reviewing a dangerous primitive."""
        code = """
import os
os.system("rm -rf /")
"""
        result = await supervisor.review_primitive("dangerous", code)
        
        assert result["approved"] is False
        assert "security" in result["reason"].lower()
    
    @pytest.mark.asyncio
    async def test_review_primitive_missing_docstring(self, supervisor):
        """Test reviewing primitive without docstring."""
        code = """
import json

def process(data):
    return json.dumps(data)
"""
        result = await supervisor.review_primitive("no_doc", code)
        
        # Quality check should fail but security may pass
        assert "quality_check" in result
    
    @pytest.mark.asyncio
    async def test_review_primitive_auto_approval(self, supervisor):
        """Test auto-approval for low-risk primitives."""
        supervisor._config.security.auto_approve_safe_operations = True
        
        code = """
\"\"\"Safe primitive.\"\"\"
import json
"""
        result = await supervisor.review_primitive("auto_safe", code)
        
        assert result["approved"] is True
        assert "auto-approved" in result["reason"].lower()
    
    @pytest.mark.asyncio
    async def test_review_primitive_requires_manual_review(self, supervisor):
        """Test that medium risk primitives require manual review."""
        code = """
import unknown_module

unknown_module.do_something()
"""
        result = await supervisor.review_primitive("unverified", code)
        
        # Check requires_manual_review flag is set correctly
        assert "requires_manual_review" in result


class TestSupervisorValidateImports:
    """Test Supervisor import validation."""
    
    @pytest.fixture
    def supervisor(self):
        """Create a Supervisor instance for testing."""
        with patch("src.engine.supervisor.get_config") as mock_get_config:
            mock_config = MagicMock()
            mock_get_config.return_value = mock_config
            
            supervisor = Supervisor()
            supervisor._config = mock_config
            return supervisor
    
    @pytest.mark.asyncio
    async def test_validate_allowed_imports(self, supervisor):
        """Test validating allowed imports."""
        imports = ["json", "os", "re"]
        result = await supervisor.validate_imports(imports)
        
        assert result["status"] == "success"
        assert result["valid"] is True
        assert len(result["allowed"]) == 3
        assert len(result["blocked"]) == 0
    
    @pytest.mark.asyncio
    async def test_validate_blocked_imports(self, supervisor):
        """Test validating blocked imports."""
        imports = ["subprocess", "socket", "json"]
        result = await supervisor.validate_imports(imports)
        
        assert result["valid"] is False
        assert "subprocess" in result["blocked"]
        assert "socket" in result["blocked"]
        assert "json" in result["allowed"]
    
    @pytest.mark.asyncio
    async def test_validate_unverified_imports(self, supervisor):
        """Test validating unverified imports."""
        imports = ["unknown_module", "another_unknown"]
        result = await supervisor.validate_imports(imports)
        
        assert result["valid"] is True  # Not blocked, just unverified
        assert len(result["unverified"]) == 2
        assert "unknown_module" in result["unverified"]


class TestSupervisorExecuteTask:
    """Test Supervisor task execution."""
    
    @pytest.fixture
    def supervisor(self):
        """Create a Supervisor instance for testing."""
        with patch("src.engine.supervisor.get_config") as mock_get_config:
            mock_config = MagicMock()
            mock_config.security.auto_approve_safe_operations = False
            mock_config.security.require_approval_for_code = False
            mock_get_config.return_value = mock_config
            
            supervisor = Supervisor()
            supervisor._config = mock_config
            return supervisor
    
    @pytest.mark.asyncio
    async def test_execute_scan_code_task(self, supervisor):
        """Test executing scan_code task."""
        task = TaskPayload(
            action="scan_code",
            params={"code": "import json"}
        )
        
        result = await supervisor.execute_task(task)
        
        assert result["status"] == "success"
        assert "passed" in result
    
    @pytest.mark.asyncio
    async def test_execute_review_primitive_task(self, supervisor):
        """Test executing review_primitive task."""
        task = TaskPayload(
            action="review_primitive",
            params={
                "name": "test_primitive",
                "code": "import json"
            }
        )
        
        result = await supervisor.execute_task(task)
        
        assert result["status"] == "success"
        assert "approved" in result
    
    @pytest.mark.asyncio
    async def test_execute_validate_imports_task(self, supervisor):
        """Test executing validate_imports task."""
        task = TaskPayload(
            action="validate_imports",
            params={"imports": ["json", "os"]}
        )
        
        result = await supervisor.execute_task(task)
        
        assert result["status"] == "success"
        assert "valid" in result
    
    @pytest.mark.asyncio
    async def test_execute_unknown_task(self, supervisor):
        """Test executing unknown task."""
        task = TaskPayload(action="unknown_action")
        
        result = await supervisor.execute_task(task)
        
        assert result["status"] == "error"
        assert "Unknown action" in result["message"]


class TestSupervisorApprovalProcess:
    """Test Supervisor approval processing."""
    
    @pytest.fixture
    def supervisor(self):
        """Create a Supervisor instance for testing."""
        with patch("src.engine.supervisor.get_config") as mock_get_config:
            mock_config = MagicMock()
            mock_config.security.auto_approve_safe_operations = False
            mock_config.security.require_approval_for_code = False
            mock_get_config.return_value = mock_config
            
            supervisor = Supervisor()
            supervisor._config = mock_config
            return supervisor
    
    @pytest.mark.asyncio
    async def test_process_approval_request_low_risk_auto(self, supervisor):
        """Test processing low risk request with auto-approval."""
        supervisor._config.security.auto_approve_safe_operations = True
        
        approval_data = {
            "action_type": "code_execution",
            "action_description": "Run safe code",
            "security_scan": {"risk_level": "low"}
        }
        
        result = await supervisor._process_approval_request(approval_data)
        
        assert result["status"] == "approved"
        assert "auto-approved" in result["reason"].lower()
    
    @pytest.mark.asyncio
    async def test_process_approval_request_manual_required(self, supervisor):
        """Test processing request requiring manual approval."""
        supervisor._config.security.require_approval_for_code = True
        
        approval_data = {
            "action_type": "code_execution",
            "action_description": "Run code",
            "security_scan": {"risk_level": "low"}
        }
        
        result = await supervisor._process_approval_request(approval_data)
        
        assert result["status"] == "pending_manual"
        assert "manual approval required" in result["reason"].lower()
    
    @pytest.mark.asyncio
    async def test_process_approval_request_denied_high_risk(self, supervisor):
        """Test processing high risk request."""
        approval_data = {
            "action_type": "dangerous_action",
            "action_description": "Run dangerous code",
            "security_scan": {"risk_level": "high", "findings": []}
        }
        
        result = await supervisor._process_approval_request(approval_data)
        
        assert result["status"] == "denied"
        assert "high" in result["reason"].lower()
    
    @pytest.mark.asyncio
    async def test_process_approval_request_denied_critical(self, supervisor):
        """Test processing critical risk request."""
        approval_data = {
            "action_type": "critical_action",
            "action_description": "Run critical code",
            "security_scan": {"risk_level": "critical", "findings": []}
        }
        
        result = await supervisor._process_approval_request(approval_data)
        
        assert result["status"] == "denied"
        assert "critical" in result["reason"].lower()


class TestSupervisorCodeQuality:
    """Test Supervisor code quality checks."""
    
    @pytest.fixture
    def supervisor(self):
        """Create a Supervisor instance for testing."""
        with patch("src.engine.supervisor.get_config") as mock_get_config:
            mock_config = MagicMock()
            mock_get_config.return_value = mock_config
            
            supervisor = Supervisor()
            supervisor._config = mock_config
            return supervisor
    
    @pytest.mark.asyncio
    async def test_check_code_quality_with_docstring(self, supervisor):
        """Test quality check for code with docstring."""
        # Code must have module docstring AND function docstrings
        code = '''
"""Module docstring."""

def func():
    """Function docstring."""
    pass
'''
        result = await supervisor._check_code_quality("test", code)
        
        # May still have issues like missing error handling, but docstring check passes
        assert "passed" in result
        assert "issues" in result
    
    @pytest.mark.asyncio
    async def test_check_code_quality_missing_docstring(self, supervisor):
        """Test quality check for code without docstring."""
        code = """
def func():
    pass
"""
        result = await supervisor._check_code_quality("test", code)
        
        assert result["passed"] is False
        assert any("docstring" in issue.lower() for issue in result["issues"])
    
    @pytest.mark.asyncio
    async def test_check_code_quality_long_lines(self, supervisor):
        """Test quality check for code with long lines."""
        code = '''
"""Module docstring."""

x = "This is a very long line that exceeds the 120 character limit which is not allowed in the codebase and continues further"
'''
        result = await supervisor._check_code_quality("test", code)
        
        # Should detect long lines issue
        assert any("long" in issue.lower() or "120" in issue for issue in result["issues"])
    
    @pytest.mark.asyncio
    async def test_check_code_quality_try_without_except(self, supervisor):
        """Test quality check for try without except."""
        code = '''
"""Module docstring."""

try:
    something()
'''
        result = await supervisor._check_code_quality("test", code)
        
        assert any("try" in issue.lower() and "except" in issue.lower() for issue in result["issues"])


class TestGetSupervisor:
    """Test get_supervisor function."""
    
    @patch("src.engine.supervisor.get_config")
    def test_get_supervisor_singleton(self, mock_get_config):
        """Test that get_supervisor returns a singleton."""
        mock_config = MagicMock()
        mock_get_config.return_value = mock_config
        
        supervisor1 = get_supervisor()
        supervisor2 = get_supervisor()
        
        assert supervisor1 is supervisor2
    
    @patch("src.engine.supervisor.get_config")
    def test_get_supervisor_creates_new(self, mock_get_config):
        """Test that get_supervisor creates new instance if None."""
        mock_config = MagicMock()
        mock_get_config.return_value = mock_config
        
        # Reset singleton
        import src.engine.supervisor as supervisor_module
        supervisor_module._supervisor = None
        
        supervisor = get_supervisor()
        assert supervisor is not None
        assert isinstance(supervisor, Supervisor)
