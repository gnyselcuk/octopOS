"""Workflow Integration - Complete workflow orchestration.

Integrates all components for end-to-end workflow:
Main Brain → IntentFinder → Coder → Self-Healing → Supervisor → Registration
"""

from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from src.engine.orchestrator import Orchestrator
from src.engine.memory.intent_finder import IntentFinder
from src.engine.supervisor import Supervisor
from src.specialist.manager_agent import ManagerAgent, get_manager_agent
from src.specialist.coder_agent import CoderAgent, get_coder_agent
from src.specialist.self_healing_agent import SelfHealingAgent, get_self_healing_agent
from src.engine.message import MessageType, OctoMessage, TaskPayload, TaskStatus
from src.utils.logger import get_logger

logger = get_logger()


class CompleteWorkflowOrchestrator:
    """Complete workflow orchestration for primitive creation.
    
    Implements the full workflow:
    1. Main Brain checks IntentFinder for available tools
    2. If not available → triggers Coder Agent
    3. Coder generates code → sends to Self-Healing for testing
    4. Self-Healing tests → reports to Supervisor
    5. Supervisor approves → Manager registers with IntentFinder
    6. Worker executes with anomaly detection
    """
    
    def __init__(self, orchestrator: Orchestrator):
        """Initialize with existing orchestrator.
        
        Args:
            orchestrator: Main Brain orchestrator
        """
        self._orchestrator = orchestrator
        self._intent_finder = IntentFinder()
        self._manager = get_manager_agent()
        self._coder = get_coder_agent()
        self._healer = get_self_healing_agent()
        self._supervisor = None  # Would be initialized from orchestrator
        
        self._pending_workflows: Dict[UUID, Dict] = {}
        
    async def initialize(self):
        """Initialize all components."""
        await self._intent_finder.initialize()
        await self._manager.start()
        await self._coder.start()
        await self._healer.start()
        
        # Register specialist agents with manager
        await self._manager.execute_task(TaskPayload(
            action="register_agent",
            params={
                "agent_id": self._coder.name,
                "agent_type": "CoderAgent",
                "capabilities": ["code_generation", "code_modification", "debugging"]
            }
        ))
        await self._manager.execute_task(TaskPayload(
            action="register_agent",
            params={
                "agent_id": self._healer.name,
                "agent_type": "SelfHealingAgent",
                "capabilities": ["debugging", "error_analysis", "auto_repair"]
            }
        ))
        await self._manager.execute_task(TaskPayload(
            action="register_agent",
            params={
                "agent_id": "Supervisor",
                "agent_type": "Supervisor",
                "capabilities": ["security_review", "approval"]
            }
        ))
        
        logger.info("CompleteWorkflowOrchestrator initialized")
        
    async def process_with_workflow(
        self,
        user_input: str,
        user_id: str
    ) -> Dict[str, Any]:
        """Process user input with complete workflow.
        
        Args:
            user_input: User request
            user_id: User identifier
            
        Returns:
            Processing result
        """
        logger.info(f"Processing workflow for: {user_input[:50]}...")
        
        # Step 1: Check IntentFinder for existing primitives
        matches = await self._intent_finder.find_primitives(user_input, top_k=3)
        
        if matches and matches[0].score > 0.8:
            # Existing primitive found, use it
            logger.info(f"Found existing primitive: {matches[0].name}")
            return {
                "status": "success",
                "action": "use_existing",
                "primitive": matches[0].name,
                "confidence": matches[0].score
            }
        
        # Step 2: No matching primitive, create new one
        logger.info("No matching primitive found, creating new one")
        
        workflow_id = uuid4()
        
        # Trigger workflow through Manager Agent
        result = await self._manager.execute_task(TaskPayload(
            action="create_primitive_workflow",
            params={
                "description": user_input,
                "user_id": user_id,
                "workflow_id": str(workflow_id)
            }
        ))
        
        return {
            "status": result.get("status", "error"),
            "workflow_id": str(workflow_id),
            "result": result
        }
    
    async def handle_coder_completion(
        self,
        task_id: UUID,
        code: str,
        tests: str
    ) -> bool:
        """Handle Coder Agent completion.
        
        Routes to Self-Healing Agent for testing.
        
        Args:
            task_id: Original task ID
            code: Generated code
            tests: Generated tests
            
        Returns:
            True if routed successfully
        """
        logger.info(f"Routing Coder output to Self-Healing for task {task_id}")
        
        # Send to Self-Healing Agent
        await self._healer.execute_task(TaskPayload(
            action="test_code",
            params={
                "code": code,
                "tests": tests,
                "original_task": str(task_id)
            }
        ))
        
        return True
    
    async def handle_healing_completion(
        self,
        task_id: UUID,
        test_results: Dict,
        code: str
    ) -> bool:
        """Handle Self-Healing Agent completion.
        
        Routes to Supervisor for approval.
        
        Args:
            task_id: Original task ID
            test_results: Test execution results
            code: Code that was tested
            
        Returns:
            True if routed successfully
        """
        logger.info(f"Routing test results to Supervisor for task {task_id}")
        
        # Request approval from Supervisor
        # This would integrate with Supervisor approval workflow
        
        return True
    
    async def handle_approval(
        self,
        task_id: UUID,
        code: str,
        approved: bool
    ) -> bool:
        """Handle Supervisor approval.
        
        Registers primitive with IntentFinder if approved.
        
        Args:
            task_id: Original task ID
            code: Code to register
            approved: Approval status
            
        Returns:
            True if handled successfully
        """
        if not approved:
            logger.warning(f"Code not approved for task {task_id}")
            return False
        
        logger.info(f"Registering approved primitive for task {task_id}")
        
        # Register with IntentFinder
        await self._intent_finder.add_primitive(
            name=f"primitive_{task_id.hex[:8]}",
            description="Auto-generated primitive",
            code=code
        )
        
        return True
