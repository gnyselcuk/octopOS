"""Unit tests for interfaces/ui/automation_engine.py module.

This module tests the UI automation workflow engine.
"""

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from src.interfaces.ui.automation_engine import AutomationEngine, WorkflowStep


class TestWorkflowStep:
    """Test WorkflowStep dataclass."""
    
    def test_create_workflow_step(self):
        """Test creating a workflow step."""
        step = WorkflowStep(
            action="click",
            target="#submit-button",
            params={"wait_after": 1.0}
        )
        
        assert step.action == "click"
        assert step.target == "#submit-button"
        assert step.params == {"wait_after": 1.0}
    
    def test_workflow_step_types(self):
        """Test different workflow step action types."""
        actions = ["click", "type", "scroll", "wait"]
        
        for action in actions:
            step = WorkflowStep(
                action=action,
                target=f"target-{action}",
                params={}
            )
            assert step.action == action


class TestAutomationEngine:
    """Test AutomationEngine class."""
    
    @pytest.fixture
    def engine(self):
        """Create automation engine instance."""
        with patch('src.interfaces.ui.automation_engine.NovaActClient'):
            return AutomationEngine()
    
    def test_initialization(self, engine):
        """Test engine initialization."""
        assert engine._recorded_workflows == {}
    
    def test_record_workflow(self, engine):
        """Test starting workflow recording."""
        engine.record_workflow("test_workflow")
        
        assert "test_workflow" in engine._recorded_workflows
        assert engine._recorded_workflows["test_workflow"] == []
    
    def test_add_step(self, engine):
        """Test adding steps to a workflow."""
        engine.record_workflow("test_workflow")
        
        step1 = WorkflowStep(
            action="click",
            target="#button",
            params={}
        )
        step2 = WorkflowStep(
            action="type",
            target="#input",
            params={"text": "hello"}
        )
        
        engine.add_step("test_workflow", step1)
        engine.add_step("test_workflow", step2)
        
        assert len(engine._recorded_workflows["test_workflow"]) == 2
        assert engine._recorded_workflows["test_workflow"][0] == step1
        assert engine._recorded_workflows["test_workflow"][1] == step2
    
    def test_add_step_to_nonexistent_workflow(self, engine):
        """Test adding step to workflow that doesn't exist."""
        step = WorkflowStep(action="click", target="#button", params={})
        
        # Should not raise, just not add
        engine.add_step("nonexistent", step)
        
        assert "nonexistent" not in engine._recorded_workflows
    
    @pytest.mark.asyncio
    async def test_replay_workflow_success(self, engine):
        """Test replaying a recorded workflow successfully."""
        engine.record_workflow("login_flow")
        
        steps = [
            WorkflowStep("click", "#username", {}),
            WorkflowStep("type", "#username", {"text": "user123"}),
            WorkflowStep("click", "#login", {})
        ]
        
        for step in steps:
            engine.add_step("login_flow", step)
        
        result = await engine.replay_workflow("login_flow")
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_replay_nonexistent_workflow(self, engine):
        """Test replaying workflow that doesn't exist."""
        result = await engine.replay_workflow("nonexistent")
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_replay_workflow_with_variables(self, engine):
        """Test replaying workflow with variable substitution."""
        engine.record_workflow("data_entry")
        
        steps = [
            WorkflowStep("type", "#name", {"text": "{{name}}"}),
            WorkflowStep("type", "#email", {"text": "{{email}}"})
        ]
        
        for step in steps:
            engine.add_step("data_entry", step)
        
        variables = {"name": "John Doe", "email": "john@example.com"}
        result = await engine.replay_workflow("data_entry", variables)
        
        assert result is True
    
    def test_multiple_workflows(self, engine):
        """Test managing multiple workflows."""
        # Create multiple workflows
        engine.record_workflow("workflow1")
        engine.record_workflow("workflow2")
        
        step1 = WorkflowStep("click", "#btn1", {})
        step2 = WorkflowStep("click", "#btn2", {})
        
        engine.add_step("workflow1", step1)
        engine.add_step("workflow2", step2)
        
        assert len(engine._recorded_workflows) == 2
        assert len(engine._recorded_workflows["workflow1"]) == 1
        assert len(engine._recorded_workflows["workflow2"]) == 1
    
    def test_workflow_step_immutability(self, engine):
        """Test that workflow steps maintain their values."""
        engine.record_workflow("test")
        
        step = WorkflowStep(
            action="scroll",
            target="window",
            params={"direction": "down", "amount": 500}
        )
        
        engine.add_step("test", step)
        
        retrieved_step = engine._recorded_workflows["test"][0]
        assert retrieved_step.action == "scroll"
        assert retrieved_step.target == "window"
        assert retrieved_step.params["direction"] == "down"
        assert retrieved_step.params["amount"] == 500
    
    @pytest.mark.asyncio
    async def test_replay_empty_workflow(self, engine):
        """Test replaying workflow with no steps."""
        engine.record_workflow("empty_workflow")
        
        result = await engine.replay_workflow("empty_workflow")
        
        # Should succeed even with no steps
        assert result is True
    
    def test_workflow_overwrite(self, engine):
        """Test that recording same workflow name overwrites."""
        engine.record_workflow("test_flow")
        
        step1 = WorkflowStep("click", "#old", {})
        engine.add_step("test_flow", step1)
        
        # Record again - should reset
        engine.record_workflow("test_flow")
        
        assert len(engine._recorded_workflows["test_flow"]) == 0
