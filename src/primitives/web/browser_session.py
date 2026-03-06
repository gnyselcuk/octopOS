"""
Browser Session Management for Nova Act Mission Integration

Manages persistent browser sessions using Playwright, allowing:
- Long-lived sessions across missions
- Cookie persistence for maintaining login states
- Profile isolation per user/session
- Resource cleanup and session lifecycle management

Author: octopOS Team
"""

import asyncio
import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable
from contextlib import asynccontextmanager
import hashlib

from playwright.async_api import async_playwright, Browser, BrowserContext, Page, ConsoleMessage


@dataclass
class SessionInfo:
    """Information about a browser session."""
    session_id: str
    profile_path: Path
    created_at: datetime = field(default_factory=datetime.now)
    last_accessed: datetime = field(default_factory=datetime.now)
    context_id: Optional[str] = None
    is_active: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BrowserSnapshot:
    """Snapshot of browser state for Nova Act analysis."""
    url: str
    title: str
    html: str
    screenshot_path: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    viewport_width: int = 1920
    viewport_height: int = 1080
    console_logs: List[str] = field(default_factory=list)
    scroll_position: Dict[str, int] = field(default_factory=lambda: {"x": 0, "y": 0})
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for Nova Act model input."""
        return {
            "url": self.url,
            "title": self.title,
            "timestamp": self.timestamp.isoformat(),
            "viewport": {
                "width": self.viewport_width,
                "height": self.viewport_height
            },
            "scroll_position": self.scroll_position,
            "has_screenshot": self.screenshot_path is not None
        }


class SessionManager:
    """
    Manages persistent browser sessions for long-lived missions.
    
    Features:
    - Session isolation per user/mission context
    - Cookie persistence for maintaining login states
    - Resource cleanup and lifecycle management
    - Session pool for concurrent missions
    """
    
    def __init__(
        self,
        profile_base_dir: str = "~/.octopos/browser_profiles",
        headless: bool = True,
        viewport_width: int = 1920,
        viewport_height: int = 1080,
        timeout: int = 30000,
        max_sessions: int = 5,
        session_ttl_minutes: int = 60
    ):
        """
        Initialize the session manager.
        
        Args:
            profile_base_dir: Base directory for browser profiles
            headless: Run browser in headless mode
            viewport_width: Browser viewport width
            viewport_height: Browser viewport height
            timeout: Default timeout for operations (ms)
            max_sessions: Maximum number of concurrent sessions
            session_ttl_minutes: Session time-to-live before cleanup
        """
        self.profile_base_dir = Path(profile_base_dir).expanduser().resolve()
        self.headless = headless
        self.viewport_width = viewport_width
        self.viewport_height = viewport_height
        self.timeout = timeout
        self.max_sessions = max_sessions
        self.session_ttl_minutes = session_ttl_minutes
        
        # Active sessions
        self._sessions: Dict[str, SessionInfo] = {}
        self._contexts: Dict[str, BrowserContext] = {}
        self._pages: Dict[str, Page] = {}
        
        # Lock for thread-safe operations
        self._lock = asyncio.Lock()
        
        # Initialize base directory
        self.profile_base_dir.mkdir(parents=True, exist_ok=True)
        
        # Playwright instance (initialized on first use)
        self._playwright: Optional[Any] = None
        self._browser: Optional[Browser] = None
    
    async def _init_playwright(self) -> Browser:
        """Initialize Playwright and browser instance."""
        if self._playwright is None:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=self.headless,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-accelerated-2d-canvas",
                    "--disable-gpu",
                    f"--window-size={self.viewport_width},{self.viewport_height}"
                ]
            )
        return self._browser
    
    def _generate_session_id(self, user_id: str = "default", mission_id: str = None) -> str:
        """Generate a unique session ID based on user and mission."""
        components = [user_id, str(mission_id or "default"), datetime.now().isoformat()]
        hash_input = "|".join(components)
        return hashlib.sha256(hash_input.encode()).hexdigest()[:16]
    
    async def create_session(
        self,
        user_id: str = "default",
        mission_id: str = None,
        reuse_existing: bool = True,
        metadata: Dict[str, Any] = None
    ) -> SessionInfo:
        """
        Create a new browser session or reuse existing one.
        
        Args:
            user_id: User identifier for session grouping
            mission_id: Mission identifier for session isolation
            reuse_existing: Try to reuse existing session for same user/mission
            metadata: Additional metadata for the session
            
        Returns:
            SessionInfo for the created/retrieved session
        """
        async with self._lock:
            # Check if we should reuse an existing session
            if reuse_existing:
                for sid, info in self._sessions.items():
                    if (
                        info.metadata.get("user_id") == user_id and
                        info.metadata.get("mission_id") == mission_id and
                        info.is_active
                    ):
                        info.last_accessed = datetime.now()
                        return info
            
            # Check session limit
            if len(self._sessions) >= self.max_sessions:
                await self._cleanup_oldest_session()
            
            # Generate new session
            session_id = self._generate_session_id(user_id, mission_id)
            profile_path = self.profile_base_dir / session_id
            profile_path.mkdir(parents=True, exist_ok=True)
            
            # Initialize browser
            browser = await self._init_playwright()
            
            # Create context with profile
            context = await browser.new_context(
                viewport={"width": self.viewport_width, "height": self.viewport_height},
                user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                storage_state=str(profile_path / "storage_state.json") 
                    if (profile_path / "storage_state.json").exists() 
                    else None,
                java_script_enabled=True,
                bypass_csp=True,
                permissions=["geolocation", "notifications"]
            )
            
            # Create initial page
            page = await context.new_page()
            page.set_default_timeout(self.timeout)
            
            # Set up console log capture
            console_logs = []
            page.on("console", lambda msg: console_logs.append(f"[{msg.type}] {msg.text}"))
            
            # Store session
            session_info = SessionInfo(
                session_id=session_id,
                profile_path=profile_path,
                context_id=str(id(context)),
                is_active=True,
                metadata={
                    "user_id": user_id,
                    "mission_id": mission_id,
                    "console_logs": console_logs,
                    **(metadata or {})
                }
            )
            
            self._sessions[session_id] = session_info
            self._contexts[session_id] = context
            self._pages[session_id] = page
            
            return session_info
    
    async def get_session(self, session_id: str) -> Optional[SessionInfo]:
        """Get session info by ID."""
        async with self._lock:
            info = self._sessions.get(session_id)
            if info:
                info.last_accessed = datetime.now()
            return info
    
    async def get_page(self, session_id: str) -> Optional[Page]:
        """Get the active page for a session."""
        async with self._lock:
            return self._pages.get(session_id)
    
    async def get_context(self, session_id: str) -> Optional[BrowserContext]:
        """Get the browser context for a session."""
        async with self._lock:
            return self._contexts.get(session_id)
    
    async def take_snapshot(
        self,
        session_id: str,
        screenshot_dir: str = None
    ) -> Optional[BrowserSnapshot]:
        """
        Take a snapshot of the current browser state.
        
        Args:
            session_id: Session to snapshot
            screenshot_dir: Directory to save screenshot (optional)
            
        Returns:
            BrowserSnapshot with current state
        """
        page = await self.get_page(session_id)
        if not page:
            return None
        
        # Get current state
        url = page.url
        title = await page.title()
        html = await page.content()
        
        # Get scroll position
        scroll_position = await page.evaluate("() => ({ x: window.scrollX, y: window.scrollY })")
        
        # Take screenshot
        screenshot_path = None
        if screenshot_dir:
            screenshot_dir = Path(screenshot_dir).expanduser()
            screenshot_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_path = str(screenshot_dir / f"{session_id}_{timestamp}.png")
            await page.screenshot(path=screenshot_path, full_page=False)
        
        # Get console logs from session metadata
        session_info = self._sessions.get(session_id)
        console_logs = []
        if session_info and "console_logs" in session_info.metadata:
            console_logs = session_info.metadata["console_logs"][-50:]  # Last 50 logs
            session_info.metadata["console_logs"] = []  # Clear after capture
        
        return BrowserSnapshot(
            url=url,
            title=title,
            html=html,
            screenshot_path=screenshot_path,
            viewport_width=self.viewport_width,
            viewport_height=self.viewport_height,
            console_logs=console_logs,
            scroll_position=scroll_position
        )
    
    async def save_session_state(self, session_id: str) -> bool:
        """Save session state (cookies, localStorage, etc.) to disk."""
        context = await self.get_context(session_id)
        if not context:
            return False
        
        session_info = self._sessions.get(session_id)
        if not session_info:
            return False
        
        try:
            storage_state = await context.storage_state()
            storage_path = session_info.profile_path / "storage_state.json"
            with open(storage_path, "w") as f:
                json.dump(storage_state, f, indent=2)
            return True
        except Exception as e:
            print(f"Failed to save session state: {e}")
            return False
    
    async def close_session(self, session_id: str, save_state: bool = True) -> bool:
        """
        Close a session and clean up resources.
        
        Args:
            session_id: Session to close
            save_state: Whether to save cookies/storage before closing
            
        Returns:
            True if session was closed successfully
        """
        async with self._lock:
            session_info = self._sessions.get(session_id)
            if not session_info:
                return False
            
            try:
                # Save state if requested
                if save_state:
                    await self.save_session_state(session_id)
                
                # Close context
                context = self._contexts.get(session_id)
                if context:
                    await context.close()
                
                # Clean up
                self._sessions.pop(session_id, None)
                self._contexts.pop(session_id, None)
                self._pages.pop(session_id, None)
                
                session_info.is_active = False
                return True
            except Exception as e:
                print(f"Error closing session {session_id}: {e}")
                return False
    
    async def _cleanup_oldest_session(self):
        """Clean up the oldest session when max sessions reached."""
        if not self._sessions:
            return
        
        # Find oldest session
        oldest = min(self._sessions.values(), key=lambda s: s.last_accessed)
        await self.close_session(oldest.session_id, save_state=True)
    
    async def cleanup_expired_sessions(self):
        """Clean up sessions that have exceeded TTL."""
        now = datetime.now()
        expired = [
            sid for sid, info in self._sessions.items()
            if info.is_active and 
            (now - info.last_accessed).total_seconds() / 60 > self.session_ttl_minutes
        ]
        
        for sid in expired:
            await self.close_session(sid, save_state=True)
    
    async def close_all(self):
        """Close all sessions and shut down browser."""
        async with self._lock:
            for session_id in list(self._sessions.keys()):
                await self.close_session(session_id, save_state=True)
            
            if self._browser:
                await self._browser.close()
                self._browser = None
            
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None
    
    @asynccontextmanager
    async def session(
        self,
        user_id: str = "default",
        mission_id: str = None,
        metadata: Dict[str, Any] = None
    ):
        """
        Context manager for automatic session lifecycle management.
        
        Usage:
            async with session_manager.session("user123", "price_check") as session:
                page = await session_manager.get_page(session.session_id)
                await page.goto("https://example.com")
        """
        session = await self.create_session(user_id, mission_id, metadata=metadata)
        try:
            yield session
        finally:
            await self.close_session(session.session_id, save_state=True)
    
    def get_active_sessions(self) -> List[SessionInfo]:
        """Get list of all active sessions."""
        return [info for info in self._sessions.values() if info.is_active]
    
    async def execute_in_session(
        self,
        session_id: str,
        action: Callable[[Page], Any]
    ) -> Any:
        """
        Execute an action in the context of a session.
        
        Args:
            session_id: Session ID
            action: Async callable that receives the Page object
            
        Returns:
            Result of the action
        """
        page = await self.get_page(session_id)
        if not page:
            raise ValueError(f"Session {session_id} not found or inactive")
        
        return await action(page)


# Global session manager instance
_global_session_manager: Optional[SessionManager] = None


def get_session_manager(
    profile_base_dir: str = "~/.octopos/browser_profiles",
    headless: bool = True,
    **kwargs
) -> SessionManager:
    """Get or create global session manager instance."""
    global _global_session_manager
    if _global_session_manager is None:
        _global_session_manager = SessionManager(
            profile_base_dir=profile_base_dir,
            headless=headless,
            **kwargs
        )
    return _global_session_manager


async def cleanup_all_sessions():
    """Cleanup all sessions - call on application shutdown."""
    global _global_session_manager
    if _global_session_manager:
        await _global_session_manager.close_all()
        _global_session_manager = None
