"""Self-Healing Agent - Error handling and automatic debugging.

This module implements the Self-Healing Agent that:
- Analyzes error messages and stack traces
- Suggests fixes for code issues
- Attempts automatic repairs when safe
- Coordinates with CoderAgent for complex fixes
"""

import json
import re
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

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


class ErrorAnalysis:
    """Analysis of an error."""
    
    def __init__(
        self,
        error_type: str,
        root_cause: str,
        severity: ErrorSeverity,
        suggested_fix: str,
        auto_repairable: bool,
        confidence: float
    ):
        self.error_type = error_type
        self.root_cause = root_cause
        self.severity = severity
        self.suggested_fix = suggested_fix
        self.auto_repairable = auto_repairable
        self.confidence = confidence


class SelfHealingAgent(BaseAgent):
    """Self-Healing Agent - Automatic error diagnosis and repair.
    
    The Self-Healing Agent is responsible for:
    1. Analyzing error messages and stack traces
    2. Diagnosing root causes
    3. Suggesting or applying fixes
    4. Coordinating with CoderAgent for complex repairs
    5. Learning from error patterns
    
    Example:
        >>> healer = SelfHealingAgent()
        >>> await healer.start()
        >>> result = await healer.debug_error(error_message, code)
    """
    
    def __init__(self, context: Optional[Any] = None) -> None:
        """Initialize the Self-Healing Agent.
        
        Args:
            context: Shared agent context
        """
        super().__init__(name="SelfHealingAgent", context=context)
        self.agent_logger = AgentLogger("SelfHealingAgent")
        self._config = get_config()
        self._bedrock_client = None
        self._error_history: List[Dict[str, Any]] = []
        self.agent_logger.info("SelfHealingAgent initialized")
    
    async def on_start(self) -> None:
        """Initialize Bedrock client."""
        try:
            self._bedrock_client = get_bedrock_client()
            self.agent_logger.info("SelfHealingAgent Bedrock client initialized")
        except Exception as e:
            self.agent_logger.error(f"Failed to initialize Bedrock: {e}")
            raise
    
    async def execute_task(self, task: TaskPayload) -> Dict[str, Any]:
        """Execute a task assigned to the Self-Healing Agent.
        
        Args:
            task: The task payload
            
        Returns:
            Task execution results
        """
        self.agent_logger.info(f"Executing task: {task.action}")
        
        if task.action == "debug_error":
            error_description = task.params.get("error_description", "")
            code = task.params.get("code", "")
            stack_trace = task.params.get("stack_trace", "")
            return await self.debug_error(error_description, code, stack_trace)
            
        elif task.action == "analyze_failure":
            failure_data = task.params.get("failure_data", {})
            return await self.analyze_failure(failure_data)
            
        elif task.action == "attempt_repair":
            code = task.params.get("code", "")
            fix_suggestion = task.params.get("fix_suggestion", "")
            return await self.attempt_repair(code, fix_suggestion)
            
        elif task.action == "test_code":
            code = task.params.get("code", "")
            name = task.params.get("name", "generated_code")
            return await self.test_code_in_sandbox(code, name)
            
        else:
            return {"status": "error", "message": f"Unknown action: {task.action}"}
    
    async def debug_error(
        self,
        error_description: str,
        code: str = "",
        stack_trace: str = ""
    ) -> Dict[str, Any]:
        """Debug an error and suggest fixes.
        
        Args:
            error_description: Description of the error
            code: Code that caused the error (optional)
            stack_trace: Stack trace (optional)
            
        Returns:
            Debug analysis and suggested fixes
        """
        self.agent_logger.info(f"Debugging error: {error_description[:100]}...")
        
        # Analyze the error
        analysis = await self._analyze_error(error_description, code, stack_trace)
        
        # Store in history
        self._error_history.append({
            "error": error_description,
            "analysis": analysis,
            "timestamp": "now"
        })
        
        # If auto-repairable and confidence is high, attempt repair
        if analysis.auto_repairable and analysis.confidence > 0.8 and code:
            repair_result = await self.attempt_repair(code, analysis.suggested_fix)
            
            return {
                "status": "repaired" if repair_result["success"] else "analysis_only",
                "analysis": {
                    "error_type": analysis.error_type,
                    "root_cause": analysis.root_cause,
                    "severity": analysis.severity.value,
                    "confidence": analysis.confidence
                },
                "suggested_fix": analysis.suggested_fix,
                "auto_repair_attempted": True,
                "repair_result": repair_result
            }
        
        return {
            "status": "analysis_complete",
            "analysis": {
                "error_type": analysis.error_type,
                "root_cause": analysis.root_cause,
                "severity": analysis.severity.value,
                "confidence": analysis.confidence
            },
            "suggested_fix": analysis.suggested_fix,
            "auto_repairable": analysis.auto_repairable,
            "requires_manual_fix": not analysis.auto_repairable
        }
    
    async def _analyze_error(
        self,
        error_description: str,
        code: str,
        stack_trace: str
    ) -> ErrorAnalysis:
        """Analyze an error using LLM.
        
        Args:
            error_description: Error description
            code: Code context
            stack_trace: Stack trace
            
        Returns:
            Error analysis
        """
        context = f"""
Error: {error_description}

Stack Trace:
{stack_trace}

Code Context:
```python
{code}
```
""" if code else f"""
Error: {error_description}

Stack Trace:
{stack_trace}
"""

        prompt = f"""Analyze this error and provide:
1. Error type/classification
2. Root cause explanation
3. Severity level (low/medium/high/critical)
4. Suggested fix
5. Whether this can be auto-repaired (true/false)
6. Confidence in analysis (0.0-1.0)

{context}

Respond with JSON:
{{
    "error_type": "classification",
    "root_cause": "explanation",
    "severity": "low|medium|high|critical",
    "suggested_fix": "detailed fix suggestion",
    "auto_repairable": true|false,
    "confidence": 0.0-1.0
}}"""

        try:
            response = self._bedrock_client.converse(
                modelId=self._config.aws.model_nova_pro,
                messages=[{"role": "user", "content": [{"text": prompt}]}],
                inferenceConfig={"temperature": 0.2, "maxTokens": 1500}
            )
            
            response_text = response['output']['message']['content'][0]['text']
            
            # Parse JSON
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0]
            
            result = json.loads(response_text.strip())
            
            severity_map = {
                "low": ErrorSeverity.LOW,
                "medium": ErrorSeverity.MEDIUM,
                "high": ErrorSeverity.HIGH,
                "critical": ErrorSeverity.CRITICAL
            }
            
            return ErrorAnalysis(
                error_type=result.get("error_type", "Unknown"),
                root_cause=result.get("root_cause", "Unknown"),
                severity=severity_map.get(
                    result.get("severity", "medium"),
                    ErrorSeverity.MEDIUM
                ),
                suggested_fix=result.get("suggested_fix", "No fix suggested"),
                auto_repairable=result.get("auto_repairable", False),
                confidence=result.get("confidence", 0.5)
            )
            
        except Exception as e:
            self.agent_logger.error(f"Error analysis failed: {e}")
            return ErrorAnalysis(
                error_type="Unknown",
                root_cause=f"Analysis failed: {e}",
                severity=ErrorSeverity.MEDIUM,
                suggested_fix="Manual investigation required",
                auto_repairable=False,
                confidence=0.0
            )
    
    async def attempt_repair(self, code: str, fix_suggestion: str) -> Dict[str, Any]:
        """Attempt to automatically repair code.
        
        Args:
            code: Code to repair
            fix_suggestion: Suggested fix from analysis
            
        Returns:
            Repair results
        """
        self.agent_logger.info("Attempting automatic code repair")
        
        prompt = f"""Apply this fix to the code:

Fix to apply:
{fix_suggestion}

Original code:
```python
{code}
```

Provide only the repaired code, no explanations."""

        try:
            response = self._bedrock_client.converse(
                modelId=self._config.aws.model_nova_pro,
                messages=[{"role": "user", "content": [{"text": prompt}]}],
                inferenceConfig={"temperature": 0.2, "maxTokens": 2000}
            )
            
            repaired_code = response['output']['message']['content'][0]['text']
            
            # Extract code
            if "```python" in repaired_code:
                repaired_code = repaired_code.split("```python")[1].split("```")[0]
            elif "```" in repaired_code:
                repaired_code = repaired_code.split("```")[1].split("```")[0]
            
            repaired_code = repaired_code.strip()
            
            # Check if code actually changed
            if repaired_code == code.strip():
                return {
                    "success": False,
                    "message": "Code unchanged - repair may not be applicable",
                    "original_code": code,
                    "repaired_code": repaired_code
                }
            
            return {
                "success": True,
                "message": "Code repaired successfully",
                "original_code": code,
                "repaired_code": repaired_code,
                "changes_made": True
            }
            
        except Exception as e:
            self.agent_logger.error(f"Repair attempt failed: {e}")
            return {
                "success": False,
                "message": f"Repair failed: {e}",
                "original_code": code
            }
    
    async def analyze_failure(self, failure_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze a general system failure.
        
        Args:
            failure_data: Data about the failure
            
        Returns:
            Analysis results
        """
        self.agent_logger.info("Analyzing system failure")
        
        failure_type = failure_data.get("type", "unknown")
        failure_context = failure_data.get("context", {})
        
        # Route to specific handler based on type
        if failure_type == "sandbox_failure":
            return await self.fix_sandbox(failure_context.get("issue", "unknown"))
        elif failure_type == "task_failure":
            return await self.debug_error(
                failure_context.get("error", ""),
                failure_context.get("code", ""),
                failure_context.get("stack_trace", "")
            )
        elif failure_type == "connection_failure":
            return await self._handle_connection_failure(failure_context)
        else:
            return {
                "status": "unknown_failure_type",
                "message": f"Unknown failure type: {failure_type}",
                "suggestion": "Manual investigation required"
            }
    
    async def fix_sandbox(self, issue: str) -> Dict[str, Any]:
        """Fix sandbox environment issues.
        
        Args:
            issue: Description of the sandbox issue
            
        Returns:
            Fix results
        """
        self.agent_logger.info(f"Fixing sandbox issue: {issue}")
        
        # Common sandbox fixes
        fixes = {
            "disk_full": "Clean up temporary files and logs",
            "memory_exceeded": "Restart sandbox with higher memory limit",
            "container_crashed": "Restart container and check health",
            "network_unavailable": "Check network configuration",
            "permission_denied": "Review and fix file permissions"
        }
        
        # Try to match issue
        for key, fix in fixes.items():
            if key in issue.lower():
                return {
                    "status": "identified",
                    "issue": issue,
                    "suggested_fix": fix,
                    "auto_fixable": False,  # Sandbox issues usually need manual action
                    "action_required": "Manual intervention needed"
                }
        
        # If no match, use LLM
        prompt = f"""Suggest a fix for this sandbox/container issue:

Issue: {issue}

Provide a brief diagnosis and fix suggestion."""

        try:
            response = self._bedrock_client.converse(
                modelId=self._config.aws.model_nova_lite,
                messages=[{"role": "user", "content": [{"text": prompt}]}],
                inferenceConfig={"temperature": 0.3, "maxTokens": 500}
            )
            
            suggestion = response['output']['message']['content'][0]['text']
            
            return {
                "status": "analyzed",
                "issue": issue,
                "suggested_fix": suggestion,
                "auto_fixable": False
            }
            
        except Exception as e:
            return {
                "status": "analysis_failed",
                "issue": issue,
                "error": str(e)
            }
    
    async def _handle_connection_failure(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Handle AWS or network connection failures.
        
        Args:
            context: Failure context
            
        Returns:
            Handling results
        """
        service = context.get("service", "unknown")
        error_code = context.get("error_code", "")
        
        self.agent_logger.warning(f"Connection failure to {service}: {error_code}")
        
        # Common AWS connection issues
        if error_code in ["ExpiredToken", "TokenRefreshRequired"]:
            return {
                "status": "identified",
                "issue": "AWS credentials expired",
                "suggested_fix": "Refresh AWS credentials using 'octo setup'",
                "auto_fixable": False
            }
        elif error_code in ["ThrottlingException", "RateExceeded"]:
            return {
                "status": "identified",
                "issue": "AWS API rate limit exceeded",
                "suggested_fix": "Wait and retry with exponential backoff",
                "auto_fixable": True,
                "retry_after": 5  # seconds
            }
        elif error_code in ["ServiceUnavailable", "503"]:
            return {
                "status": "identified",
                "issue": f"{service} temporarily unavailable",
                "suggested_fix": "Retry after a short delay",
                "auto_fixable": True,
                "retry_after": 10
            }
        else:
            return {
                "status": "unknown_connection_error",
                "issue": f"Connection to {service} failed",
                "error_code": error_code,
                "suggested_fix": "Check network connectivity and service status",
                "auto_fixable": False
            }
    
    def _on_message(self, message: OctoMessage) -> None:
        """Handle incoming messages.
        
        Args:
            message: Received message
        """
        super()._on_message(message)
        
        if message.type == MessageType.ERROR:
            # Automatically handle error messages
            self.agent_logger.info(f"Received error from {message.sender}")
            if isinstance(message.payload, ErrorPayload):
                # Could trigger automatic healing here
                pass
    
    async def test_code_in_sandbox(self, code: str, name: str = "generated_code") -> dict:
        """Run generated code in an isolated Docker sandbox.

        Tries EphemeralContainer (Docker) first. Falls back to a restricted
        asyncio subprocess if Docker is not available on this host.

        Args:
            code: Python source code to test
            name: Primitive name (used for logging)

        Returns:
            {passed, stdout, stderr, method, message}
        """
        import os, ast, tempfile

        self.agent_logger.info(f"Testing code in sandbox: {name}")

        # ── Step 0: AST syntax check (instant, zero cost) ──────────────────
        try:
            ast.parse(code)
        except SyntaxError as e:
            return {
                "status":  "error",
                "passed":  False,
                "stdout":  "",
                "stderr":  str(e),
                "method":  "syntax_check",
                "message": f"Syntax error: {e}",
            }

        # ── Step 1: Try Docker (EphemeralContainer) ─────────────────────────
        docker_available = False
        try:
            import asyncio as _aio
            probe = await _aio.create_subprocess_exec(
                "docker", "info",
                stdout=_aio.subprocess.DEVNULL,
                stderr=_aio.subprocess.DEVNULL,
            )
            await probe.wait()
            docker_available = probe.returncode == 0
        except FileNotFoundError:
            docker_available = False

        if docker_available:
            return await self._test_via_docker(code, name)
        else:
            self.agent_logger.warning("Docker not available, falling back to subprocess sandbox")
            return await self._test_via_subprocess(code, name)

    async def _test_via_docker(self, code: str, name: str) -> dict:
        """Execute code inside an EphemeralContainer (Docker)."""
        import tempfile, os
        from src.workers.ephemeral_container import EphemeralContainer, ContainerConfig

        config = ContainerConfig(
            image="python:3.10-slim",
            network_mode="none",       # no outbound network
            memory_limit="256m",
            memory_swap="256m",
            cpu_limit=0.5,
            pids_limit=50,
            read_only=False,           # need to write code file
            execution_timeout=30,
        )
        container = EphemeralContainer(config)

        try:
            created = await container.create()
            if not created:
                self.agent_logger.warning("Docker container creation failed, falling back")
                return await self._test_via_subprocess(code, name)

            # Write code to temp file on host then copy into container
            with tempfile.NamedTemporaryFile(
                suffix=".py", mode="w", delete=False, prefix=f"octopos_{name}_"
            ) as f:
                f.write(code)
                host_path = f.name

            try:
                copied = await container.copy_to(host_path, "/workspace/code.py")
                if not copied:
                    return {"status": "error", "passed": False,
                            "message": "Failed to copy code into container",
                            "method": "docker"}

                result = await container.execute(
                    "python /workspace/code.py",
                    timeout=25,
                )
            finally:
                os.unlink(host_path)

            passed = result.success or result.exit_code == 0
            self.agent_logger.info(
                f"Docker sandbox result for {name}: "
                f"{'PASS' if passed else 'FAIL'} (exit {result.exit_code})"
            )

            return {
                "status":  "success" if passed else "error",
                "passed":  passed,
                "stdout":  result.stdout,
                "stderr":  result.stderr,
                "exit_code": result.exit_code,
                "method":  "docker",
                "message": "Tests passed in Docker sandbox" if passed
                           else f"Tests failed (exit {result.exit_code}): {result.stderr[:300]}",
            }

        finally:
            await container.destroy()

    async def _test_via_subprocess(self, code: str, name: str) -> dict:
        """Fallback: run code in a restricted asyncio subprocess (no network).

        Not as isolated as Docker but still enforces timeout and captures output.
        """
        import asyncio, sys, tempfile, os

        with tempfile.NamedTemporaryFile(
            suffix=".py", mode="w", delete=False, prefix=f"octopos_{name}_"
        ) as f:
            f.write(code)
            path = f.name

        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                # inherit minimal env — no AWS creds, no HOME tricks
                env={"PATH": os.environ.get("PATH", ""), "PYTHONPATH": ""},
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=20
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.communicate()
                return {
                    "status":  "error",
                    "passed":  False,
                    "stdout":  "",
                    "stderr":  "Execution timed out (20s)",
                    "method":  "subprocess",
                    "message": "Code execution timed out",
                }

            passed = proc.returncode == 0
            self.agent_logger.info(
                f"Subprocess sandbox result for {name}: "
                f"{'PASS' if passed else 'FAIL'} (exit {proc.returncode})"
            )

            return {
                "status":  "success" if passed else "error",
                "passed":  passed,
                "stdout":  stdout.decode("utf-8", errors="replace"),
                "stderr":  stderr.decode("utf-8", errors="replace"),
                "exit_code": proc.returncode,
                "method":  "subprocess",
                "message": "Tests passed" if passed
                           else f"Tests failed: {stderr.decode('utf-8', errors='replace')[:300]}",
            }
        finally:
            os.unlink(path)

    async def on_stop(self) -> None:
        """Cleanup on stop."""
        self.agent_logger.info("SelfHealingAgent shutting down")


# Singleton instance
_self_healing_agent: Optional[SelfHealingAgent] = None


def get_self_healing_agent() -> SelfHealingAgent:
    """Get the global SelfHealingAgent instance.
    
    Returns:
        Singleton SelfHealingAgent instance
    """
    global _self_healing_agent
    if _self_healing_agent is None:
        _self_healing_agent = SelfHealingAgent()
    return _self_healing_agent