"""
BrowserAgent - Specialist Agent for Web Browser Missions

This agent specializes in executing complex browser-based missions using
AWS Nova Act's Computer Use capabilities and Playwright automation.

Author: octopOS Team
"""

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from uuid import uuid4

from ..engine.base_agent import BaseAgent
from ..engine.message import OctoMessage, MessageType
from ..primitives.web.nova_act_driver import (
    NovaActDriver,
    get_nova_act_driver,
    MissionResult,
    MissionStep
)
from ..primitives.web.browser_session import get_session_manager
from ..utils.config import OctoConfig
from ..utils.logger import AgentLogger

logger = AgentLogger("BrowserAgent")


@dataclass
class BrowserMission:
    """Definition of a browser-based mission."""
    mission_id: str
    description: str
    starting_url: str
    target_sites: List[str] = field(default_factory=list)
    extraction_schema: Dict[str, Any] = field(default_factory=dict)
    comparison_criteria: Dict[str, Any] = field(default_factory=dict)
    max_duration_minutes: int = 10
    requires_login: bool = False
    credentials_key: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    user_id: str = "default"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "description": self.description,
            "starting_url": self.starting_url,
            "target_sites": self.target_sites,
            "extraction_schema": self.extraction_schema,
            "comparison_criteria": self.comparison_criteria,
            "max_duration_minutes": self.max_duration_minutes,
            "requires_login": self.requires_login,
            "created_at": self.created_at.isoformat(),
            "user_id": self.user_id
        }


@dataclass
class SiteResult:
    """Result from visiting a single site."""
    site_name: str
    url: str
    success: bool
    extracted_data: Dict[str, Any] = field(default_factory=dict)
    price: Optional[float] = None
    currency: str = "TRY" # Configurable default
    screenshot_path: Optional[str] = None
    error_message: Optional[str] = None
    visit_timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "site_name": self.site_name,
            "url": self.url,
            "success": self.success,
            "price": self.price,
            "currency": self.currency,
            "extracted_data": self.extracted_data,
            "screenshot_path": self.screenshot_path,
            "error": self.error_message,
            "timestamp": self.visit_timestamp.isoformat()
        }


@dataclass
class ComparisonResult:
    """Result of comparing data across multiple sites."""
    mission_id: str
    best_option: Optional[SiteResult] = None
    all_options: List[SiteResult] = field(default_factory=list)
    comparison_criteria: str = ""
    recommendation: str = ""
    price_range: Tuple[Optional[float], Optional[float]] = (None, None)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "best_option": self.best_option.to_dict() if self.best_option else None,
            "all_options": [opt.to_dict() for opt in self.all_options],
            "comparison_criteria": self.comparison_criteria,
            "recommendation": self.recommendation,
            "price_range": self.price_range
        }


class BrowserAgent(BaseAgent):
    """
    Specialist agent for browser-based missions.
    
    This agent uses Nova Act's Computer Use capabilities to:
    - Navigate websites autonomously
    - Extract structured data
    - Compare prices across multiple sites
    - Maintain session persistence
    - Execute complex multi-step missions
    
    Example missions:
    - "Find the best price for [Product]"
    - "Check stock availability for [Item]"
    - "Compare flight prices to [Destination]"
    - "Track prices across sites"
    """
    
    def __init__(
        self,
        name: str = "BrowserAgent",
        config: OctoConfig = None,
        nova_act_driver: NovaActDriver = None
    ):
        """
        Initialize BrowserAgent.
        
        Args:
            name: Agent name
            config: OctoConfig instance
            nova_act_driver: NovaActDriver instance (or create new)
        """
        super().__init__(
            name=name,
            context=None # Context will be initialized by BaseAgent
        )
        
        self.config = config or OctoConfig()
        self.nova_act_driver = nova_act_driver or get_nova_act_driver()
        self.session_manager = get_session_manager()
        
        # Lazy load SearchEngine for discovery
        self._search_engine = None
        
        # Active missions tracking
        self._active_missions: Dict[str, BrowserMission] = {}
        self._mission_results: Dict[str, MissionResult] = {}
        
        logger.info(f"BrowserAgent initialized: {self.name}")
    
    async def execute_task(self, task: Any) -> Dict[str, Any]:
        """
        Execute a task assigned to the Browser Agent.
        
        This satisfies the BaseAgent abstract method requirement.
        """
        action = getattr(task, "action", "")
        params = getattr(task, "params", {})
        
        # Create a dummy message for existing handlers
        from src.engine.message import MessageType
        message = OctoMessage(
            sender="Orchestrator",
            receiver=self.name,
            type=MessageType.TASK,
            payload=params
        )
        
        if action == "price_comparison":
            return await self._handle_price_comparison(message)
        elif action == "stock_check":
            return await self._handle_stock_check(message)
        elif action == "data_extraction":
            return await self._handle_data_extraction(message)
        elif action == "web_discovery":
            return await self._handle_web_discovery(message)
        elif action == "abort_mission":
            return await self._handle_abort_mission(message)
        else: # Default to general browser mission if no specific action matches
            return await self._handle_browser_mission(message)
    
    async def _handle_browser_mission(self, message: OctoMessage) -> Dict[str, Any]:
        """Handle general browser mission requests."""
        mission_data = message.payload
        
        mission = BrowserMission(
            mission_id=mission_data.get("mission_id", str(uuid4())),
            description=mission_data.get("description", "Browser mission"),
            starting_url=mission_data.get("starting_url"),
            target_sites=mission_data.get("target_sites", []),
            extraction_schema=mission_data.get("extraction_schema", {}),
            max_duration_minutes=mission_data.get("max_duration_minutes", 10),
            user_id=getattr(message, "user_id", "default")
        )
        
        result = await self.execute_mission(mission)
        return result.to_dict()
    
    async def _handle_price_comparison(self, message: OctoMessage) -> Dict[str, Any]:
        """Handle price comparison missions (e.g., RTX 5090 search)."""
        payload = message.payload
        
        # Extract mission parameters
        product_name = payload.get("product_name", "product")
        search_query = payload.get("search_query", product_name)
        sites = payload.get("sites", [])
        
        # If no sites provided, try discovery or use config defaults
        if not sites:
            if self.config.web.discovery_enabled:
                logger.info(f"Discovery enabled, searching for best sites for {product_name}")
                sites = await self._discover_sites(product_name)
            
            if not sites:
                sites = self.config.web.default_comparison_sites
        
        # Create mission
        mission_id = f"price_compare_{uuid4().hex[:8]}"
        
        # Run comparison across all sites
        comparison_result = await self.compare_prices(
            mission_id=mission_id,
            product_name=product_name,
            sites=sites,
            user_id=getattr(message, "user_id", "default")
        )
        
        return comparison_result.to_dict()
    
    async def _handle_stock_check(self, message: OctoMessage) -> Dict[str, Any]:
        """Handle stock availability check missions."""
        payload = message.payload
        
        product_name = payload.get("product_name")
        sites = payload.get("sites", [])
        
        mission_id = f"stock_check_{uuid4().hex[:8]}"
        
        results = []
        for site in sites:
            mission = BrowserMission(
                mission_id=f"{mission_id}_{site}",
                description=f"Check stock for {product_name} on {site}",
                starting_url=site,
                extraction_schema={
                    "in_stock": "boolean",
                    "price": "number",
                    "availability_text": "string"
                },
                user_id=getattr(message, "user_id", "default")
            )
            
            result = await self.execute_mission(mission)
            results.append({
                "site": site,
                "in_stock": result.final_data.get("in_stock", False) if result.final_data else False,
                "price": result.final_data.get("price") if result.final_data else None,
                "details": result.final_data if result.final_data else {}
            })
        
        return {
            "mission_id": mission_id,
            "product": product_name,
            "sites_checked": len(sites),
            "results": results
        }
    
    async def _handle_data_extraction(self, message: OctoMessage) -> Dict[str, Any]:
        """Handle structured data extraction missions."""
        payload = message.payload
        
        mission = BrowserMission(
            mission_id=payload.get("mission_id", str(uuid4())),
            description=payload.get("description", "Data extraction"),
            starting_url=payload.get("url"),
            extraction_schema=payload.get("schema", {}),
            user_id=getattr(message, "user_id", "default")
        )
        
        result = await self.execute_mission(mission)
        return result.to_dict()
    
    async def _handle_abort_mission(self, message: OctoMessage) -> Dict[str, Any]:
        """Handle mission abort requests."""
        mission_id = message.payload.get("mission_id")
        
        if mission_id:
            aborted = await self.nova_act_driver.abort_mission(mission_id)
            return {"mission_id": mission_id, "aborted": aborted}
        
        return {"error": "No mission_id provided"}
    
    async def execute_mission(self, mission: BrowserMission) -> MissionResult:
        """
        Execute a single browser mission.
        
        Args:
            mission: BrowserMission definition
            
        Returns:
            MissionResult with full execution history
        """
        logger.info(f"Executing mission: {mission.mission_id} - {mission.description}")
        
        self._active_missions[mission.mission_id] = mission
        
        # Build mission context for Nova Act
        mission_context = self._build_mission_context(mission)
        
        try:
            # Run the mission through Nova Act Driver
            result = await self.nova_act_driver.run_mission(
                mission_id=mission.mission_id,
                initial_url=mission.starting_url,
                mission_context=mission_context,
                user_id=mission.user_id,
                max_steps=self.config.browser.max_steps_per_mission
            )
            
            self._mission_results[mission.mission_id] = result
            
            logger.info(
                f"Mission {mission.mission_id} completed: "
                f"success={result.success}, steps={len(result.steps)}"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Mission {mission.mission_id} failed: {e}")
            
            # Create failed result
            result = MissionResult(
                mission_id=mission.mission_id,
                success=False,
                reasoning_log=[f"Mission failed with exception: {str(e)}"]
            )
            
            self._mission_results[mission.mission_id] = result
            return result
            
        finally:
            self._active_missions.pop(mission.mission_id, None)
    
    def _build_mission_context(self, mission: BrowserMission) -> str:
        """Build detailed mission context for Nova Act."""
        
        context_parts = [
            f"=== MISSION: {mission.description} ===",
            "",
            "OBJECTIVE:",
            mission.description,
            "",
        ]
        
        if mission.target_sites:
            context_parts.extend([
                "TARGET SITES:",
                "\n".join(f"- {site}" for site in mission.target_sites),
                ""
            ])
        
        if mission.extraction_schema:
            context_parts.extend([
                "EXTRACTION SCHEMA (extract these data points):",
                json.dumps(mission.extraction_schema, indent=2),
                ""
            ])
        
        if mission.comparison_criteria:
            context_parts.extend([
                "COMPARISON CRITERIA:",
                json.dumps(mission.comparison_criteria, indent=2),
                ""
            ])
        
        context_parts.extend([
            "INSTRUCTIONS:",
            "1. Navigate to the provided URL",
            "2. Analyze the page structure",
            "3. Use CLICK, TYPE, SCROLL actions to find required information",
            "4. Extract data according to the schema when found",
            "5. Take SCREENSHOTS for verification",
            "6. When mission is complete, use TERMINATE with extracted_data",
            "",
            "TIPS:",
            "- If a site blocks automation, try alternative approaches",
            "- Look for price, availability, ratings in product cards",
            "- Handle popups/cookies by accepting or closing them",
            "- Scroll to load more content if needed",
            ""
        ])
        
        return "\n".join(context_parts)
    
    async def compare_prices(
        self,
        mission_id: str,
        product_name: str,
        sites: List[str],
        user_id: str = "default"
    ) -> ComparisonResult:
        """
        Compare prices for a product across multiple sites.
        
        Args:
            mission_id: Base mission ID
            product_name: Product to search for
            sites: List of site domains to check
            user_id: User identifier
            
        Returns:
            ComparisonResult with best option and all findings
        """
        logger.info(f"Starting price comparison for {product_name} across {len(sites)} sites")
        
        all_results: List[SiteResult] = []
        
        # Use a single session for all sites to maintain context
        session = await self.session_manager.create_session(
            user_id=user_id,
            mission_id=mission_id,
            metadata={"product": product_name, "type": "price_comparison"}
        )
        
        try:
            for site in sites:
                site_mission_id = f"{mission_id}_{site}"
                
                mission = BrowserMission(
                    mission_id=site_mission_id,
                    description=f"Find price for {product_name} on {site}",
                    starting_url=f"https://{site}",
                    extraction_schema={
                        "product_name": "string",
                        "price": "number",
                        "currency": "string",
                        "in_stock": "boolean",
                        "availability": "string",
                        "product_url": "string"
                    },
                    user_id=user_id
                )
                
                # Execute mission
                result = await self.nova_act_driver.run_mission(
                    mission_id=site_mission_id,
                    initial_url=f"https://{site}",
                    mission_context=self._build_mission_context(mission),
                    user_id=user_id,
                    session_id=session.session_id,  # Reuse session
                    max_steps=15  # Limit per site
                )
                
                # Parse result into SiteResult
                site_result = self._parse_site_result(site, result)
                all_results.append(site_result)
                
                logger.info(
                    f"Site {site}: success={site_result.success}, "
                    f"price={site_result.price}"
                )
            
            # Find best option (lowest price)
            valid_results = [
                r for r in all_results 
                if r.success and r.price is not None
            ]
            
            best_option = None
            price_range = (None, None)
            
            if valid_results:
                # Sort by price
                sorted_results = sorted(valid_results, key=lambda x: x.price or float('inf'))
                best_option = sorted_results[0]
                prices = [r.price for r in valid_results if r.price is not None]
                price_range = (min(prices), max(prices)) if prices else (None, None)
            
            # Generate recommendation
            recommendation = self._generate_recommendation(
                product_name, best_option, valid_results
            )
            
            return ComparisonResult(
                mission_id=mission_id,
                best_option=best_option,
                all_options=all_results,
                comparison_criteria=f"Lowest price for {product_name}",
                recommendation=recommendation,
                price_range=price_range
            )
            
        finally:
            # Close session
            await self.session_manager.close_session(session.session_id, save_state=True)
    
    def _parse_site_result(self, site: str, result: MissionResult) -> SiteResult:
        """Parse MissionResult into SiteResult."""
        if not result.success or not result.final_data:
            return SiteResult(
                site_name=site,
                url=result.final_data.get("product_url", "") if result.final_data else "",
                success=False,
                error_message="Mission failed or no data extracted"
            )
        
        data = result.final_data
        
        # Extract price (handle various formats)
        price = None
        price_raw = data.get("price")
        if price_raw:
            try:
                if isinstance(price_raw, (int, float)):
                    price = float(price_raw)
                elif isinstance(price_raw, str):
                    # Remove currency symbols and parse
                    import re
                    price_clean = re.sub(r'[^\d.]', '', price_raw)
                    price = float(price_clean) if price_clean else None
            except (ValueError, TypeError):
                price = None
        
        return SiteResult(
            site_name=site,
            url=data.get("product_url", ""),
            success=True,
            extracted_data=data,
            price=price,
            currency=data.get("currency", "USD"),
            screenshot_path=self._get_last_screenshot(result)
        )
    
    def _get_last_screenshot(self, result: MissionResult) -> Optional[str]:
        """Get the last screenshot from mission steps."""
        for step in reversed(result.steps):
            if step.verification and step.verification.screenshot_path:
                return step.verification.screenshot_path
        return None
    
    def _generate_recommendation(
        self,
        product_name: str,
        best_option: Optional[SiteResult],
        all_options: List[SiteResult]
    ) -> str:
        """Generate human-readable recommendation."""
        if not best_option:
            return f"Could not find pricing information for {product_name} on any site."
        
        valid_count = len([o for o in all_options if o.success])
        
        recommendation = (
            f"Best price for {product_name}: ${best_option.price:.2f} "
            f"at {best_option.site_name}"
        )
        
        if valid_count > 1:
            prices = [o.price for o in all_options if o.price is not None]
            if len(prices) > 1:
                savings = max(prices) - best_option.price
                if savings > 0:
                    recommendation += (
                        f". You save ${savings:.2f} compared to the highest price."
                    )
        
        return recommendation
    
    async def get_mission_status(self, mission_id: str) -> Optional[Dict[str, Any]]:
        """Get current status of a mission."""
        # Check active missions
        if mission_id in self._active_missions:
            active_result = self.nova_act_driver.get_active_mission(mission_id)
            if active_result:
                return {
                    "mission_id": mission_id,
                    "status": "running",
                    "steps_completed": len(active_result.steps),
                    "current_step": active_result.steps[-1].to_dict() if active_result.steps else None
                }
            
            return {
                "mission_id": mission_id,
                "status": "starting",
                "message": "Mission is initializing"
            }
        
        # Check completed missions
        if mission_id in self._mission_results:
            result = self._mission_results[mission_id]
            return {
                "mission_id": mission_id,
                "status": "completed",
                "success": result.success,
                "total_steps": len(result.steps),
                "final_data": result.final_data
            }
        
        return None
    
    async def _handle_web_discovery(self, message: OctoMessage) -> Dict[str, Any]:
        """Handle manual site discovery request."""
        query = message.payload.get("query")
        if not query:
            return {"error": "Missing query"}
        
        sites = await self._discover_sites(query)
        return {"query": query, "found_sites": sites}

    async def _discover_sites(self, query: str) -> List[str]:
        """Use SearchEngine to find the best sites for a query."""
        if not self._search_engine:
            from ..primitives.web.search_engine import SearchEngine
            self._search_engine = SearchEngine()
            
        logger.info(f"Running web discovery for: {query}")
        
        # Search specifically for shopping/results sites
        tr_indicators = ["fiyat", "en ucuz", "nerede", "satın al", "fiyatı", "kaç para"]
        is_tr = any(indicator in query.lower() for indicator in tr_indicators) or any(c in query for c in "çğıöşüİ")
        
        if is_tr:
            discovery_query = f"{query} fiyat karşılaştırma alışveriş"
        else:
            discovery_query = f"{query} price comparison shopping"
        result = await self._search_engine.execute(query=discovery_query, num_results=10)
        
        if not result.success or not result.data:
            return []
            
        found_sites = []
        for item in result.data.get("results", []):
            url = item.get("url", "")
            if url:
                # Extract domain
                from urllib.parse import urlparse
                domain = urlparse(url).netloc
                if domain and domain not in found_sites:
                    found_sites.append(domain)
        
        # Filter out generic search engines if they appeared
        ignore_list = ["google.com", "bing.com", "duckduckgo.com", "brave.com"]
        filtered_sites = [s for s in found_sites if not any(ignore in s for ignore in ignore_list)]
        
        return filtered_sites[:5] # Return top 5 potential sites
    
    async def process_message(self, message: OctoMessage) -> Optional[OctoMessage]:
        """
        Process incoming messages for browser missions.
        
        This is the main entry point for the agent.
        """
        # Let BaseAgent handle routing
        return await super().process_message(message)
    
    async def initialize(self):
        """Initialize the browser agent."""
        await super().initialize()
        logger.info(f"BrowserAgent {self.name} ready")
    
    async def shutdown(self):
        """Shutdown the browser agent and cleanup sessions."""
        # Abort any active missions
        for mission_id in list(self._active_missions.keys()):
            await self.nova_act_driver.abort_mission(mission_id)
        
        await super().shutdown()
        logger.info(f"BrowserAgent {self.agent_id} shutdown complete")
        logger.info(f"BrowserAgent {self.name} shutdown complete")


# Factory function
_browser_agent: Optional[BrowserAgent] = None

def get_browser_agent(
    name: str = "BrowserAgent",
    config: OctoConfig = None
) -> BrowserAgent:
    """Get or create the global BrowserAgent instance."""
    global _browser_agent
    if _browser_agent is None:
        _browser_agent = BrowserAgent(name=name, config=config)
    return _browser_agent

def create_browser_agent(
    name: str = "BrowserAgent",
    config: OctoConfig = None
) -> BrowserAgent:
    """Create a new BrowserAgent instance."""
    return BrowserAgent(name=name, config=config)
