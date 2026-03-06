"""Bedrock Invoker - AWS Bedrock model invocation primitive.

Provides Bedrock foundation model operations including text generation
and conversational AI.

Example:
    >>> from src.primitives.cloud_aws.bedrock_invoker import BedrockInvoker
    >>> invoker = BedrockInvoker()
    >>> result = await invoker.execute(
    ...     prompt="What is the capital of France?",
    ...     model_id="amazon.nova-lite-v1:0"
    ... )
"""

from typing import Any, Dict, List, Optional
from enum import Enum

from src.primitives.base_primitive import BasePrimitive, PrimitiveResult, register_primitive
from src.utils.aws_sts import get_bedrock_client
from src.utils.config import get_config
from src.utils.logger import get_logger

logger = get_logger()


class BedrockOperation(str, Enum):
    """Bedrock operation types."""
    CONVERSE = "converse"
    GENERATE = "generate"


class BedrockInvoker(BasePrimitive):
    """Invoke AWS Bedrock foundation models.
    
    Provides Bedrock model interaction:
    - Text generation with various models
    - Conversational AI with message history
    - Support for Nova, Claude, Llama models
    """
    
    # Supported models
    DEFAULT_MODEL = "amazon.nova-lite-v1:0"
    SUPPORTED_MODELS = [
        "amazon.nova-lite-v1:0",
        "amazon.nova-pro-v1:0",
        "amazon.nova-micro-v1:0",
        "anthropic.claude-3-5-sonnet-20241022-v2:0",
        "anthropic.claude-3-sonnet-20240229-v1:0",
        "anthropic.claude-3-haiku-20240307-v1:0",
        "meta.llama3-70b-instruct-v1:0",
        "meta.llama3-8b-instruct-v1:0",
    ]
    
    def __init__(self) -> None:
        """Initialize Bedrock Invoker."""
        super().__init__()
        self._client = None
    
    @property
    def name(self) -> str:
        return "bedrock_invoke"
    
    @property
    def description(self) -> str:
        return (
            "Invoke AWS Bedrock foundation models for text generation. "
            "Supports Amazon Nova, Claude, Llama models with configurable "
            "parameters like temperature and max tokens."
        )
    
    @property
    def parameters(self) -> Dict[str, Dict[str, Any]]:
        return {
            "operation": {
                "type": "string",
                "description": "Operation type: converse or generate",
                "required": False,
                "default": "converse",
                "enum": [op.value for op in BedrockOperation]
            },
            "prompt": {
                "type": "string",
                "description": "Input prompt text",
                "required": True
            },
            "model_id": {
                "type": "string",
                "description": "Bedrock model ID",
                "required": False,
                "default": "amazon.nova-lite-v1:0"
            },
            "max_tokens": {
                "type": "integer",
                "description": "Maximum tokens to generate",
                "required": False,
                "default": 500
            },
            "temperature": {
                "type": "number",
                "description": "Sampling temperature (0-1)",
                "required": False,
                "default": 0.7
            },
            "top_p": {
                "type": "number",
                "description": "Top-p sampling",
                "required": False,
                "default": 0.9
            },
            "system_prompt": {
                "type": "string",
                "description": "System prompt for conversation",
                "required": False
            },
            "conversation_history": {
                "type": "array",
                "description": "List of previous messages [{role, content}]",
                "required": False
            }
        }
    
    def _get_client(self):
        """Get or create Bedrock client."""
        if self._client is None:
            self._client = get_bedrock_client()
        return self._client
    
    async def execute(self, **kwargs) -> PrimitiveResult:
        """Execute Bedrock invocation.
        
        Args:
            operation: BedrockOperation type
            prompt: Input prompt
            model_id: Model identifier
            max_tokens: Max tokens to generate
            temperature: Sampling temperature
            top_p: Top-p sampling
            system_prompt: System instructions
            conversation_history: Previous messages
            
        Returns:
            PrimitiveResult with model response
        """
        operation_str = kwargs.get("operation", "converse")
        prompt = kwargs.get("prompt", "")
        model_id = kwargs.get("model_id", self.DEFAULT_MODEL)
        max_tokens = kwargs.get("max_tokens", 500)
        temperature = kwargs.get("temperature", 0.7)
        top_p = kwargs.get("top_p", 0.9)
        system_prompt = kwargs.get("system_prompt")
        conversation_history = kwargs.get("conversation_history", [])
        
        if not prompt:
            return PrimitiveResult(
                success=False,
                data=None,
                message="Missing required parameter: prompt",
                error="MissingParameters"
            )
        
        # Validate model
        if model_id not in self.SUPPORTED_MODELS:
            logger.warning(f"Model {model_id} not in known supported list, attempting anyway")
        
        try:
            client = self._get_client()
            
            # Build messages
            messages = []
            
            # Add conversation history
            for msg in conversation_history:
                messages.append({
                    "role": msg.get("role", "user"),
                    "content": [{"text": msg.get("content", "")}]
                })
            
            # Add current prompt
            messages.append({
                "role": "user",
                "content": [{"text": prompt}]
            })
            
            # Build inference config
            inference_config = {
                "maxTokens": max_tokens,
                "temperature": temperature,
                "topP": top_p
            }
            
            # Build request
            request = {
                "modelId": model_id,
                "messages": messages,
                "inferenceConfig": inference_config
            }
            
            # Add system prompt if provided
            if system_prompt:
                request["system"] = [{"text": system_prompt}]
            
            # Invoke model
            response = client.converse(**request)
            
            # Extract response text
            output_message = response.get('output', {}).get('message', {})
            content = output_message.get('content', [])
            
            response_text = ""
            if content and len(content) > 0:
                response_text = content[0].get('text', '')
            
            # Extract usage
            usage = response.get('usage', {})
            
            return PrimitiveResult(
                success=True,
                data={
                    "response": response_text,
                    "model": model_id,
                    "usage": {
                        "input_tokens": usage.get('inputTokens', 0),
                        "output_tokens": usage.get('outputTokens', 0),
                        "total_tokens": usage.get('totalTokens', 0)
                    }
                },
                message=f"Successfully invoked {model_id}",
                metadata={
                    "stop_reason": response.get('stopReason')
                }
            )
            
        except Exception as e:
            logger.error(f"Bedrock invocation error: {e}")
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"Invocation failed: {e}",
                error=str(e)
            )


def register_all() -> None:
    """Register Bedrock primitives."""
    register_primitive(BedrockInvoker())
