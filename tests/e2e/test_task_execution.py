import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock
from src.engine.workflow_integration import CompleteWorkflowOrchestrator
from src.engine.orchestrator import Orchestrator

@pytest.mark.asyncio
async def test_simple_task_execution():
    """
    Feature: Basit Görev Yürütme
      Scenario: Kullanıcı bir Python betiği çalıştırmak istiyor
        Given kullanıcı bir istek gönderir
        When sistem niyeti analiz eder
        Then uygun primitive'i seçer
        And sonucu kullanıcıya döndürür
    """
    # Setup
    orchestrator = Orchestrator()
    workflow = CompleteWorkflowOrchestrator(orchestrator)
    
    # Mock IntentFinder behavior to simulate finding an existing tool
    match_mock = MagicMock()
    match_mock.score = 0.95
    match_mock.name = "python_runner"
    workflow._intent_finder.find_primitives = AsyncMock(return_value=[match_mock])
    
    # Execute workflow targeting a simple task
    result = await workflow.process_with_workflow("Python ile 2+2 hesapla", "user_123")
    
    # Assertions
    assert result["status"] == "success"
    assert result["action"] == "use_existing"
    assert result["primitive"] == "python_runner"
    workflow._intent_finder.find_primitives.assert_called_once()

@pytest.mark.asyncio
async def test_dynamic_primitive_development():
    """
    Feature: Dinamik Primitive Geliştirme
      Scenario: Mevcut olmayan bir araç için geliştirme
        Given kullanıcı "GitHub'dan repo klonla" isteği gönderir
        When sistem uygun primitive bulamaz
        Then Coder Agent devreye girer ve workflow tetiklenir
    """
    orchestrator = Orchestrator()
    workflow = CompleteWorkflowOrchestrator(orchestrator)
    
    # Mock IntentFinder to return nothing (simulating tool not found)
    workflow._intent_finder.find_primitives = AsyncMock(return_value=[])
    
    # Mock Manager Agent to return a workflow triggered status
    workflow._manager.execute_task = AsyncMock(return_value={
        "status": "workflow_started", 
        "message": "Coder Agent triggered"
    })
    
    # Execute workflow for a missing tool
    result = await workflow.process_with_workflow("GitHub'dan repo klonla", "user_123")
    
    # Assertions
    assert result["status"] == "workflow_started"
    assert "workflow_id" in result
    workflow._manager.execute_task.assert_called_once()
