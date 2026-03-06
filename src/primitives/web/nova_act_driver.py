"""
Nova Act Browser Driver - Enhanced Browser Automation with AWS Nova

This module provides the core integration between Playwright browser automation
and AWS Bedrock Nova's Computer Use capabilities. It implements the
Observe-Act-Verify loop for intelligent browser missions.

Author: octopOS Team
"""

import asyncio
import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
import base64
import mimetypes

import boto3
from botocore.exceptions import ClientError
from playwright.async_api import Page, ElementHandle, Locator, expect

# Internal imports
from .browser_session import SessionManager, get_session_manager, BrowserSnapshot
from ...utils.config import OctoConfig
from ...utils.logger import get_logger

logger = get_logger()


class BrowserAction(Enum):
    """Supported browser actions for Nova Act model."""
    GOTO = "goto"  # Navigate to URL
    CLICK = "click"  # Click on element
    TYPE = "type"  # Type text into input
    SCROLL = "scroll"  # Scroll page
    WAIT = "wait"  # Wait for condition
    EXTRACT = "extract"  # Extract data from page
    SCREENSHOT = "screenshot"  # Take screenshot
    BACK = "back"  # Go back
    FORWARD = "forward"  # Go forward
    REFRESH = "refresh"  # Refresh page
    SELECT = "select"  # Select from dropdown
    HOVER = "hover"  # Hover over element
    PRESS = "press"  # Press key
    TERMINATE = "terminate"  # End mission


@dataclass
class NovaActDecision:
    """Decision from Nova Act model about next browser action."""
    action: BrowserAction
    target: Optional[str] = None  # CSS selector, XPath, or URL
    value: Optional[str] = None  # Text to type, key to press, etc.
    reason: str = ""  # Reasoning for this action
    expected_outcome: str = ""  # What Nova Act expects to happen
    confidence: float = 0.0  # Confidence score (0-1)
    is_final: bool = False  # Whether this is the final step
    extracted_data: Optional[Dict[str, Any]] = None  # Data extracted from page
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "action": self.action.value,
            "target": self.target,
            "value": self.value,
            "reason": self.reason,
            "expected_outcome": self.expected_outcome,
            "confidence": self.confidence,
            "is_final": self.is_final,
            "extracted_data": self.extracted_data
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'NovaActDecision':
        """Create from dictionary."""
        return cls(
            action=BrowserAction(data.get("action", "wait")),
            target=data.get("target"),
            value=data.get("value"),
            reason=data.get("reason", ""),
            expected_outcome=data.get("expected_outcome", ""),
            confidence=data.get("confidence", 0.0),
            is_final=data.get("is_final", False),
            extracted_data=data.get("extracted_data")
        )


@dataclass
class VerificationResult:
    """Result of verifying a browser action."""
    success: bool
    actual_outcome: str
    matches_expected: bool
    screenshot_path: Optional[str] = None
    page_state: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "actual_outcome": self.actual_outcome,
            "matches_expected": self.matches_expected,
            "has_screenshot": self.screenshot_path is not None,
            "error": self.error_message
        }


@dataclass
class MissionStep:
    """A single step in a browser mission."""
    step_number: int
    decision: NovaActDecision
    action_result: Optional[Any] = None
    verification: Optional[VerificationResult] = None
    timestamp: datetime = field(default_factory=datetime.now)
    duration_ms: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_number": self.step_number,
            "decision": self.decision.to_dict(),
            "action_result": str(self.action_result) if self.action_result else None,
            "verification": self.verification.to_dict() if self.verification else None,
            "timestamp": self.timestamp.isoformat(),
            "duration_ms": self.duration_ms
        }


@dataclass
class MissionResult:
    """Result of a completed browser mission."""
    mission_id: str
    success: bool
    steps: List[MissionStep] = field(default_factory=list)
    final_data: Optional[Dict[str, Any]] = None
    reasoning_log: List[str] = field(default_factory=list)
    total_steps: int = 0
    total_duration_ms: float = 0.0
    session_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "success": self.success,
            "total_steps": len(self.steps),
            "total_duration_ms": self.total_duration_ms,
            "final_data": self.final_data,
            "reasoning_log": self.reasoning_log,
            "session_id": self.session_id,
            "steps": [step.to_dict() for step in self.steps]
        }


class NovaActDriver:
    """
    Enhanced browser driver that uses AWS Nova Act for intelligent
    decision-making during browser automation.
    
    Implements the Observe-Act-Verify loop:
    1. OBSERVE: Take screenshot and get page state
    2. ANALYZE: Send to Nova Act model for decision
    3. ACT: Execute the browser action
    4. VERIFY: Check if action achieved expected outcome
    """
    
    def __init__(
        self,
        session_manager: Optional[SessionManager] = None,
        bedrock_client: Optional[Any] = None,
        model_id: str = "amazon.nova-pro-v1:0",
        screenshot_dir: str = "~/.octopos/screenshots",
        max_steps: int = 20,
        config: Optional[OctoConfig] = None
    ):
        """
        Initialize Nova Act Driver.
        
        Args:
            session_manager: Browser session manager instance
            bedrock_client: AWS Bedrock client
            model_id: Nova model ID to use
            screenshot_dir: Directory for mission screenshots
            max_steps: Maximum steps per mission
            config: OctoConfig instance
        """
        self.session_manager = session_manager or get_session_manager()
        self.bedrock_client = bedrock_client or boto3.client("bedrock-runtime", region_name="us-east-1")
        self.model_id = model_id
        self.screenshot_dir = Path(screenshot_dir).expanduser()
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        self.max_steps = max_steps
        self.config = config or OctoConfig()
        
        # Track active missions
        self._active_missions: Dict[str, MissionResult] = {}
        
        logger.info(f"NovaActDriver initialized with model: {model_id}")
    
    async def observe(
        self,
        session_id: str,
        mission_context: str = "",
        previous_actions: List[Dict] = None
    ) -> Tuple[BrowserSnapshot, str]:
        """
        OBSERVE: Capture current browser state and prepare for Nova Act.
        
        Args:
            session_id: Active browser session
            mission_context: Current mission context/objective
            previous_actions: History of previous actions and results
            
        Returns:
            Tuple of (BrowserSnapshot, prompt_for_nova)
        """
        # Take snapshot
        snapshot = await self.session_manager.take_snapshot(
            session_id,
            screenshot_dir=str(self.screenshot_dir)
        )
        
        if not snapshot:
            raise RuntimeError(f"Failed to capture snapshot for session {session_id}")
        
        # Build observation prompt
        observation = self._build_observation_prompt(snapshot, mission_context, previous_actions)
        
        return snapshot, observation
    
    def _build_observation_prompt(
        self,
        snapshot: BrowserSnapshot,
        mission_context: str,
        previous_actions: List[Dict] = None
    ) -> str:
        """Build the observation prompt for Nova Act."""
        
        prompt_parts = [
            "=== BROWSER OBSERVATION ===",
            f"Current URL: {snapshot.url}",
            f"Page Title: {snapshot.title}",
            f"Viewport: {snapshot.viewport_width}x{snapshot.viewport_height}",
            f"Scroll Position: {snapshot.scroll_position}",
            "",
            "=== MISSION CONTEXT ===",
            mission_context,
            ""
        ]
        
        if previous_actions:
            prompt_parts.extend([
                "=== PREVIOUS ACTIONS ===",
                json.dumps(previous_actions[-5:], indent=2),  # Last 5 actions
                ""
            ])
        
        prompt_parts.extend([
            "=== PAGE CONTENT (truncated) ===",
            snapshot.html[:8000] if len(snapshot.html) > 8000 else snapshot.html,
            "",
            "=== AVAILABLE ACTIONS ===",
            "- goto: Navigate to URL",
            "- click: Click element (provide selector)",
            "- type: Type text (provide selector and value)",
            "- scroll: Scroll page",
            "- wait: Wait for condition",
            "- extract: Extract data from page",
            "- screenshot: Take screenshot",
            "- back/forward/refresh: Navigation",
            "- select: Select from dropdown",
            "- hover: Hover over element",
            "- press: Press key",
            "- terminate: End mission (success or failure)",
            "",
            "=== INSTRUCTIONS ===",
            "Analyze the current browser state and decide the NEXT action.",
            "Respond with a JSON object containing:",
            "- action: One of the available actions",
            "- target: CSS selector, XPath, or URL (if applicable)",
            "- value: Text to type or key to press (if applicable)",
            "- reason: Your reasoning for this action",
            "- expected_outcome: What you expect to happen",
            "- confidence: Your confidence (0.0-1.0)",
            "- is_final: true if this completes the mission",
            "- extracted_data: Any data you extracted (if applicable)"
        ])
        
        return "\n".join(prompt_parts)
    
    async def analyze(self, observation: str, screenshot_path: Optional[str] = None) -> NovaActDecision:
        """
        ANALYZE: Send observation to Nova Act and get decision.
        
        Args:
            observation: The observation prompt
            screenshot_path: Path to screenshot for multimodal analysis
            
        Returns:
            NovaActDecision with next action
        """
        try:
            # Build messages for Nova model
            messages = [{"role": "user", "content": []}]
            
            # Add text content
            messages[0]["content"].append({
                "text": observation
            })
            
            # Add screenshot if available (multimodal)
            if screenshot_path and os.path.exists(screenshot_path):
                # Bedrock converse format expects image directly
                ext = os.path.splitext(screenshot_path)[1].lower().replace('.', '')
                if ext == 'jpg': ext = 'jpeg'
                
                with open(screenshot_path, "rb") as f:
                    image_bytes = f.read()
                
                messages[0]["content"].append({
                    "image": {
                        "format": ext,
                        "source": {
                            "bytes": image_bytes
                        }
                    }
                })
            
            # Call Nova Act model
            response = self.bedrock_client.converse(
                modelId=self.model_id,
                messages=messages,
                inferenceConfig={
                    "maxTokens": 4096,
                    "temperature": 0.3,
                    "topP": 0.9
                }
            )
            
            # Parse response
            content = response["output"]["message"]["content"]
            text_response = content[0]["text"] if content else ""
            
            # Try to parse JSON from response
            decision = self._parse_decision(text_response)
            
            logger.info(
                f"Nova Act decision: {decision.action.value} "
                f"(confidence: {decision.confidence:.2f})"
            )
            
            return decision
            
        except ClientError as e:
            logger.error(f"AWS Bedrock error: {e}")
            # Fallback: return wait action
            return NovaActDecision(
                action=BrowserAction.WAIT,
                reason=f"Error calling Nova Act: {str(e)}",
                confidence=0.0
            )
        except Exception as e:
            logger.error(f"Error analyzing with Nova Act: {e}")
            return NovaActDecision(
                action=BrowserAction.WAIT,
                reason=f"Error: {str(e)}",
                confidence=0.0
            )
    
    def _parse_decision(self, text_response: str) -> NovaActDecision:
        """Parse Nova Act response into decision."""
        try:
            # Try to find JSON in the response
            import re
            json_match = re.search(r'\{.*\}', text_response, re.DOTALL)
            
            if json_match:
                json_str = json_match.group()
                data = json.loads(json_str)
                
                return NovaActDecision(
                    action=BrowserAction(data.get("action", "wait")),
                    target=data.get("target"),
                    value=data.get("value"),
                    reason=data.get("reason", ""),
                    expected_outcome=data.get("expected_outcome", ""),
                    confidence=data.get("confidence", 0.5),
                    is_final=data.get("is_final", False),
                    extracted_data=data.get("extracted_data")
                )
            else:
                # Fallback: try to parse entire response as JSON
                data = json.loads(text_response)
                return NovaActDecision(
                    action=BrowserAction(data.get("action", "wait")),
                    target=data.get("target"),
                    value=data.get("value"),
                    reason=data.get("reason", ""),
                    expected_outcome=data.get("expected_outcome", ""),
                    confidence=data.get("confidence", 0.5),
                    is_final=data.get("is_final", False),
                    extracted_data=data.get("extracted_data")
                )
                
        except json.JSONDecodeError:
            # If no valid JSON, try to infer from text
            text_lower = text_response.lower()
            
            if "click" in text_lower:
                return NovaActDecision(
                    action=BrowserAction.CLICK,
                    reason=text_response[:500]
                )
            elif "type" in text_lower or "enter" in text_lower:
                return NovaActDecision(
                    action=BrowserAction.TYPE,
                    reason=text_response[:500]
                )
            elif "goto" in text_lower or "navigate" in text_lower or "http" in text_lower:
                return NovaActDecision(
                    action=BrowserAction.GOTO,
                    reason=text_response[:500]
                )
            elif "extract" in text_lower or "found" in text_lower:
                return NovaActDecision(
                    action=BrowserAction.EXTRACT,
                    is_final=True,
                    reason=text_response[:500]
                )
            elif "complete" in text_lower or "done" in text_lower:
                return NovaActDecision(
                    action=BrowserAction.TERMINATE,
                    is_final=True,
                    reason=text_response[:500]
                )
            else:
                return NovaActDecision(
                    action=BrowserAction.WAIT,
                    reason=f"Could not parse decision from: {text_response[:500]}",
                    confidence=0.0
                )
    
    async def act(self, session_id: str, decision: NovaActDecision) -> Any:
        """
        ACT: Execute the browser action decided by Nova Act.
        
        Args:
            session_id: Active browser session
            decision: NovaActDecision to execute
            
        Returns:
            Result of the action
        """
        page = await self.session_manager.get_page(session_id)
        if not page:
            raise RuntimeError(f"No active page for session {session_id}")
        
        action = decision.action
        target = decision.target
        value = decision.value
        
        try:
            if action == BrowserAction.GOTO:
                if not target:
                    raise ValueError("GOTO action requires target URL")
                result = await page.goto(target, wait_until="networkidle")
                return {"url": page.url, "title": await page.title()}
            
            elif action == BrowserAction.CLICK:
                if not target:
                    raise ValueError("CLICK action requires target selector")
                element = await page.wait_for_selector(target, timeout=self.config.browser.timeout // 2)
                if element:
                    await element.click()
                    return {"clicked": target, "success": True}
                return {"clicked": target, "success": False, "error": "Element not found"}
            
            elif action == BrowserAction.TYPE:
                if not target or value is None:
                    raise ValueError("TYPE action requires target and value")
                element = await page.wait_for_selector(target, timeout=self.config.browser.timeout // 2)
                if element:
                    await element.fill(value)
                    return {"typed": value, "into": target, "success": True}
                return {"typed": value, "into": target, "success": False, "error": "Element not found"}
            
            elif action == BrowserAction.SCROLL:
                direction = value or "down"
                amount = 500
                if direction == "down":
                    await page.evaluate(f"window.scrollBy(0, {amount})")
                elif direction == "up":
                    await page.evaluate(f"window.scrollBy(0, -{amount})")
                elif direction == "bottom":
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                elif direction == "top":
                    await page.evaluate("window.scrollTo(0, 0)")
                return {"scrolled": direction, "success": True}
            
            elif action == BrowserAction.WAIT:
                wait_time = int(value) if value and value.isdigit() else 1000
                await page.wait_for_timeout(wait_time)
                return {"waited_ms": wait_time}
            
            elif action == BrowserAction.EXTRACT:
                # Extract data based on selector
                if target:
                    elements = await page.query_selector_all(target)
                    texts = []
                    for el in elements[:20]:  # Limit to 20 elements
                        text = await el.text_content()
                        if text:
                            texts.append(text.strip())
                    return {"extracted": texts, "selector": target}
                else:
                    # Extract all text
                    body_text = await page.text_content("body")
                    return {"extracted": body_text[:5000] if body_text else ""}
            
            elif action == BrowserAction.SCREENSHOT:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                path = str(self.screenshot_dir / f"manual_{session_id}_{timestamp}.png")
                await page.screenshot(path=path, full_page=True)
                return {"screenshot_path": path}
            
            elif action == BrowserAction.BACK:
                await page.go_back()
                return {"navigated": "back", "url": page.url}
            
            elif action == BrowserAction.FORWARD:
                await page.go_forward()
                return {"navigated": "forward", "url": page.url}
            
            elif action == BrowserAction.REFRESH:
                await page.reload()
                return {"refreshed": True, "url": page.url}
            
            elif action == BrowserAction.SELECT:
                if not target or not value:
                    raise ValueError("SELECT action requires target and value")
                element = await page.wait_for_selector(target, timeout=self.config.browser.timeout // 2)
                if element:
                    await element.select_option(value)
                    return {"selected": value, "success": True}
                return {"selected": value, "success": False, "error": "Element not found"}
            
            elif action == BrowserAction.HOVER:
                if not target:
                    raise ValueError("HOVER action requires target selector")
                element = await page.wait_for_selector(target, timeout=self.config.browser.timeout // 2)
                if element:
                    await element.hover()
                    return {"hovered": target, "success": True}
                return {"hovered": target, "success": False, "error": "Element not found"}
            
            elif action == BrowserAction.PRESS:
                if not value:
                    raise ValueError("PRESS action requires value (key name)")
                await page.keyboard.press(value)
                return {"pressed": value}
            
            elif action == BrowserAction.TERMINATE:
                return {"terminated": True, "final": True}
            
            else:
                return {"error": f"Unknown action: {action.value}"}
                
        except Exception as e:
            logger.error(f"Action {action.value} failed: {e}")
            return {"error": str(e), "action": action.value, "success": False}
    
    async def verify(
        self,
        session_id: str,
        decision: NovaActDecision,
        action_result: Any,
        pre_snapshot: BrowserSnapshot
    ) -> VerificationResult:
        """
        VERIFY: Check if action achieved expected outcome.
        
        Args:
            session_id: Active browser session
            decision: The decision that was executed
            action_result: Result from the act() method
            pre_snapshot: Snapshot before the action
            
        Returns:
            VerificationResult
        """
        # Take new snapshot
        post_snapshot = await self.session_manager.take_snapshot(
            session_id,
            screenshot_dir=str(self.screenshot_dir)
        )
        
        if not post_snapshot:
            return VerificationResult(
                success=False,
                actual_outcome="Failed to capture post-action snapshot",
                matches_expected=False,
                error_message="Snapshot failed"
            )
        
        # Basic verification logic
        success = True
        actual_outcome = ""
        matches_expected = True
        error_message = None
        
        # Check for action errors
        if isinstance(action_result, dict):
            if "error" in action_result:
                success = False
                error_message = action_result["error"]
                actual_outcome = f"Action failed: {error_message}"
            elif action_result.get("success") is False:
                success = False
                actual_outcome = f"Action did not succeed: {action_result}"
            else:
                # Action executed without errors
                actual_outcome = f"Action completed: {action_result}"
        
        # Check URL change for navigation actions
        if decision.action in [BrowserAction.GOTO, BrowserAction.BACK, BrowserAction.FORWARD]:
            if post_snapshot.url != pre_snapshot.url:
                actual_outcome += f" | Navigated to: {post_snapshot.url}"
            elif decision.action == BrowserAction.GOTO:
                success = False
                actual_outcome += " | Navigation may have failed (URL unchanged)"
        
        # For terminate action, always mark as success
        if decision.action == BrowserAction.TERMINATE:
            success = True
            actual_outcome = "Mission terminated"
        
        return VerificationResult(
            success=success,
            actual_outcome=actual_outcome,
            matches_expected=matches_expected,  # Could be enhanced with Nova Act verification
            screenshot_path=post_snapshot.screenshot_path,
            page_state=post_snapshot.to_dict(),
            error_message=error_message
        )
    
    async def execute_step(
        self,
        session_id: str,
        mission_context: str,
        previous_steps: List[MissionStep] = None
    ) -> MissionStep:
        """
        Execute a single Observe-Act-Verify step.
        
        Args:
            session_id: Active browser session
            mission_context: Mission objective
            previous_steps: Previous steps in this mission
            
        Returns:
            MissionStep with full results
        """
        start_time = asyncio.get_event_loop().time()
        
        # OBSERVE
        previous_actions = [step.to_dict() for step in (previous_steps or [])]
        snapshot, observation = await self.observe(
            session_id,
            mission_context,
            previous_actions
        )
        
        # ANALYZE
        decision = await self.analyze(observation, snapshot.screenshot_path)
        
        # ACT
        action_result = await self.act(session_id, decision)
        
        # VERIFY
        verification = await self.verify(session_id, decision, action_result, snapshot)
        
        duration = (asyncio.get_event_loop().time() - start_time) * 1000
        
        step = MissionStep(
            step_number=len(previous_steps or []) + 1,
            decision=decision,
            action_result=action_result,
            verification=verification,
            duration_ms=duration
        )
        
        logger.info(
            f"Step {step.step_number}: {decision.action.value} "
            f"({duration:.0f}ms, success={verification.success})"
        )
        
        return step
    
    async def run_mission(
        self,
        mission_id: str,
        initial_url: str,
        mission_context: str,
        user_id: str = "default",
        session_id: str = None,
        max_steps: int = None
    ) -> MissionResult:
        """
        Run a complete browser mission using the Observe-Act-Verify loop.
        
        Args:
            mission_id: Unique mission identifier
            initial_url: Starting URL
            mission_context: Mission objective and context
            user_id: User identifier for session grouping
            session_id: Existing session ID (or create new)
            max_steps: Override max steps for this mission
            
        Returns:
            MissionResult with full mission history
        """
        max_steps = max_steps or self.max_steps
        
        # Create or reuse session
        if not session_id:
            session = await self.session_manager.create_session(
                user_id=user_id,
                mission_id=mission_id,
                metadata={"mission_context": mission_context}
            )
            session_id = session.session_id
        
        result = MissionResult(
            mission_id=mission_id,
            success=False,
            session_id=session_id
        )
        
        self._active_missions[mission_id] = result
        
        try:
            # Navigate to initial URL
            page = await self.session_manager.get_page(session_id)
            await page.goto(initial_url, wait_until="networkidle")
            
            # Execute steps
            for step_num in range(max_steps):
                step = await self.execute_step(
                    session_id,
                    mission_context,
                    result.steps
                )
                
                result.steps.append(step)
                result.reasoning_log.append(step.decision.reason)
                
                # Check for termination
                if step.decision.is_final or step.decision.action == BrowserAction.TERMINATE:
                    result.success = step.verification.success if step.verification else True
                    result.final_data = step.decision.extracted_data
                    break
                
                # Check for repeated failures
                if step_num > 3:
                    recent_failures = sum(
                        1 for s in result.steps[-3:]
                        if not s.verification.success
                    )
                    if recent_failures >= 3:
                        result.success = False
                        result.reasoning_log.append(
                            f"Mission aborted after {recent_failures} consecutive failures"
                        )
                        break
            else:
                # Max steps reached
                result.success = False
                result.reasoning_log.append(f"Mission reached max steps ({max_steps})")
            
            # Calculate total duration
            result.total_duration_ms = sum(s.duration_ms for s in result.steps)
            
        except Exception as e:
            logger.error(f"Mission {mission_id} failed: {e}")
            result.success = False
            result.reasoning_log.append(f"Exception: {str(e)}")
        
        finally:
            # Save session state
            await self.session_manager.save_session_state(session_id)
            del self._active_missions[mission_id]
        
        return result
    
    def get_active_mission(self, mission_id: str) -> Optional[MissionResult]:
        """Get currently running mission."""
        return self._active_missions.get(mission_id)
    
    async def abort_mission(self, mission_id: str) -> bool:
        """Abort a running mission."""
        if mission_id in self._active_missions:
            result = self._active_missions[mission_id]
            result.success = False
            result.reasoning_log.append("Mission aborted by user/system")
            del self._active_missions[mission_id]
            return True
        return False


# Global driver instance
_global_driver: Optional[NovaActDriver] = None


def get_nova_act_driver(
    session_manager: Optional[SessionManager] = None,
    config: Optional[OctoConfig] = None
) -> NovaActDriver:
    """Get or create global Nova Act Driver."""
    global _global_driver
    if _global_driver is None:
        cfg = config or OctoConfig()
        _global_driver = NovaActDriver(
            session_manager=session_manager,
            model_id=cfg.browser.nova_act_model,
            screenshot_dir=cfg.browser.profile_dir,
            max_steps=cfg.browser.max_steps_per_mission,
            config=cfg
        )
    return _global_driver
