"""Screen Analysis - Screen content understanding."""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass

from src.interfaces.ui.nova_act import NovaActClient
from src.utils.logger import get_logger

logger = get_logger()


@dataclass
class UIElement:
    """A detected UI element."""
    type: str
    text: Optional[str]
    coordinates: tuple
    confidence: float


class ScreenAnalyzer:
    """Analyze screen content using Nova Act.
    
    Detects UI elements and understands screen layout.
    """
    
    def __init__(self):
        """Initialize screen analyzer."""
        self._nova_act = NovaActClient()
        
    async def analyze(self, screenshot: bytes) -> Dict[str, Any]:
        """Analyze a screenshot.
        
        Args:
            screenshot: Image bytes
            
        Returns:
            Analysis results with detected elements
        """
        result = await self._nova_act.analyze_screen(
            screenshot,
            "Identify all interactive UI elements"
        )
        
        return {
            "elements": result.get("elements", []),
            "layout": result.get("layout", {}),
            "summary": result.get("summary", "")
        }
    
    def find_element(
        self,
        elements: List[UIElement],
        text: str
    ) -> Optional[UIElement]:
        """Find element by text.
        
        Args:
            elements: List of elements
            text: Text to search for
            
        Returns:
            Matching element or None
        """
        for elem in elements:
            if elem.text and text.lower() in elem.text.lower():
                return elem
        return None
