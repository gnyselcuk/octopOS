"""Unit tests for interfaces/cli/commands.py module.

This module tests the CLI commands for octopOS management.
"""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from typer.testing import CliRunner

from src.interfaces.cli.commands import app, budget, cache_stats, dlq_command, status


runner = CliRunner()


class TestStatusCommand:
    """Test the status CLI command."""
    
    @pytest.fixture
    def mock_manager(self):
        """Create a mock manager agent."""
        with patch('src.interfaces.cli.commands.get_manager_agent') as mock_get:
            manager = MagicMock()
            registry = MagicMock()
            
            # Mock agent data
            agent1 = MagicMock()
            agent1.agent_id = "agent-001"
            agent1.agent_type = "coder"
            agent1.status.value = "idle"
            agent1.task_count = 0
            
            agent2 = MagicMock()
            agent2.agent_id = "agent-002"
            agent2.agent_type = "browser"
            agent2.status.value = "busy"
            agent2.task_count = 2
            
            registry.get_all_agents.return_value = [agent1, agent2]
            registry.get_health_summary.return_value = {
                'total_agents': 2,
                'idle': 1,
                'busy': 1,
                'error': 0
            }
            manager.get_registry.return_value = registry
            
            mock_get.return_value = manager
            yield manager
    
    @pytest.fixture
    def mock_worker_pool(self):
        """Create a mock worker pool."""
        with patch('src.interfaces.cli.commands.get_worker_pool') as mock_get:
            pool = MagicMock()
            pool.get_stats.return_value = {
                'available_workers': 3,
                'busy_workers': 2,
                'total_workers': 5,
                'queue_size': 10,
                'config': {'min_workers': 2, 'max_workers': 10}
            }
            mock_get.return_value = pool
            yield pool
    
    def test_status_basic(self, mock_manager, mock_worker_pool):
        """Test basic status command output."""
        result = runner.invoke(app, ["status"])
        
        assert result.exit_code == 0
        assert "System Status" in result.output
        assert "agent-001" in result.output
        assert "agent-002" in result.output
        assert "coder" in result.output
        assert "browser" in result.output
    
    def test_status_verbose(self, mock_manager, mock_worker_pool):
        """Test status command with verbose flag."""
        result = runner.invoke(app, ["status", "--verbose"])
        
        assert result.exit_code == 0
        assert "min_workers" in result.output or "min=" in result.output


class TestBudgetCommand:
    """Test the budget CLI command."""
    
    @pytest.fixture
    def mock_budget_manager(self):
        """Create a mock token budget manager."""
        with patch('src.interfaces.cli.commands.get_token_budget_manager') as mock_get:
            manager = MagicMock()
            
            # Mock budget
            budget = MagicMock()
            budget.get_summary.return_value = {
                'total_cost_usd': 2.50,
                'budget_limit_usd': 10.0,
                'remaining_usd': 7.50,
                'total_tokens': 15000,
                'usage_count': 25,
                'stopped': False
            }
            
            manager.get_budget.return_value = budget
            manager.create_budget.return_value = budget
            mock_get.return_value = manager
            yield manager
    
    def test_budget_show_existing(self, mock_budget_manager):
        """Test showing existing budget."""
        result = runner.invoke(app, ["budget"])
        
        assert result.exit_code == 0
        assert "$2.50" in result.output or "$2.5" in result.output
        assert "$10.0" in result.output or "$10" in result.output
    
    def test_budget_show_missing(self, mock_budget_manager):
        """Test showing budget when none exists."""
        mock_budget_manager.get_budget.return_value = None
        
        result = runner.invoke(app, ["budget"])
        
        assert result.exit_code == 0
        assert "No budget found" in result.output
    
    def test_budget_create(self, mock_budget_manager):
        """Test creating a new budget."""
        result = runner.invoke(app, ["budget", "--create", "25.0"])
        
        assert result.exit_code == 0
        assert "Created budget" in result.output or "✓" in result.output
        mock_budget_manager.create_budget.assert_called_once()
    
    def test_budget_with_session(self, mock_budget_manager):
        """Test budget command with specific session."""
        result = runner.invoke(app, ["budget", "--session", "test-session"])
        
        assert result.exit_code == 0
        mock_budget_manager.get_budget.assert_called_with("test-session")
    
    def test_budget_exceeded(self, mock_budget_manager):
        """Test budget display when exceeded."""
        budget = MagicMock()
        budget.get_summary.return_value = {
            'total_cost_usd': 12.0,
            'budget_limit_usd': 10.0,
            'remaining_usd': -2.0,
            'total_tokens': 20000,
            'usage_count': 30,
            'stopped': True
        }
        mock_budget_manager.get_budget.return_value = budget
        
        result = runner.invoke(app, ["budget"])
        
        assert result.exit_code == 0
        assert "BUDGET EXCEEDED" in result.output or "stopped" in result.output.lower()


class TestCacheStatsCommand:
    """Test the cache-stats CLI command."""
    
    @pytest.fixture
    def mock_cache(self):
        """Create a mock semantic cache."""
        with patch('src.interfaces.cli.commands.get_semantic_cache') as mock_get:
            cache = MagicMock()
            cache.get_stats.return_value = {
                'total_entries': 100,
                'total_hits': 500,
                'avg_hits_per_entry': 5.0,
                'cache_size_mb': 12.5
            }
            mock_get.return_value = cache
            yield cache
    
    def test_cache_stats_basic(self, mock_cache):
        """Test basic cache stats display."""
        result = runner.invoke(app, ["cache-stats"])
        
        assert result.exit_code == 0
        assert "Cache Statistics" in result.output
        assert "100" in result.output  # entries
        assert "500" in result.output  # hits
    
    def test_cache_stats_with_error(self, mock_cache):
        """Test cache stats when cache returns error."""
        mock_cache.get_stats.return_value = {"error": "Cache not initialized"}
        
        result = runner.invoke(app, ["cache-stats"])
        
        assert result.exit_code == 0
        assert "Error" in result.output
    
    def test_cache_stats_clear(self, mock_cache):
        """Test clearing expired cache entries."""
        result = runner.invoke(app, ["cache-stats", "--clear"])
        
        assert result.exit_code == 0
        mock_cache.clear_expired.assert_called_once()


class TestDLQCommand:
    """Test the DLQ (Dead Letter Queue) CLI command."""
    
    @pytest.fixture
    def mock_dlq(self):
        """Create a mock DLQ."""
        with patch('src.interfaces.cli.commands.get_dead_letter_queue') as mock_get:
            dlq = MagicMock()
            dlq.get_stats.return_value = {
                'total_entries': 10,
                'pending': 5,
                'analyzing': 2,
                'resolved': 2,
                'failed': 1,
                'error_types': {'RuntimeError': 3, 'TimeoutError': 2}
            }
            
            # Mock pending entries
            entry1 = MagicMock()
            entry1.id = "entry-001"
            entry1.agent_name = "CoderAgent"
            entry1.error_type = "RuntimeError"
            entry1.failed_at = "2024-01-01T10:00:00"
            
            entry2 = MagicMock()
            entry2.id = "entry-002"
            entry2.agent_name = "BrowserAgent"
            entry2.error_type = "TimeoutError"
            entry2.failed_at = "2024-01-01T09:00:00"
            
            dlq.get_pending.return_value = [entry1, entry2]
            dlq.clear_resolved.return_value = 3
            
            mock_get.return_value = dlq
            yield dlq
    
    def test_dlq_stats_default(self, mock_dlq):
        """Test DLQ stats shown by default."""
        result = runner.invoke(app, ["dlq"])
        
        assert result.exit_code == 0
        assert "Dead Letter Queue" in result.output
        assert "10" in result.output  # total
        assert "5" in result.output   # pending
    
    def test_dlq_list_entries(self, mock_dlq):
        """Test listing DLQ entries."""
        result = runner.invoke(app, ["dlq", "--list"])
        
        assert result.exit_code == 0
        assert "CoderAgent" in result.output
        assert "BrowserAgent" in result.output
        assert "RuntimeError" in result.output
    
    def test_dlq_clear_resolved(self, mock_dlq):
        """Test clearing resolved DLQ entries."""
        result = runner.invoke(app, ["dlq", "--clear-resolved"])
        
        assert result.exit_code == 0
        mock_dlq.clear_resolved.assert_called_once()
    
    def test_dlq_stats_flag(self, mock_dlq):
        """Test DLQ with explicit stats flag."""
        result = runner.invoke(app, ["dlq", "--stats"])
        
        assert result.exit_code == 0
        assert "Dead Letter Queue" in result.output


class TestAskCommand:
    """Test the ask CLI command."""
    
    @pytest.fixture
    def mock_orchestrator(self):
        """Create a mock orchestrator."""
        with patch('src.interfaces.cli.commands.get_orchestrator') as mock_get:
            orchestrator = AsyncMock()
            orchestrator.process_user_input.return_value = {
                'status': 'success',
                'response': 'This is the answer to your question.'
            }
            mock_get.return_value = orchestrator
            yield orchestrator
    
    def test_ask_success(self, mock_orchestrator):
        """Test successful ask command."""
        result = runner.invoke(app, ["ask", "What is the weather today?"])
        
        assert result.exit_code == 0
        assert "Processing" in result.output
        mock_orchestrator.process_user_input.assert_called_once()
    
    def test_ask_error(self, mock_orchestrator):
        """Test ask command with error response."""
        mock_orchestrator.process_user_input.return_value = {
            'status': 'error',
            'message': 'Something went wrong'
        }
        
        result = runner.invoke(app, ["ask", "Test question"])
        
        assert result.exit_code == 0
        assert "Error" in result.output or "error" in result.output.lower()


class TestChatCommand:
    """Test the chat CLI command."""
    
    @pytest.fixture
    def mock_orchestrator(self):
        """Create a mock orchestrator."""
        with patch('src.interfaces.cli.commands.get_orchestrator') as mock_get:
            orchestrator = AsyncMock()
            orchestrator.process_user_input.return_value = {
                'status': 'success',
                'response': 'Hello! How can I help you?'
            }
            mock_get.return_value = orchestrator
            yield orchestrator
    
    @patch('src.interfaces.cli.commands.Prompt.ask')
    def test_chat_interactive(self, mock_prompt, mock_orchestrator):
        """Test interactive chat mode."""
        mock_prompt.side_effect = ["Hello", "exit"]
        
        result = runner.invoke(app, ["chat"])
        
        assert result.exit_code == 0
        assert "Chat Mode" in result.output or "chat" in result.output.lower()
    
    @patch('src.interfaces.cli.commands.Prompt.ask')
    def test_chat_with_quit(self, mock_prompt, mock_orchestrator):
        """Test chat with quit command."""
        mock_prompt.side_effect = ["quit"]
        
        result = runner.invoke(app, ["chat"])
        
        assert result.exit_code == 0
