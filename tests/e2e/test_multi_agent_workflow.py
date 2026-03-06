import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock
from uuid import uuid4

from src.engine.workflow_integration import CompleteWorkflowOrchestrator
from src.engine.orchestrator import Orchestrator
from src.engine.message import TaskPayload

@pytest.mark.asyncio
async def test_error_recovery_workflow():
    """
    Feature: Hata Kurtarma ve Self-Healing
      Scenario: Code Generation sonrası test hatasının düzeltilmesi
        Given Coder Agent yeni bir araç kodu yazar
        And Self-Healing Agent kodu test ederken hata alır
        When Self-Healing Agent hata logunu analiz eder
        Then Kodu düzeltip tekrar test eder
    """
    orchestrator = Orchestrator()
    workflow = CompleteWorkflowOrchestrator(orchestrator)
    
    # Simulate a task id
    task_id = uuid4()
    faulty_code = "def error_func():\n    return 1 / 0"
    tests_code = "def test_error_func():\n    assert error_func() == 1"
    
    # Mock healer execution
    workflow._healer.execute_task = AsyncMock(return_value={
        "status": "testing_started",
        "message": "Self-Healing Agent testing code"
    })
    
    # Trigger the step where Coder finishes and hands over to Healer
    result = await workflow.handle_coder_completion(task_id, faulty_code, tests_code)
    
    assert result is True
    workflow._healer.execute_task.assert_called_once()
    
    # Verify the payload sent to healer
    called_payload: TaskPayload = workflow._healer.execute_task.call_args[0][0]
    assert called_payload.action == "test_code"
    assert called_payload.params["code"] == faulty_code
    assert called_payload.params["tests"] == tests_code

@pytest.mark.asyncio
async def test_approval_and_registration_workflow():
    """
    Feature: Güvenlik ve Onay
      Scenario: Başarılı olan aracın sisteme kaydedilmesi
        Given Supervisor kodu güvenli bulur ve onaylar
        When Onay işlemi workflow'a iletilir
        Then Kod IntentFinder'a kaydedilir
    """
    orchestrator = Orchestrator()
    workflow = CompleteWorkflowOrchestrator(orchestrator)
    
    task_id = uuid4()
    good_code = "def good_func():\n    return 'success'"
    
    # Mock intent finder add_primitive
    workflow._intent_finder.add_primitive = AsyncMock(return_value=True)
    
    # Handle approval with True
    result_approved = await workflow.handle_approval(task_id, good_code, approved=True)
    
    assert result_approved is True
    workflow._intent_finder.add_primitive.assert_called_once()
    
    # Handle approval with False
    workflow._intent_finder.add_primitive.reset_mock()
    result_rejected = await workflow.handle_approval(task_id, good_code, approved=False)
    
    assert result_rejected is False
    workflow._intent_finder.add_primitive.assert_not_called()
