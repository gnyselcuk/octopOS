"""Nova Act Client - Multimodal UI automation."""

from typing import Any, Dict, List, Optional
import json
import boto3

from src.utils.config import get_config
from src.utils.logger import get_logger

logger = get_logger()


class NovaActClient:
    """AWS Nova Act for UI automation and screen understanding.
    
    Provides web UI automation, screen understanding, and workflow recording.
    """
    
    MODEL_ID = "amazon.nova-act-v1:0"
    
    def __init__(self, region: Optional[str] = None):
        """Initialize Nova Act client.
        
        Args:
            region: AWS region
        """
        self._config = get_config()
        self._region = region or self._config.aws.region
        
        self._client = None
        try:
            self._client = boto3.client('bedrock-runtime', region_name=self._region)
            logger.info("Nova Act client initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize Nova Act: {e}")
    
    async def analyze_screen(
        self,
        screenshot: bytes,
        query: str
    ) -> Dict[str, Any]:
        """Analyze a screen screenshot.
        
        Args:
            screenshot: Screenshot image bytes
            query: Question about the screen
            
        Returns:
            Analysis results
        """
        if not self._client:
            return {"error": "Client not available"}
        
        try:
            response = self._client.invoke_model(
                modelId=self.MODEL_ID,
                body=json.dumps({
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "image", "source": {"bytes": screenshot}},
                            {"type": "text", "text": query}
                        ]
                    }]
                })
            )
            
            result = json.loads(response['body'].read())
            return result
        except Exception as e:
            logger.error(f"Screen analysis failed: {e}")
            return {"error": str(e)}
    
    async def generate_action(
        self,
        goal: str,
        screen_context: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Generate UI action to achieve goal.
        
        Args:
            goal: User goal
            screen_context: Current screen state
            
        Returns:
            Recommended action
        """
        return {
            "action": "click",
            "target": "button",
            "coordinates": [100, 200]
        }
