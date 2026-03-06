"""Dead Letter Queue (DLQ) - Failed messages handling.

Collects failed messages for later analysis and recovery by Self-Healing Agent.
"""

import json
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4
from pathlib import Path
import asyncio

from src.engine.message import OctoMessage, MessageType
from src.utils.logger import get_logger

logger = get_logger()


@dataclass
class DeadLetter:
    """A failed message entry."""
    id: str
    original_message: Dict[str, Any]
    error_type: str
    error_message: str
    failed_at: str
    retry_count: int
    agent_name: str
    status: str  # "pending", "analyzing", "resolved", "failed"
    analysis_result: Optional[Dict] = None
    resolved_at: Optional[str] = None


class DeadLetterQueue:
    """Queue for failed messages.
    
    Stores messages that failed processing for later analysis
    by the Self-Healing Agent.
    """
    
    def __init__(self, storage_path: Optional[str] = None):
        """Initialize DLQ.
        
        Args:
            storage_path: Path to store DLQ data
        """
        self._storage_path = Path(storage_path or ".data/dlq")
        self._storage_path.mkdir(parents=True, exist_ok=True)
        
        self._queue: List[DeadLetter] = []
        self._processing = False
        
        # Load existing entries
        self._load()
        
        logger.info(f"DLQ initialized with {len(self._queue)} entries")
    
    def _get_storage_file(self) -> Path:
        """Get storage file path."""
        return self._storage_path / "dead_letters.json"
    
    def _load(self):
        """Load existing entries from storage."""
        storage_file = self._get_storage_file()
        if storage_file.exists():
            try:
                with open(storage_file, 'r') as f:
                    data = json.load(f)
                    self._queue = [DeadLetter(**entry) for entry in data]
            except Exception as e:
                logger.error(f"Failed to load DLQ: {e}")
    
    def _save(self):
        """Save entries to storage."""
        try:
            storage_file = self._get_storage_file()
            with open(storage_file, 'w') as f:
                json.dump(
                    [asdict(entry) for entry in self._queue],
                    f,
                    indent=2,
                    default=str
                )
        except Exception as e:
            logger.error(f"Failed to save DLQ: {e}")
    
    def add(
        self,
        message: OctoMessage,
        error_type: str,
        error_message: str,
        agent_name: str,
        retry_count: int = 0
    ) -> str:
        """Add a failed message to DLQ.
        
        Args:
            message: The failed message
            error_type: Type of error
            error_message: Error description
            agent_name: Agent that failed
            retry_count: Number of retry attempts
            
        Returns:
            DLQ entry ID
        """
        entry_id = str(uuid4())
        
        dead_letter = DeadLetter(
            id=entry_id,
            original_message=message.model_dump(),
            error_type=error_type,
            error_message=error_message,
            failed_at=datetime.utcnow().isoformat(),
            retry_count=retry_count,
            agent_name=agent_name,
            status="pending"
        )
        
        self._queue.append(dead_letter)
        self._save()
        
        logger.warning(
            f"Added to DLQ: {entry_id} from {agent_name} - {error_type}"
        )
        
        return entry_id
    
    def get_pending(self, limit: int = 100) -> List[DeadLetter]:
        """Get pending entries for analysis.
        
        Args:
            limit: Maximum entries to return
            
        Returns:
            List of pending dead letters
        """
        pending = [
            entry for entry in self._queue
            if entry.status == "pending"
        ]
        return pending[:limit]
    
    def update_status(
        self,
        entry_id: str,
        status: str,
        analysis_result: Optional[Dict] = None
    ) -> bool:
        """Update entry status.
        
        Args:
            entry_id: Entry ID
            status: New status
            analysis_result: Analysis results
            
        Returns:
            True if updated
        """
        for entry in self._queue:
            if entry.id == entry_id:
                entry.status = status
                entry.analysis_result = analysis_result
                
                if status in ["resolved", "failed"]:
                    entry.resolved_at = datetime.utcnow().isoformat()
                
                self._save()
                logger.info(f"Updated DLQ entry {entry_id} to {status}")
                return True
        
        return False
    
    def get_entry(self, entry_id: str) -> Optional[DeadLetter]:
        """Get specific entry."""
        for entry in self._queue:
            if entry.id == entry_id:
                return entry
        return None
    
    def get_stats(self) -> Dict[str, Any]:
        """Get DLQ statistics."""
        total = len(self._queue)
        pending = sum(1 for e in self._queue if e.status == "pending")
        analyzing = sum(1 for e in self._queue if e.status == "analyzing")
        resolved = sum(1 for e in self._queue if e.status == "resolved")
        failed = sum(1 for e in self._queue if e.status == "failed")
        
        # Count by error type
        error_types: Dict[str, int] = {}
        for entry in self._queue:
            error_types[entry.error_type] = error_types.get(entry.error_type, 0) + 1
        
        return {
            "total_entries": total,
            "pending": pending,
            "analyzing": analyzing,
            "resolved": resolved,
            "failed": failed,
            "error_types": error_types
        }
    
    async def process_with_healer(
        self,
        healer_agent,
        batch_size: int = 10
    ) -> Dict[str, Any]:
        """Process pending entries with Self-Healing Agent.
        
        Args:
            healer_agent: SelfHealingAgent instance
            batch_size: Entries to process per batch
            
        Returns:
            Processing results
        """
        pending = self.get_pending(batch_size)
        
        if not pending:
            return {"processed": 0, "message": "No pending entries"}
        
        results = {
            "processed": 0,
            "resolved": 0,
            "failed": 0,
            "entries": []
        }
        
        for entry in pending:
            # Mark as analyzing
            self.update_status(entry.id, "analyzing")
            
            try:
                # Analyze with Self-Healing Agent
                from src.engine.message import TaskPayload
                
                analysis_result = await healer_agent.execute_task(TaskPayload(
                    action="analyze_error",
                    params={
                        "error_type": entry.error_type,
                        "error_message": entry.error_message,
                        "original_message": entry.original_message,
                        "agent_name": entry.agent_name
                    }
                ))
                
                if analysis_result.get("can_recover", False):
                    # Try recovery
                    self.update_status(
                        entry.id,
                        "resolved",
                        analysis_result
                    )
                    results["resolved"] += 1
                else:
                    self.update_status(
                        entry.id,
                        "failed",
                        analysis_result
                    )
                    results["failed"] += 1
                
                results["entries"].append({
                    "id": entry.id,
                    "status": "resolved" if analysis_result.get("can_recover") else "failed"
                })
                
            except Exception as e:
                logger.error(f"Failed to process DLQ entry {entry.id}: {e}")
                self.update_status(entry.id, "pending")  # Reset to pending
            
            results["processed"] += 1
        
        return results
    
    def clear_resolved(self, older_than_hours: int = 24) -> int:
        """Clear resolved entries older than threshold.
        
        Args:
            older_than_hours: Clear entries older than this
            
        Returns:
            Number of entries cleared
        """
        cutoff = datetime.utcnow() - __import__('datetime').timedelta(hours=older_than_hours)
        
        to_clear = [
            entry for entry in self._queue
            if entry.status in ["resolved", "failed"]
            and entry.resolved_at
            and datetime.fromisoformat(entry.resolved_at) < cutoff
        ]
        
        for entry in to_clear:
            self._queue.remove(entry)
        
        if to_clear:
            self._save()
        
        logger.info(f"Cleared {len(to_clear)} resolved entries from DLQ")
        return len(to_clear)


# Singleton instance
_dlq_instance: Optional[DeadLetterQueue] = None


def get_dead_letter_queue(storage_path: Optional[str] = None) -> DeadLetterQueue:
    """Get singleton DeadLetterQueue."""
    global _dlq_instance
    if _dlq_instance is None:
        _dlq_instance = DeadLetterQueue(storage_path)
    return _dlq_instance
