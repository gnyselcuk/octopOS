"""Integration Hooks - Connect new components to existing system.

Integrates ManagerAgent, TokenBudget, SemanticCache, DLQ, CloudWatch
with existing Orchestrator and BaseAgent.
"""

from typing import Any, Dict, Optional
import functools

from src.engine.base_agent import BaseAgent
from src.engine.orchestrator import Orchestrator
from src.engine.message import OctoMessage, TaskPayload, MessageType
from src.engine.dead_letter_queue import get_dead_letter_queue
from src.engine.memory.semantic_cache import get_semantic_cache
from src.specialist.manager_agent import get_manager_agent
from src.utils.token_budget import get_token_budget_manager
from src.utils.cloudwatch_logger import CloudWatchLogger
from src.utils.bedrock_guardrails import BedrockGuardrails
from src.utils.logger import get_logger

logger = get_logger()


class IntegrationHooks:
    """Hooks for integrating new components into existing agents.
    
    Provides decorators and utility functions to wire up:
    - Token Budget tracking
    - Semantic Caching
    - Dead Letter Queue
    - CloudWatch Logging
    - Manager Agent coordination
    """
    
    def __init__(self):
        self._token_budget = get_token_budget_manager()
        self._semantic_cache = get_semantic_cache()
        self._dlq = get_dead_letter_queue()
        self._cloudwatch = CloudWatchLogger()
        self._guardrails = BedrockGuardrails()
        self._manager = get_manager_agent()
        
        self._initialized = False
    
    async def initialize(self):
        """Initialize all integrated components."""
        await self._semantic_cache.initialize()
        await self._manager.start()
        self._initialized = True
        logger.info("Integration hooks initialized")
    
    def track_tokens(self, model: str, session_id: str = "default"):
        """Decorator to track token usage for a function.
        
        Args:
            model: Model name for pricing
            session_id: Session identifier
        """
        def decorator(func):
            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                # Create budget if not exists
                budget = self._token_budget.get_budget(session_id)
                if not budget:
                    budget = self._token_budget.create_budget(
                        session_id=session_id,
                        user_id="system"
                    )
                
                # Check budget before call
                if budget.stopped:
                    logger.error(f"Budget exceeded for session {session_id}")
                    return {"error": "budget_exceeded", "budget_status": budget.get_summary()}
                
                # Execute function
                result = await func(*args, **kwargs)
                
                # Track usage if result contains token info
                if isinstance(result, dict):
                    prompt_tokens = result.get("prompt_tokens", 0)
                    completion_tokens = result.get("completion_tokens", 0)
                    
                    if prompt_tokens or completion_tokens:
                        status = self._token_budget.record_usage(
                            session_id=session_id,
                            model=model,
                            prompt_tokens=prompt_tokens,
                            completion_tokens=completion_tokens
                        )
                        
                        if not status["allowed"]:
                            logger.warning(f"Budget limit reached: {status}")
                        
                        # Add budget info to result
                        result["_budget_status"] = status
                
                return result
            return wrapper
        return decorator
    
    def with_cache(self, cache_key_func=None):
        """Decorator to add semantic caching to a function.
        
        Args:
            cache_key_func: Function to generate cache key from args
        """
        def decorator(func):
            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                # Generate cache key
                if cache_key_func:
                    key = cache_key_func(*args, **kwargs)
                else:
                    key = str(args) + str(kwargs)
                
                # Try cache
                cached = await self._semantic_cache.get(key)
                if cached:
                    logger.debug(f"Cache hit for {func.__name__}")
                    return {"response": cached, "cached": True}
                
                # Execute and cache
                result = await func(*args, **kwargs)
                
                if isinstance(result, dict) and "response" in result:
                    await self._semantic_cache.set(key, result["response"])
                elif isinstance(result, str):
                    await self._semantic_cache.set(key, result)
                
                return result
            return wrapper
        return decorator
    
    def with_dlq(self, agent_name: str):
        """Decorator to add Dead Letter Queue handling.
        
        Args:
            agent_name: Name of the agent for DLQ tracking
        """
        def decorator(func):
            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    logger.error(f"Function {func.__name__} failed: {e}")
                    
                    # Try to extract message from args
                    message = None
                    for arg in args:
                        if isinstance(arg, OctoMessage):
                            message = arg
                            break
                    
                    if message:
                        self._dlq.add(
                            message=message,
                            error_type=type(e).__name__,
                            error_message=str(e),
                            agent_name=agent_name
                        )
                    
                    raise
            return wrapper
        return decorator
    
    def with_cloudwatch(self, metric_name: str = None):
        """Decorator to log metrics to CloudWatch.
        
        Args:
            metric_name: Custom metric name
        """
        def decorator(func):
            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                import time
                start = time.time()
                
                try:
                    result = await func(*args, **kwargs)
                    duration = time.time() - start
                    
                    # Log success metric
                    name = metric_name or f"{func.__name__}_success"
                    self._cloudwatch.put_metric(
                        metric_name=name,
                        value=1,
                        dimensions={"function": func.__name__}
                    )
                    
                    # Log duration
                    self._cloudwatch.put_metric(
                        metric_name=f"{func.__name__}_duration",
                        value=duration,
                        unit="Seconds"
                    )
                    
                    return result
                    
                except Exception as e:
                    # Log failure metric
                    name = metric_name or f"{func.__name__}_failure"
                    self._cloudwatch.put_metric(
                        metric_name=name,
                        value=1,
                        dimensions={"function": func.__name__, "error": type(e).__name__}
                    )
                    raise
            return wrapper
        return decorator
    
    def with_guardrails(self, source: str = "INPUT"):
        """Decorator to apply Bedrock Guardrails.
        
        Args:
            source: "INPUT" or "OUTPUT"
        """
        def decorator(func):
            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                # Filter input if it's the first string arg
                if source == "INPUT" and args:
                    for i, arg in enumerate(args):
                        if isinstance(arg, str):
                            filtered = self._guardrails.filter_input(arg)
                            args = list(args)
                            args[i] = filtered
                            args = tuple(args)
                            break
                
                # Execute
                result = await func(*args, **kwargs)
                
                # Filter output if it's a string or dict with content
                if source == "OUTPUT":
                    if isinstance(result, str):
                        result = self._guardrails.filter_output(result)
                    elif isinstance(result, dict) and "content" in result:
                        result["content"] = self._guardrails.filter_output(result["content"])
                
                return result
            return wrapper
        return decorator


# Singleton
_hooks_instance: Optional[IntegrationHooks] = None


def get_integration_hooks() -> IntegrationHooks:
    """Get singleton IntegrationHooks."""
    global _hooks_instance
    if _hooks_instance is None:
        _hooks_instance = IntegrationHooks()
    return _hooks_instance


# Convenience decorators

def track_tokens(model: str, session_id: str = "default"):
    """Decorator to track token usage."""
    return get_integration_hooks().track_tokens(model, session_id)


def with_cache(cache_key_func=None):
    """Decorator to add semantic caching."""
    return get_integration_hooks().with_cache(cache_key_func)


def with_dlq(agent_name: str):
    """Decorator to add DLQ handling."""
    return get_integration_hooks().with_dlq(agent_name)


def with_cloudwatch(metric_name: str = None):
    """Decorator to log CloudWatch metrics."""
    return get_integration_hooks().with_cloudwatch(metric_name)


def with_guardrails(source: str = "INPUT"):
    """Decorator to apply Bedrock Guardrails."""
    return get_integration_hooks().with_guardrails(source)
