"""
Web Primitives Module - Browser automation and web interaction tools.

This module provides tools for:
- Browser session management with persistence
- Web search (Brave/DuckDuckGo)
- Nova Act browser automation
- Public API calling
- Screenshot storage
- Result visualization

Author: octopOS Team
"""

from .browser_session import (
    SessionManager,
    SessionInfo,
    BrowserSnapshot,
    get_session_manager,
    cleanup_all_sessions
)

from .nova_act_driver import (
    NovaActDriver,
    NovaActDecision,
    BrowserAction,
    MissionResult,
    MissionStep,
    VerificationResult,
    get_nova_act_driver
)

from .screenshot_storage import (
    ScreenshotStorage,
    ScreenshotMetadata,
    get_screenshot_storage
)

from .result_visualizer import (
    ResultVisualizer,
    format_price_comparison,
    format_mission_result,
    format_stock_check
)

__all__ = [
    # Browser Session Management
    "SessionManager",
    "SessionInfo",
    "BrowserSnapshot",
    "get_session_manager",
    "cleanup_all_sessions",
    
    # Nova Act Driver
    "NovaActDriver",
    "NovaActDecision",
    "BrowserAction",
    "MissionResult",
    "MissionStep",
    "VerificationResult",
    "get_nova_act_driver",
    
    # Screenshot Storage
    "ScreenshotStorage",
    "ScreenshotMetadata",
    "get_screenshot_storage",
    
    # Result Visualizer
    "ResultVisualizer",
    "format_price_comparison",
    "format_mission_result",
    "format_stock_check"
]


def register_all() -> None:
    """Register all web primitives with the tool registry."""
    from src.primitives.tool_registry import register_primitive
    from src.primitives.web.search_engine import SearchEngine
    from src.primitives.web.public_api_caller import PublicAPICaller
    from src.primitives.web.nova_act_scraper import NovaActScraper
    
    # Register search engine
    register_primitive(SearchEngine(), category='web', tags=['search', 'web'])
    
    # Register public api caller
    register_primitive(PublicAPICaller(), category='web', tags=['api', 'public'])
    
    # Register nova act scraper
    register_primitive(NovaActScraper(), category='web', tags=['scrape', 'nova_act'])
