"""Token Budget - Cost control and budgeting for LLM usage.

Tracks token usage per session with budget limits and stop-loss mechanism.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID

from src.utils.logger import get_logger

logger = get_logger()


@dataclass
class TokenUsage:
    """Token usage record."""
    prompt_tokens: int
    completion_tokens: int
    model: str
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    cost_usd: float = 0.0


@dataclass
class SessionBudget:
    """Budget tracking for a session."""
    session_id: str
    user_id: str
    budget_limit_usd: float
    warning_threshold_usd: float
    stop_loss_threshold_usd: float
    
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_cost_usd: float = 0.0
    usage_history: List[TokenUsage] = field(default_factory=list)
    warnings_issued: int = 0
    stopped: bool = False
    
    # Model pricing (per 1K tokens)
    MODEL_PRICING = {
        "amazon.nova-lite-v1:0": {"input": 0.0003, "output": 0.0012},
        "amazon.nova-pro-v1:0": {"input": 0.0008, "output": 0.0032},
        "amazon.nova-micro-v1:0": {"input": 0.000035, "output": 0.00014},
    }
    
    def calculate_cost(self, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        """Calculate cost for token usage."""
        pricing = self.MODEL_PRICING.get(model, {"input": 0.001, "output": 0.003})
        input_cost = (prompt_tokens / 1000) * pricing["input"]
        output_cost = (completion_tokens / 1000) * pricing["output"]
        return input_cost + output_cost
    
    def record_usage(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int
    ) -> Dict[str, any]:
        """Record token usage and check budget.
        
        Returns:
            Dict with status and warnings
        """
        if self.stopped:
            return {"allowed": False, "reason": "budget_exceeded", "current_cost": self.total_cost_usd}
        
        cost = self.calculate_cost(model, prompt_tokens, completion_tokens)
        
        usage = TokenUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            model=model,
            cost_usd=cost
        )
        
        self.usage_history.append(usage)
        self.total_prompt_tokens += prompt_tokens
        self.total_completion_tokens += completion_tokens
        self.total_cost_usd += cost
        
        result = {
            "allowed": True,
            "current_cost": self.total_cost_usd,
            "budget_remaining": self.budget_limit_usd - self.total_cost_usd
        }
        
        # Check stop-loss
        if self.total_cost_usd >= self.stop_loss_threshold_usd:
            self.stopped = True
            result["allowed"] = False
            result["reason"] = "stop_loss_triggered"
            logger.error(f"Stop-loss triggered for session {self.session_id}: ${self.total_cost_usd:.2f}")
        
        # Check warning threshold
        elif self.total_cost_usd >= self.warning_threshold_usd:
            self.warnings_issued += 1
            result["warning"] = f"Budget warning: ${self.total_cost_usd:.2f} / ${self.budget_limit_usd:.2f}"
            logger.warning(f"Budget warning for session {self.session_id}: ${self.total_cost_usd:.2f}")
        
        return result
    
    def get_summary(self) -> Dict:
        """Get budget summary."""
        return {
            "session_id": self.session_id,
            "total_cost_usd": round(self.total_cost_usd, 4),
            "budget_limit_usd": self.budget_limit_usd,
            "remaining_usd": round(self.budget_limit_usd - self.total_cost_usd, 4),
            "total_tokens": self.total_prompt_tokens + self.total_completion_tokens,
            "usage_count": len(self.usage_history),
            "stopped": self.stopped
        }


class TokenBudgetManager:
    """Manages token budgets for all sessions."""
    
    DEFAULT_BUDGET = 10.0  # $10 default
    WARNING_THRESHOLD = 0.5  # 50% warning
    STOP_LOSS_THRESHOLD = 5.0  # $5 stop-loss
    
    def __init__(self):
        self._budgets: Dict[str, SessionBudget] = {}
        self._logger = logger
    
    def create_budget(
        self,
        session_id: str,
        user_id: str,
        budget_limit: Optional[float] = None
    ) -> SessionBudget:
        """Create a new session budget."""
        budget = SessionBudget(
            session_id=session_id,
            user_id=user_id,
            budget_limit_usd=budget_limit or self.DEFAULT_BUDGET,
            warning_threshold_usd=(budget_limit or self.DEFAULT_BUDGET) * self.WARNING_THRESHOLD,
            stop_loss_threshold_usd=min(
                self.STOP_LOSS_THRESHOLD,
                (budget_limit or self.DEFAULT_BUDGET) * 0.8
            )
        )
        self._budgets[session_id] = budget
        self._logger.info(f"Created budget for session {session_id}: ${budget.budget_limit_usd}")
        return budget
    
    def get_budget(self, session_id: str) -> Optional[SessionBudget]:
        """Get budget for session."""
        return self._budgets.get(session_id)
    
    def record_usage(
        self,
        session_id: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int
    ) -> Dict[str, any]:
        """Record usage for a session."""
        budget = self._budgets.get(session_id)
        if not budget:
            self._logger.warning(f"No budget found for session {session_id}")
            return {"allowed": True, "warning": "no_budget_tracking"}
        
        return budget.record_usage(model, prompt_tokens, completion_tokens)
    
    def check_budget(self, session_id: str) -> Dict[str, any]:
        """Check current budget status."""
        budget = self._budgets.get(session_id)
        if not budget:
            return {"error": "budget_not_found"}
        return budget.get_summary()


# Singleton instance
_budget_manager: Optional[TokenBudgetManager] = None


def get_token_budget_manager() -> TokenBudgetManager:
    """Get singleton TokenBudgetManager."""
    global _budget_manager
    if _budget_manager is None:
        _budget_manager = TokenBudgetManager()
    return _budget_manager
