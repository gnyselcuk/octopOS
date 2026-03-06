"""Bedrock Guardrails Integration - Content filtering and safety."""

from typing import Any, Dict, List, Optional
import json
import boto3
from botocore.exceptions import ClientError

from src.utils.config import get_config
from src.utils.logger import get_logger

logger = get_logger()


class BedrockGuardrails:
    """AWS Bedrock Guardrails integration for content safety.
    
    Provides content filtering, PII detection, and topic controls
    for Bedrock model invocations.
    """
    
    def __init__(
        self,
        guardrail_id: Optional[str] = None,
        guardrail_version: str = "DRAFT",
        region: Optional[str] = None
    ):
        """Initialize Guardrails.
        
        Args:
            guardrail_id: Guardrail ID from AWS
            guardrail_version: Guardrail version
            region: AWS region
        """
        self._config = get_config()
        self._region = region or self._config.aws.region
        
        self._guardrail_id = guardrail_id or getattr(self._config.aws, 'guardrail_id', None)
        self._guardrail_version = guardrail_version
        
        self._client = None
        try:
            self._client = boto3.client('bedrock-runtime', region_name=self._region)
            logger.info("Bedrock Guardrails initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize Guardrails: {e}")
    
    def apply_guardrails(
        self,
        content: str,
        source: str = "INPUT"  # INPUT or OUTPUT
    ) -> Dict[str, Any]:
        """Apply guardrails to content.
        
        Args:
            content: Content to check
            source: Content source (INPUT/OUTPUT)
            
        Returns:
            Guardrails result
        """
        if not self._client or not self._guardrail_id:
            # Pass through if not configured
            return {
                "action": "NONE",
                "outputs": [{"text": content}],
                "assessments": []
            }
        
        try:
            response = self._client.apply_guardrail(
                guardrailIdentifier=self._guardrail_id,
                guardrailVersion=self._guardrail_version,
                content=[{
                    "text": {
                        "text": content
                    }
                }],
                source=source
            )
            
            action = response.get("action", "NONE")
            
            if action == "GUARDRAIL_INTERVENED":
                logger.warning(f"Guardrails intervened on {source}")
                outputs = response.get("outputs", [])
                if outputs:
                    return {
                        "action": action,
                        "content": outputs[0].get("text", content),
                        "assessments": response.get("assessments", [])
                    }
            
            return {
                "action": action,
                "content": content,
                "assessments": response.get("assessments", [])
            }
            
        except Exception as e:
            logger.error(f"Guardrails check failed: {e}")
            return {
                "action": "ERROR",
                "content": content,
                "error": str(e)
            }
    
    def filter_input(self, prompt: str) -> str:
        """Filter user input through guardrails.
        
        Args:
            prompt: User prompt
            
        Returns:
            Filtered prompt
        """
        result = self.apply_guardrails(prompt, "INPUT")
        return result.get("content", prompt)
    
    def filter_output(self, response: str) -> str:
        """Filter model output through guardrails.
        
        Args:
            response: Model response
            
        Returns:
            Filtered response
        """
        result = self.apply_guardrails(response, "OUTPUT")
        return result.get("content", response)
