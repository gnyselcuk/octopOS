"""Unit tests for primitives/web/browser_session.py module.

This module tests the browser session management using Playwright.
"""

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from src.primitives.web.browser_session import (
    BrowserSnapshot,
    SessionInfo,
    SessionManager,
)


class TestSessionInfo:
    """Test SessionInfo dataclass."""
    
    def test_create_session_info(self):
        """Test creating session info."""
        info = SessionInfo(
            session_id="test123",
            profile_path=Path("/tmp/test"),
            context_id="ctx456"
        )
        
        assert info.session_id == "test123"
        assert info.profile_path == Path("/tmp/test")
        assert info.context_id == "ctx456"
        assert info.is_active is False
        assert isinstance(info.created_at, datetime)
        assert isinstance(info.last_accessed, datetime)
    
    def test_session_info_defaults(self):
        """Test session info default values."""
        info = SessionInfo(
            session_id="test",
            profile_path=Path("/tmp")
        )
        
        assert info.metadata == {}
        assert info.context_id is None


class TestBrowserSnapshot:
    """Test BrowserSnapshot dataclass."""
    
    def test_create_snapshot(self):
        """Test creating browser snapshot."""
        snapshot = BrowserSnapshot(
            url="https://example.com",
            title="Example Page",
            html="<html></html>",
            screenshot_path="/tmp/screenshot.png"
        )
        
        assert snapshot.url == "https://example.com"
        assert snapshot.title == "Example Page"
        assert snapshot.html == "<html></html>"
        assert snapshot.screenshot_path == "/tmp/screenshot.png"
        assert snapshot.viewport_width == 1920  # default
        assert snapshot.viewport_height == 1080  # default
    
    def test_snapshot_to_dict(self):
        """Test converting snapshot to dictionary."""
        snapshot = BrowserSnapshot(
            url="https://example.com",
            title="Example",
            html="<html></html>",
            screenshot_path="/tmp/ss.png",
            viewport_width=1280,
            viewport_height=720,
            scroll_position={"x": 100, "y": 200}
        )
        
        data = snapshot.to_dict()
        
        assert data["url"] == "https://example.com"
        assert data["title"] == "Example"
        assert data["viewport"]["width"] == 1280
        assert data["viewport"]["height"] == 720
        assert data["scroll_position"]["x"] == 100
        assert data["has_screenshot"] is True


class TestSessionManager:
    """Test SessionManager class."""
    
    @pytest.fixture
    def manager(self, tmp_path):
        """Create session manager with temp directory."""
        return SessionManager(
            profile_base_dir=str(tmp_path / "profiles"),
            headless=True,
            viewport_width=1920,
            viewport_height=1080,
            max_sessions=3
        )
    
    def test_initialization(self, manager, tmp_path):
        """Test session manager initialization."""
        assert manager.profile_base_dir == (tmp_path / "profiles").resolve()
        assert manager.headless is True
        assert manager.viewport_width == 1920
        assert manager.viewport_height == 1080
        assert manager.max_sessions == 3
        assert manager._sessions == {}
        assert manager._contexts == {}
        assert manager._pages == {}
    
    def test_generate_session_id(self, manager):
        """Test session ID generation."""
        session_id1 = manager._generate_session_id("user1", "mission1")
        session_id2 = manager._generate_session_id("user1", "mission1")
        session_id3 = manager._generate_session_id("user2", "mission1")
        
        # Same user/mission should generate different IDs (timestamp-based)
        assert session_id1 != session_id2
        # Different user should generate different ID
        assert session_id1 != session_id3
        # Should be 16 characters (SHA256 truncated)
        assert len(session_id1) == 16
    
    @pytest.mark.asyncio
    async def test_create_session(self, manager):
        """Test creating a browser session."""
        with patch.object(manager, '_init_playwright', new_callable=AsyncMock) as mock_init:
            mock_browser = AsyncMock()
            mock_context = AsyncMock()
            mock_page = AsyncMock()
            
            mock_init.return_value = mock_browser
            mock_browser.new_context.return_value = mock_context
            mock_context.new_page.return_value = mock_page
            
            session = await manager.create_session(
                user_id="test_user",
                mission_id="test_mission"
            )
            
            assert session is not None
            assert session.session_id is not None
            assert session.is_active is True
            assert session.metadata["user_id"] == "test_user"
            assert session.metadata["mission_id"] == "test_mission"
    
    @pytest.mark.asyncio
    async def test_create_session_reuse(self, manager):
        """Test reusing existing session."""
        with patch.object(manager, '_init_playwright', new_callable=AsyncMock) as mock_init:
            mock_browser = AsyncMock()
            mock_context = AsyncMock()
            mock_page = AsyncMock()
            
            mock_init.return_value = mock_browser
            mock_browser.new_context.return_value = mock_context
            mock_context.new_page.return_value = mock_page
            
            # Create first session
            session1 = await manager.create_session(
                user_id="user1",
                mission_id="mission1"
            )
            
            # Try to create another with same params (should reuse)
            session2 = await manager.create_session(
                user_id="user1",
                mission_id="mission1",
                reuse_existing=True
            )
            
            assert session1.session_id == session2.session_id
    
    @pytest.mark.asyncio
    async def test_get_session(self, manager):
        """Test getting session by ID."""
        with patch.object(manager, '_init_playwright', new_callable=AsyncMock) as mock_init:
            mock_browser = AsyncMock()
            mock_context = AsyncMock()
            mock_page = AsyncMock()
            
            mock_init.return_value = mock_browser
            mock_browser.new_context.return_value = mock_context
            mock_context.new_page.return_value = mock_page
            
            session = await manager.create_session()
            retrieved = await manager.get_session(session.session_id)
            
            assert retrieved is not None
            assert retrieved.session_id == session.session_id
    
    @pytest.mark.asyncio
    async def test_get_nonexistent_session(self, manager):
        """Test getting session that doesn't exist."""
        result = await manager.get_session("nonexistent")
        assert result is None
    
    @pytest.mark.asyncio
    async def test_close_session(self, manager):
        """Test closing a session."""
        with patch.object(manager, '_init_playwright', new_callable=AsyncMock) as mock_init:
            mock_browser = AsyncMock()
            mock_context = AsyncMock()
            mock_page = AsyncMock()
            
            mock_init.return_value = mock_browser
            mock_browser.new_context.return_value = mock_context
            mock_context.new_page.return_value = mock_page
            
            session = await manager.create_session()
            
            with patch.object(manager, 'save_session_state', new_callable=AsyncMock):
                result = await manager.close_session(session.session_id)
                
                assert result is True
                mock_context.close.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_close_nonexistent_session(self, manager):
        """Test closing session that doesn't exist."""
        result = await manager.close_session("nonexistent")
        assert result is False
    
    @pytest.mark.asyncio
    async def test_take_snapshot(self, manager, tmp_path):
        """Test taking browser snapshot."""
        with patch.object(manager, '_init_playwright', new_callable=AsyncMock) as mock_init:
            mock_browser = AsyncMock()
            mock_context = AsyncMock()
            mock_page = AsyncMock()
            
            mock_init.return_value = mock_browser
            mock_browser.new_context.return_value = mock_context
            mock_context.new_page.return_value = mock_page
            
            mock_page.url = "https://example.com"
            mock_page.title = AsyncMock(return_value="Example")
            mock_page.content = AsyncMock(return_value="<html></html>")
            mock_page.evaluate = AsyncMock(return_value={"x": 0, "y": 0})
            
            session = await manager.create_session()
            
            screenshot_dir = tmp_path / "screenshots"
            snapshot = await manager.take_snapshot(
                session.session_id,
                screenshot_dir=str(screenshot_dir)
            )
            
            assert snapshot is not None
            assert snapshot.url == "https://example.com"
            assert snapshot.title == "Example"
            mock_page.screenshot.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_take_snapshot_no_screenshot(self, manager):
        """Test taking snapshot without screenshot."""
        with patch.object(manager, '_init_playwright', new_callable=AsyncMock) as mock_init:
            mock_browser = AsyncMock()
            mock_context = AsyncMock()
            mock_page = AsyncMock()
            
            mock_init.return_value = mock_browser
            mock_browser.new_context.return_value = mock_context
            mock_context.new_page.return_value = mock_page
            
            mock_page.url = "https://example.com"
            mock_page.title = AsyncMock(return_value="Example")
            mock_page.content = AsyncMock(return_value="<html></html>")
            mock_page.evaluate = AsyncMock(return_value={"x": 0, "y": 0})
            
            session = await manager.create_session()
            
            snapshot = await manager.take_snapshot(session.session_id)
            
            assert snapshot is not None
            assert snapshot.screenshot_path is None
    
    @pytest.mark.asyncio
    async def test_save_session_state(self, manager, tmp_path):
        """Test saving session state."""
        with patch.object(manager, '_init_playwright', new_callable=AsyncMock) as mock_init:
            mock_browser = AsyncMock()
            mock_context = AsyncMock()
            mock_page = AsyncMock()
            
            mock_init.return_value = mock_browser
            mock_browser.new_context.return_value = mock_context
            mock_context.new_page.return_value = mock_page
            mock_context.storage_state = AsyncMock(return_value={
                "cookies": [],
                "origins": []
            })
            
            session = await manager.create_session()
            
            result = await manager.save_session_state(session.session_id)
            
            assert result is True
            mock_context.storage_state.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_session_limit_cleanup(self, manager):
        """Test that session limit triggers cleanup."""
        manager.max_sessions = 2
        
        with patch.object(manager, '_init_playwright', new_callable=AsyncMock) as mock_init, \
             patch.object(manager, '_cleanup_oldest_session', new_callable=AsyncMock) as mock_cleanup:
            
            mock_browser = AsyncMock()
            mock_context = AsyncMock()
            mock_page = AsyncMock()
            
            mock_init.return_value = mock_browser
            mock_browser.new_context.return_value = mock_context
            mock_context.new_page.return_value = mock_page
            
            # Create sessions up to limit
            await manager.create_session(user_id="user1")
            await manager.create_session(user_id="user2")
            
            # Third session should trigger cleanup
            await manager.create_session(user_id="user3")
            
            mock_cleanup.assert_called_once()
