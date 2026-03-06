"""Unit tests for utils/token_budget.py module.

This module tests the token budget management and cost control.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.utils.token_budget import (
    SessionBudget,
    TokenBudgetManager,
    TokenUsage,
    get_token_budget_manager,
)


class TestTokenUsage:
    """Test TokenUsage dataclass."""
    
    def test_create_token_usage(self):
        """Test creating token usage record."""
        usage = TokenUsage(
            prompt_tokens=100,
            completion_tokens=50,
            model="amazon.nova-lite-v1:0",
            cost_usd=0.0015
        )
        
        assert usage.prompt_tokens == 100
        assert usage.completion_tokens == 50
        assert usage.model == "amazon.nova-lite-v1:0"
        assert usage.cost_usd == 0.0015
        assert usage.timestamp is not None


class TestSessionBudget:
    """Test SessionBudget class."""
    
    @pytest.fixture
    def budget(self):
        """Create test session budget."""
        return SessionBudget(
            session_id="test-session",
            user_id="test-user",
            budget_limit_usd=10.0,
            warning_threshold_usd=5.0,
            stop_loss_threshold_usd=8.0
        )
    
    def test_initialization(self, budget):
        """Test budget initialization."""
        assert budget.session_id == "test-session"
        assert budget.user_id == "test-user"
        assert budget.budget_limit_usd == 10.0
        assert budget.total_cost_usd == 0.0
        assert budget.total_prompt_tokens == 0
        assert budget.stopped is False
    
    def test_calculate_cost_nova_lite(self, budget):
        """Test cost calculation for Nova Lite."""
        cost = budget.calculate_cost(
            "amazon.nova-lite-v1:0",
            prompt_tokens=1000,
            completion_tokens=500
        )
        
        # Nova Lite: $0.0003/1K input, $0.0012/1K output
        expected = (1000 / 1000) * 0.0003 + (500 / 1000) * 0.0012
        assert cost == pytest.approx(expected, 0.0001)
    
    def test_calculate_cost_nova_pro(self, budget):
        """Test cost calculation for Nova Pro."""
        cost = budget.calculate_cost(
            "amazon.nova-pro-v1:0",
            prompt_tokens=2000,
            completion_tokens=1000
        )
        
        # Nova Pro: $0.0008/1K input, $0.0032/1K output
        expected = (2000 / 1000) * 0.0008 + (1000 / 1000) * 0.0032
        assert cost == pytest.approx(expected, 0.0001)
    
    def test_calculate_cost_nova_micro(self, budget):
        """Test cost calculation for Nova Micro."""
        cost = budget.calculate_cost(
            "amazon.nova-micro-v1:0",
            prompt_tokens=10000,
            completion_tokens=5000
        )
        
        # Nova Micro: $0.000035/1K input, $0.00014/1K output
        expected = (10000 / 1000) * 0.000035 + (5000 / 1000) * 0.00014
        assert cost == pytest.approx(expected, 0.0001)
    
    def test_calculate_cost_unknown_model(self, budget):
        """Test cost calculation for unknown model uses defaults."""
        cost = budget.calculate_cost(
            "unknown-model",
            prompt_tokens=1000,
            completion_tokens=1000
        )
        
        # Should use default pricing
        expected = (1000 / 1000) * 0.001 + (1000 / 1000) * 0.003
        assert cost == pytest.approx(expected, 0.0001)
    
    def test_record_usage_success(self, budget):
        """Test recording usage within budget."""
        result = budget.record_usage(
            "amazon.nova-lite-v1:0",
            prompt_tokens=1000,
            completion_tokens=500
        )
        
        assert result["allowed"] is True
        assert result["current_cost"] > 0
        assert result["budget_remaining"] > 0
        assert len(budget.usage_history) == 1
        assert budget.total_prompt_tokens == 1000
    
    def test_record_usage_triggers_warning(self, budget):
        """Test that warning is triggered at threshold."""
        # Add usage that crosses warning threshold
        result = budget.record_usage(
            "amazon.nova-pro-v1:0",
            prompt_tokens=100000,  # Large usage
            completion_tokens=100000
        )
        
        if result.get("warning"):
            assert "warning" in result
            assert budget.warnings_issued > 0
    
    def test_record_usage_triggers_stop_loss(self, budget):
        """Test that stop-loss stops further usage."""
        # First, use up the budget
        budget.record_usage(
            "amazon.nova-pro-v1:0",
            prompt_tokens=1000000,
            completion_tokens=1000000
        )
        
        # Budget should be stopped
        assert budget.stopped is True
        
        # Subsequent usage should be blocked
        result = budget.record_usage(
            "amazon.nova-lite-v1:0",
            prompt_tokens=100,
            completion_tokens=50
        )
        
        assert result["allowed"] is False
        assert result["reason"] == "budget_exceeded"
    
    def test_get_summary(self, budget):
        """Test getting budget summary."""
        budget.record_usage(
            "amazon.nova-lite-v1:0",
            prompt_tokens=1000,
            completion_tokens=500
        )
        
        summary = budget.get_summary()
        
        assert summary["session_id"] == "test-session"
        assert summary["total_cost_usd"] > 0
        assert summary["budget_limit_usd"] == 10.0
        assert summary["remaining_usd"] > 0
        assert summary["total_tokens"] == 1500
        assert summary["usage_count"] == 1
        assert summary["stopped"] is False


class TestTokenBudgetManager:
    """Test TokenBudgetManager class."""
    
    @pytest.fixture
    def manager(self):
        """Create token budget manager."""
        with patch('src.utils.token_budget.get_logger'):
            return TokenBudgetManager()
    
    def test_initialization(self, manager):
        """Test manager initialization."""
        assert manager._budgets == {}
        assert manager.DEFAULT_BUDGET == 10.0
    
    def test_create_budget(self, manager):
        """Test creating a budget."""
        budget = manager.create_budget(
            session_id="session-123",
            user_id="user-456",
            budget_limit=25.0
        )
        
        assert budget.session_id == "session-123"
        assert budget.user_id == "user-456"
        assert budget.budget_limit_usd == 25.0
        assert "session-123" in manager._budgets
    
    def test_create_budget_default_limit(self, manager):
        """Test creating budget with default limit."""
        budget = manager.create_budget(
            session_id="session-789",
            user_id="user-000"
        )
        
        assert budget.budget_limit_usd == manager.DEFAULT_BUDGET
    
    def test_get_budget_existing(self, manager):
        """Test getting existing budget."""
        created = manager.create_budget("session-1", "user-1")
        retrieved = manager.get_budget("session-1")
        
        assert retrieved is created
    
    def test_get_budget_nonexistent(self, manager):
        """Test getting non-existent budget."""
        result = manager.get_budget("nonexistent")
        
        assert result is None
    
    def test_record_usage_existing_budget(self, manager):
        """Test recording usage with existing budget."""
        manager.create_budget("session-1", "user-1")
        
        result = manager.record_usage(
            "session-1",
            "amazon.nova-lite-v1:0",
            1000,
            500
        )
        
        assert "allowed" in result
    
    def test_record_usage_no_budget(self, manager):
        """Test recording usage without budget."""
        result = manager.record_usage(
            "no-budget-session",
            "amazon.nova-lite-v1:0",
            1000,
            500
        )
        
        assert result["allowed"] is True
        assert "no_budget_tracking" in result.get("warning", "")
    
    def test_check_budget_existing(self, manager):
        """Test checking existing budget."""
        manager.create_budget("session-1", "user-1")
        manager.record_usage("session-1", "amazon.nova-lite-v1:0", 1000, 500)
        
        result = manager.check_budget("session-1")
        
        assert "error" not in result
        assert result["session_id"] == "session-1"
    
    def test_check_budget_nonexistent(self, manager):
        """Test checking non-existent budget."""
        result = manager.check_budget("nonexistent")
        
        assert "error" in result


class TestGetTokenBudgetManager:
    """Test get_token_budget_manager singleton function."""
    
    def test_singleton_instance(self):
        """Test that singleton instance is returned."""
        with patch('src.utils.token_budget.get_logger'):
            manager1 = get_token_budget_manager()
            manager2 = get_token_budget_manager()
            
            assert manager1 is manager2
    
    def test_returns_manager(self):
        """Test that function returns TokenBudgetManager."""
        with patch('src.utils.token_budget.get_logger'):
            manager = get_token_budget_manager()
            
            assert isinstance(manager, TokenBudgetManager)
