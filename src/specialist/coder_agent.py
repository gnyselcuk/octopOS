"""Coder Agent - Dynamic primitive and tool generation.

This module implements the Coder Agent that:
- Generates new primitive tools based on requirements
- Writes clean, documented Python code
- Integrates with Supervisor for security approval
- Registers new primitives with the IntentFinder
"""

import json
import re
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from src.engine.base_agent import BaseAgent
from src.engine.message import (
    ErrorPayload,
    ErrorSeverity,
    MessageType,
    OctoMessage,
    TaskPayload,
    TaskStatus,
)
from src.utils.aws_sts import get_bedrock_client
from src.utils.config import get_config
from src.utils.logger import AgentLogger


class CoderAgent(BaseAgent):
    """Coder Agent - Creates new primitive tools dynamically.
    
    The Coder Agent is responsible for:
    1. Generating Python code based on natural language descriptions
    2. Writing well-documented, tested code
    3. Submitting code to Supervisor for security review
    4. Integrating approved primitives into the system
    
    Example:
        >>> coder = CoderAgent()
        >>> await coder.start()
        >>> result = await coder.create_primitive(
        ...     "Create a tool that uploads files to S3"
        ... )
    """
    
    def __init__(self, context: Optional[Any] = None) -> None:
        """Initialize the Coder Agent.
        
        Args:
            context: Shared agent context
        """
        super().__init__(name="CoderAgent", context=context)
        self.agent_logger = AgentLogger("CoderAgent")
        self._config = get_config()
        self._bedrock_client = None
        self._pending_reviews: Dict[UUID, Dict[str, Any]] = {}
        self.agent_logger.info("CoderAgent initialized")
    
    async def on_start(self) -> None:
        """Initialize Bedrock client."""
        try:
            self._bedrock_client = get_bedrock_client()
            self.agent_logger.info("CoderAgent Bedrock client initialized")
        except Exception as e:
            self.agent_logger.error(f"Failed to initialize Bedrock: {e}")
            raise
    
    async def execute_task(self, task: TaskPayload) -> Dict[str, Any]:
        """Execute a task assigned to the Coder Agent.
        
        Args:
            task: The task payload
            
        Returns:
            Task execution results
        """
        self.agent_logger.info(f"Executing task: {task.action}")
        
        if task.action == "create_primitive":
            description = task.params.get("description", "")
            name = task.params.get("name")
            language = task.params.get("language", "python")
            return await self.create_primitive(description, name, language)
            
        elif task.action == "modify_primitive":
            name = task.params.get("name", "")
            changes = task.params.get("changes", "")
            current_code = task.params.get("current_code", "")
            return await self.modify_primitive(name, current_code, changes)
            
        elif task.action == "fix_code":
            code = task.params.get("code", "")
            error = task.params.get("error", "")
            return await self.fix_code(code, error)
            
        elif task.action == "review_feedback":
            # Handle feedback from Supervisor
            approval_id = task.params.get("approval_id")
            approved = task.params.get("approved", False)
            feedback = task.params.get("feedback", "")
            return await self._handle_review_feedback(approval_id, approved, feedback)
            
        else:
            return {"status": "error", "message": f"Unknown action: {task.action}"}
    
    async def create_primitive(
        self,
        description: str,
        name: Optional[str] = None,
        language: str = "python",
        delivery_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a new primitive tool — full inline pipeline.

        Pipeline:
            1. Generate code via Nova Pro
            2. Supervisor.review_primitive (rule-based + LLM security scan)
            3. SelfHealingAgent.test_code_in_sandbox (Docker or subprocess)
            4. IntentFinder.add_primitive (register permanently)
            5. FileDeliveryService: upload to private S3 → deliver via channel

        Args:
            description: Natural language description of what to create
            name: Optional suggested name
            language: Programming language (default: python)
            delivery_context: Optional dict with delivery info:
                {
                    "channel": "telegram" | "cli",
                    "chat_id": str,          # for Telegram
                    "bot": TelegramBot,      # for Telegram
                    "reply_to": str,         # optional message id
                }

        Returns:
            Result dict with status, code, s3_key, presigned_url
        """
        self.agent_logger.info(f"Creating primitive (full pipeline): {description[:80]}…")

        # ── Stage 1: Generate code ──────────────────────────────────────────
        code = await self._generate_code(description, name, language)
        if not code:
            return {"status": "error", "message": "Code generation failed (LLM returned empty)"}

        if not name:
            name = self._extract_name_from_description(description)

        self.agent_logger.info(f"Code generated for '{name}' ({len(code)} chars)")

        # ── Stage 2: Security review (Supervisor) ───────────────────────────
        try:
            from src.engine.supervisor import Supervisor
            supervisor = Supervisor()
            supervisor._bedrock_client = self._bedrock_client
            review = await supervisor.review_primitive(name, code)
        except Exception as e:
            self.agent_logger.error(f"Supervisor review failed: {e}")
            review = {"approved": False, "reason": str(e), "security_scan": {}}

        risk = review.get("security_scan", {}).get("risk_level", "unknown")
        approved_by_supervisor = review.get("approved", False)

        self.agent_logger.info(
            f"Supervisor review for '{name}': "
            f"{'APPROVED' if approved_by_supervisor else 'DENIED'} (risk={risk})"
        )

        if not approved_by_supervisor:
            return {
                "status":        "rejected",
                "intent":        "code",
                "message":       f"🛡️ Güvenlik incelemesi reddetti: {review.get('reason', 'Bilinmeyen sebep')}",
                "name":          name,
                "risk_level":    risk,
                "findings":      review.get("security_scan", {}).get("findings", []),
                "full_code":     code,
            }

        # ── Stage 3: Sandbox test (Docker → subprocess fallback) ────────────
        try:
            from src.specialist.self_healing_agent import SelfHealingAgent
            healer = SelfHealingAgent()
            healer._bedrock_client = self._bedrock_client
            test_result = await healer.test_code_in_sandbox(code, name)
        except Exception as e:
            self.agent_logger.error(f"Sandbox test failed with exception: {e}")
            test_result = {"passed": False, "message": str(e), "method": "error"}

        sandbox_method = test_result.get("method", "unknown")
        self.agent_logger.info(
            f"Sandbox ({sandbox_method}) test for '{name}': "
            f"{'PASS' if test_result.get('passed') else 'FAIL'}"
        )

        if not test_result.get("passed"):
            stderr = test_result.get("stderr", "")
            return {
                "status":        "test_failed",
                "intent":        "code",
                "message":       f"⚠️ Sandbox testi başarısız: {test_result.get('message', stderr[:200])}",
                "name":          name,
                "sandbox_method": sandbox_method,
                "stdout":        test_result.get("stdout", ""),
                "stderr":        stderr,
                "full_code":     code,
            }

        # ── Stage 4: Register with IntentFinder ─────────────────────────────
        try:
            from src.engine.memory.intent_finder import get_intent_finder
            docs = await self._generate_documentation(code, description)
            intent_finder = await get_intent_finder()
            await intent_finder.add_primitive(
                name=name,
                description=docs.get("description", description),
                code=code,
                metadata={
                    "created_by":   "CoderAgent",
                    "approved_by":  "Supervisor",
                    "risk_level":   risk,
                    "sandbox":      sandbox_method,
                    "docs":         docs,
                }
            )
            registered = True
            self.agent_logger.info(f"Primitive '{name}' registered in IntentFinder ✅")
        except Exception as e:
            self.agent_logger.error(f"IntentFinder registration failed: {e}")
            registered = False

        result = {
            "status":          "success" if registered else "pending_review",
            "intent":          "code",
            "name":            name,
            "risk_level":      risk,
            "sandbox_method":  sandbox_method,
            "registered":      registered,
            "full_code":       code,
            "code_preview":    code[:500] + "…" if len(code) > 500 else code,
            "message": (
                f"✅ `{name}` oluşturuldu, test edildi ve sisteme kaydedildi."
                if registered else
                f"✅ `{name}` oluşturuldu ve test edildi — kayıt manuel onay bekliyor."
            ),
        }

        # ── Stage 5: File delivery (S3 upload + channel send) ────────────────
        try:
            from src.utils.file_delivery import get_file_delivery_service, DeliveryChannel

            ctx = delivery_context or {}
            channel_str = ctx.get("channel", "cli")
            channel = DeliveryChannel(channel_str) if channel_str in DeliveryChannel._value2member_map_ else DeliveryChannel.CLI

            delivery = await get_file_delivery_service().deliver_code(
                code=code,
                name=name,
                channel=channel,
                chat_id=ctx.get("chat_id"),
                bot=ctx.get("bot"),
                reply_to=ctx.get("reply_to"),
                extra_caption=f"\n<i>🛡 Risk: {risk} | 🧪 Sandbox: {sandbox_method}</i>",
            )
            result["s3_key"]       = delivery.get("s3_key", "")
            result["presigned_url"] = delivery.get("presigned_url", "")
            result["delivered"]    = delivery.get("delivered", False)
            self.agent_logger.info(
                f"File delivery for '{name}': delivered={result['delivered']}, "
                f"s3_key={result['s3_key']}"
            )
        except Exception as e:
            self.agent_logger.warning(f"File delivery failed (non-fatal): {e}")

        return result


    async def _generate_code(
        self,
        description: str,
        name: Optional[str],
        language: str
    ) -> str:
        """Generate code using the LLM.
        
        Args:
            description: What to create
            name: Suggested name
            language: Programming language
            
        Returns:
            Generated code
        """
        system_prompt = """You are an expert Python programmer creating tools for an AI agent system.
Write clean, well-documented, secure code following these guidelines:

1. Use type hints
2. Include docstrings for all functions/classes
3. Handle errors gracefully with try/except
4. No dangerous operations (no eval, exec, os.system, etc.)
5. Keep it focused and single-purpose
6. Include example usage in docstrings

The code will be used as a 'primitive' tool that the AI agent can call.
"""

        name_hint = f"Suggested name: {name}" if name else "Choose an appropriate name"
        
        prompt = f"""Create a Python function/class for this task:

{description}

{name_hint}

Requirements:
- The code should be a complete, runnable Python module
- Include imports at the top
- Use clear variable names
- Add error handling
- Return results as dictionaries

Provide only the code, no explanations."""

        try:
            response = self._bedrock_client.converse(
                modelId=self._config.aws.model_nova_pro,
                system=[{"text": system_prompt}],
                messages=[{"role": "user", "content": [{"text": prompt}]}],
                inferenceConfig={"temperature": 0.3, "maxTokens": 2000}
            )
            
            code = response['output']['message']['content'][0]['text']
            
            # Extract code from markdown if present
            if "```python" in code:
                code = code.split("```python")[1].split("```")[0]
            elif "```" in code:
                code = code.split("```")[1].split("```")[0]
            
            return code.strip()
            
        except Exception as e:
            self.agent_logger.error(f"Code generation failed: {e}")
            return ""
    
    async def _generate_documentation(self, code: str, description: str) -> Dict[str, str]:
        """Generate documentation for the code.
        
        Args:
            code: The code to document
            description: Original description
            
        Returns:
            Documentation parts
        """
        prompt = f"""Generate documentation for this Python code:

```python
{code}
```

Original purpose: {description}

Provide a JSON object with:
{{
    "summary": "One-line summary",
    "description": "Detailed description",
    "parameters": "Description of parameters",
    "returns": "Description of return value",
    "examples": "Usage examples"
}}"""

        try:
            response = self._bedrock_client.converse(
                modelId=self._config.aws.model_nova_lite,
                messages=[{"role": "user", "content": [{"text": prompt}]}],
                inferenceConfig={"temperature": 0.2, "maxTokens": 1000}
            )
            
            response_text = response['output']['message']['content'][0]['text']
            
            # Parse JSON
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0]
            
            docs = json.loads(response_text.strip())
            return docs
            
        except Exception as e:
            self.agent_logger.warning(f"Documentation generation failed: {e}")
            return {
                "summary": "Auto-generated primitive",
                "description": description,
                "parameters": "See code",
                "returns": "See code",
                "examples": "See code docstrings"
            }
    
    def _extract_name_from_description(self, description: str) -> str:
        """Extract a reasonable name from description.
        
        Args:
            description: Natural language description
            
        Returns:
            Snake_case name
        """
        # Remove common words and convert to snake_case
        words = description.lower().split()
        keywords = [w for w in words if w not in [
            'a', 'an', 'the', 'to', 'for', 'that', 'which', 'with',
            'create', 'make', 'build', 'generate', 'write'
        ] and w.isalnum()]
        
        if len(keywords) >= 3:
            name = "_".join(keywords[:3])
        elif keywords:
            name = "_".join(keywords)
        else:
            name = f"primitive_{uuid4().hex[:8]}"
        
        # Clean up
        name = re.sub(r'[^a-z0-9_]', '_', name)
        name = re.sub(r'_+', '_', name)
        
        return name[:50]  # Limit length
    
    async def modify_primitive(
        self,
        name: str,
        current_code: str,
        changes: str
    ) -> Dict[str, Any]:
        """Modify an existing primitive.
        
        Args:
            name: Name of primitive
            current_code: Current code
            changes: Description of changes needed
            
        Returns:
            Modification results
        """
        self.agent_logger.info(f"Modifying primitive: {name}")
        
        prompt = f"""Modify this Python code according to the requested changes:

Current code:
```python
{current_code}
```

Changes needed:
{changes}

Provide only the modified code, no explanations."""

        try:
            response = self._bedrock_client.converse(
                modelId=self._config.aws.model_nova_pro,
                messages=[{"role": "user", "content": [{"text": prompt}]}],
                inferenceConfig={"temperature": 0.3, "maxTokens": 2000}
            )
            
            new_code = response['output']['message']['content'][0]['text']
            
            # Extract code
            if "```python" in new_code:
                new_code = new_code.split("```python")[1].split("```")[0]
            elif "```" in new_code:
                new_code = new_code.split("```")[1].split("```")[0]
            
            # Send for review
            approval_id = uuid4()
            self.request_approval(
                action_type="modify_primitive",
                action_description=f"Modify primitive '{name}': {changes}",
                code_changes=new_code
            )
            
            self._pending_reviews[approval_id] = {
                "name": name,
                "code": new_code.strip(),
                "previous_code": current_code,
                "status": "pending_review"
            }
            
            return {
                "status": "pending_review",
                "message": "Modified code sent for security review",
                "approval_id": str(approval_id)
            }
            
        except Exception as e:
            self.agent_logger.error(f"Code modification failed: {e}")
            return {"status": "error", "message": str(e)}
    
    async def fix_code(self, code: str, error: str) -> Dict[str, Any]:
        """Fix code that has errors.
        
        Args:
            code: Code with errors
            error: Error message
            
        Returns:
            Fixed code
        """
        self.agent_logger.info("Fixing code based on error")
        
        prompt = f"""Fix this Python code that has an error:

Code:
```python
{code}
```

Error:
{error}

Provide only the fixed code, no explanations."""

        try:
            response = self._bedrock_client.converse(
                modelId=self._config.aws.model_nova_pro,
                messages=[{"role": "user", "content": [{"text": prompt}]}],
                inferenceConfig={"temperature": 0.3, "maxTokens": 2000}
            )
            
            fixed_code = response['output']['message']['content'][0]['text']
            
            # Extract code
            if "```python" in fixed_code:
                fixed_code = fixed_code.split("```python")[1].split("```")[0]
            elif "```" in fixed_code:
                fixed_code = fixed_code.split("```")[1].split("```")[0]
            
            return {
                "status": "success",
                "fixed_code": fixed_code.strip()
            }
            
        except Exception as e:
            self.agent_logger.error(f"Code fixing failed: {e}")
            return {"status": "error", "message": str(e)}
    
    async def _handle_review_feedback(
        self,
        approval_id: UUID,
        approved: bool,
        feedback: str
    ) -> Dict[str, Any]:
        """Handle feedback from Supervisor review.
        
        Args:
            approval_id: ID of the approval request
            approved: Whether it was approved
            feedback: Feedback message
            
        Returns:
            Handling results
        """
        if approval_id not in self._pending_reviews:
            return {"status": "error", "message": "Unknown approval ID"}
        
        review = self._pending_reviews[approval_id]
        
        if approved:
            review["status"] = "approved"
            
            # Register the primitive with IntentFinder
            try:
                from src.engine.memory.intent_finder import get_intent_finder
                
                intent_finder = await get_intent_finder()
                await intent_finder.add_primitive(
                    name=review["name"],
                    description=review.get("docs", {}).get("description", review["description"]),
                    code=review["code"],
                    metadata={
                        "created_by": "CoderAgent",
                        "approved_by": "Supervisor",
                        "docs": review.get("docs", {})
                    }
                )
                
                self.agent_logger.info(f"Primitive registered: {review['name']}")
                
                return {
                    "status": "success",
                    "message": f"Primitive '{review['name']}' approved and registered",
                    "name": review["name"]
                }
                
            except Exception as e:
                self.agent_logger.error(f"Failed to register primitive: {e}")
                return {
                    "status": "error",
                    "message": f"Approved but registration failed: {e}"
                }
        else:
            review["status"] = "rejected"
            review["feedback"] = feedback
            
            self.agent_logger.info(f"Primitive rejected: {review['name']} - {feedback}")
            
            return {
                "status": "rejected",
                "message": f"Primitive '{review['name']}' was rejected",
                "feedback": feedback
            }
    
    def _on_message(self, message: OctoMessage) -> None:
        """Handle incoming messages.
        
        Args:
            message: Received message
        """
        super()._on_message(message)
        
        if message.type == MessageType.APPROVAL_GRANTED:
            self.agent_logger.info(f"Received approval from {message.sender}")
            # Handle approval in next task execution
        elif message.type == MessageType.APPROVAL_DENIED:
            self.agent_logger.info(f"Received denial from {message.sender}")
            # Handle denial in next task execution
    
    async def on_stop(self) -> None:
        """Cleanup on stop."""
        self.agent_logger.info("CoderAgent shutting down")
        self._pending_reviews.clear()


# Singleton instance
_coder_agent: Optional[CoderAgent] = None


def get_coder_agent() -> CoderAgent:
    """Get the global CoderAgent instance.
    
    Returns:
        Singleton CoderAgent instance
    """
    global _coder_agent
    if _coder_agent is None:
        _coder_agent = CoderAgent()
    return _coder_agent