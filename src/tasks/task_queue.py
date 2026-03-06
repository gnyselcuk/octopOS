"""Task Queue (OctoQueue) - Persistent task management system.

This module implements the task queue that:
- Stores tasks persistently (SQLite or DynamoDB)
- Manages task status and lifecycle
- Handles recurring tasks
- Coordinates with the Scheduler
"""

import json
import sqlite3
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from src.utils.config import get_config
from src.utils.logger import get_logger

logger = get_logger()


class TaskPriority(Enum):
    """Task priority levels."""
    CRITICAL = 1
    HIGH = 3
    NORMAL = 5
    LOW = 7
    BACKGROUND = 9


class TaskState(Enum):
    """Task states."""
    PENDING = "pending"
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


@dataclass
class Task:
    """A task in the queue."""
    
    id: str
    title: str
    description: str
    agent_type: str  # Which agent should handle this
    action: str  # Action to perform
    params: Dict[str, Any]
    state: TaskState
    priority: TaskPriority
    created_at: str
    scheduled_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    parent_id: Optional[str] = None  # For subtasks
    retry_count: int = 0
    max_retries: int = 3
    recurrence: Optional[str] = None  # Cron expression for recurring tasks
    metadata: Optional[Dict[str, Any]] = None


class TaskQueue:
    """Persistent task queue for octopOS.
    
    Manages tasks with SQLite backend (local) or DynamoDB (cloud).
    Supports recurring tasks, priorities, and status tracking.
    
    Example:
        >>> queue = TaskQueue()
        >>> task_id = queue.create_task(
        ...     title="Process data",
        ...     agent_type="Worker",
        ...     action="process_file",
        ...     params={"file": "data.csv"}
        ... )
        >>> task = queue.get_task(task_id)
        >>> queue.update_task_state(task_id, TaskState.IN_PROGRESS)
    """
    
    def __init__(self, db_path: Optional[str] = None) -> None:
        """Initialize the task queue.
        
        Args:
            db_path: Path to SQLite database
        """
        self._config = get_config()
        self._db_path = db_path or self._config.task.db_path
        self._initialized = False
        
        logger.info(f"TaskQueue initialized with db: {self._db_path}")
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection."""
        db_path = Path(self._db_path).expanduser()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        return conn
    
    def initialize(self) -> None:
        """Initialize database tables."""
        if self._initialized:
            return
        
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # Create tasks table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT,
                    agent_type TEXT NOT NULL,
                    action TEXT NOT NULL,
                    params TEXT,
                    state TEXT NOT NULL,
                    priority INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    scheduled_at TEXT,
                    started_at TEXT,
                    completed_at TEXT,
                    result TEXT,
                    error TEXT,
                    parent_id TEXT,
                    retry_count INTEGER DEFAULT 0,
                    max_retries INTEGER DEFAULT 3,
                    recurrence TEXT,
                    metadata TEXT
                )
            """)
            
            # Create index on state for faster queries
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_tasks_state 
                ON tasks(state)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_tasks_priority 
                ON tasks(priority)
            """)
            
            conn.commit()
            conn.close()
            
            self._initialized = True
            logger.info("TaskQueue database initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize TaskQueue: {e}")
            raise
    
    def create_task(
        self,
        title: str,
        agent_type: str,
        action: str,
        description: str = "",
        params: Optional[Dict[str, Any]] = None,
        priority: TaskPriority = TaskPriority.NORMAL,
        scheduled_at: Optional[str] = None,
        parent_id: Optional[str] = None,
        recurrence: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Create a new task.
        
        Args:
            title: Task title
            agent_type: Agent type to handle task
            action: Action to perform
            description: Task description
            params: Action parameters
            priority: Task priority
            scheduled_at: Schedule time (ISO format)
            parent_id: Parent task ID (for subtasks)
            recurrence: Cron expression for recurring tasks
            metadata: Additional metadata
            
        Returns:
            Task ID
        """
        self.initialize()
        
        task_id = str(uuid4())
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO tasks (
                    id, title, description, agent_type, action, params,
                    state, priority, created_at, scheduled_at, parent_id,
                    recurrence, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                task_id,
                title,
                description,
                agent_type,
                action,
                json.dumps(params or {}),
                TaskState.PENDING.value,
                priority.value,
                datetime.utcnow().isoformat(),
                scheduled_at,
                parent_id,
                recurrence,
                json.dumps(metadata or {})
            ))
            
            conn.commit()
            logger.info(f"Created task: {task_id} - {title}")
            return task_id
            
        except Exception as e:
            logger.error(f"Failed to create task: {e}")
            raise
        finally:
            conn.close()
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """Get a task by ID.
        
        Args:
            task_id: Task ID
            
        Returns:
            Task or None
        """
        self.initialize()
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                "SELECT * FROM tasks WHERE id = ?",
                (task_id,)
            )
            row = cursor.fetchone()
            
            if row is None:
                return None
            
            return self._row_to_task(row)
            
        finally:
            conn.close()
    
    def update_task_state(
        self,
        task_id: str,
        state: TaskState,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None
    ) -> bool:
        """Update task state.
        
        Args:
            task_id: Task ID
            state: New state
            result: Task result (for completed tasks)
            error: Error message (for failed tasks)
            
        Returns:
            True if successful
        """
        self.initialize()
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Build update query based on state
            if state == TaskState.IN_PROGRESS:
                cursor.execute("""
                    UPDATE tasks 
                    SET state = ?, started_at = ?
                    WHERE id = ?
                """, (state.value, datetime.utcnow().isoformat(), task_id))
                
            elif state in [TaskState.COMPLETED, TaskState.FAILED]:
                cursor.execute("""
                    UPDATE tasks 
                    SET state = ?, completed_at = ?, result = ?, error = ?
                    WHERE id = ?
                """, (
                    state.value,
                    datetime.utcnow().isoformat(),
                    json.dumps(result) if result else None,
                    error,
                    task_id
                ))
                
                # Handle recurring tasks
                if state == TaskState.COMPLETED:
                    self._schedule_next_recurrence(task_id)
                    
            else:
                cursor.execute(
                    "UPDATE tasks SET state = ? WHERE id = ?",
                    (state.value, task_id)
                )
            
            conn.commit()
            logger.info(f"Updated task {task_id} to state: {state.value}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update task state: {e}")
            return False
        finally:
            conn.close()
    
    def _schedule_next_recurrence(self, task_id: str) -> None:
        """Schedule next occurrence of a recurring task."""
        task = self.get_task(task_id)
        if not task or not task.recurrence:
            return
        
        try:
            from croniter import croniter
            
            # Calculate next run time
            base_time = datetime.fromisoformat(task.scheduled_at or task.created_at)
            itr = croniter(task.recurrence, base_time)
            next_run = itr.get_next(datetime)
            
            # Create new task instance
            self.create_task(
                title=task.title,
                agent_type=task.agent_type,
                action=task.action,
                description=task.description,
                params=task.params,
                priority=task.priority,
                scheduled_at=next_run.isoformat(),
                recurrence=task.recurrence,
                metadata=task.metadata
            )
            
            logger.info(f"Scheduled next recurrence for task {task_id}")
            
        except Exception as e:
            logger.error(f"Failed to schedule recurrence: {e}")
    
    def get_pending_tasks(
        self,
        limit: int = 100,
        agent_type: Optional[str] = None
    ) -> List[Task]:
        """Get pending tasks ordered by priority.
        
        Args:
            limit: Maximum number of tasks
            agent_type: Filter by agent type
            
        Returns:
            List of pending tasks
        """
        self.initialize()
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            if agent_type:
                cursor.execute("""
                    SELECT * FROM tasks 
                    WHERE state = ? AND agent_type = ?
                    ORDER BY priority ASC, created_at ASC
                    LIMIT ?
                """, (TaskState.PENDING.value, agent_type, limit))
            else:
                cursor.execute("""
                    SELECT * FROM tasks 
                    WHERE state = ?
                    ORDER BY priority ASC, created_at ASC
                    LIMIT ?
                """, (TaskState.PENDING.value, limit))
            
            rows = cursor.fetchall()
            return [self._row_to_task(row) for row in rows]
            
        finally:
            conn.close()
    
    def get_scheduled_tasks(
        self,
        before: Optional[str] = None,
        limit: int = 100
    ) -> List[Task]:
        """Get scheduled tasks that are due.
        
        Args:
            before: Get tasks scheduled before this time
            limit: Maximum number of tasks
            
        Returns:
            List of scheduled tasks
        """
        self.initialize()
        
        before = before or datetime.utcnow().isoformat()
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT * FROM tasks 
                WHERE state = ? AND scheduled_at <= ?
                ORDER BY priority ASC, scheduled_at ASC
                LIMIT ?
            """, (TaskState.PENDING.value, before, limit))
            
            rows = cursor.fetchall()
            return [self._row_to_task(row) for row in rows]
            
        finally:
            conn.close()
    
    def retry_task(self, task_id: str) -> bool:
        """Retry a failed task.
        
        Args:
            task_id: Task ID
            
        Returns:
            True if retry scheduled
        """
        task = self.get_task(task_id)
        if not task:
            return False
        
        if task.retry_count >= task.max_retries:
            logger.warning(f"Task {task_id} exceeded max retries")
            return False
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                UPDATE tasks 
                SET state = ?, retry_count = retry_count + 1, error = NULL
                WHERE id = ?
            """, (TaskState.PENDING.value, task_id))
            
            conn.commit()
            logger.info(f"Task {task_id} queued for retry ({task.retry_count + 1}/{task.max_retries})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to retry task: {e}")
            return False
        finally:
            conn.close()
    
    def cancel_task(self, task_id: str) -> bool:
        """Cancel a pending or scheduled task.
        
        Args:
            task_id: Task ID
            
        Returns:
            True if cancelled
        """
        return self.update_task_state(task_id, TaskState.CANCELLED)
    
    def delete_task(self, task_id: str) -> bool:
        """Permanently delete a task.
        
        Args:
            task_id: Task ID
            
        Returns:
            True if deleted
        """
        self.initialize()
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            conn.commit()
            logger.info(f"Deleted task: {task_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete task: {e}")
            return False
        finally:
            conn.close()
    
    def get_task_stats(self) -> Dict[str, Any]:
        """Get task queue statistics.
        
        Returns:
            Statistics dictionary
        """
        self.initialize()
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Count by state
            cursor.execute("""
                SELECT state, COUNT(*) as count 
                FROM tasks 
                GROUP BY state
            """)
            state_counts = {row['state']: row['count'] for row in cursor.fetchall()}
            
            # Total count
            cursor.execute("SELECT COUNT(*) as total FROM tasks")
            total = cursor.fetchone()['total']
            
            # Recent completions
            cursor.execute("""
                SELECT COUNT(*) as recent 
                FROM tasks 
                WHERE completed_at > datetime('now', '-1 day')
            """)
            recent = cursor.fetchone()['recent']
            
            return {
                "total": total,
                "by_state": state_counts,
                "completed_last_24h": recent
            }
            
        finally:
            conn.close()
    
    def _row_to_task(self, row: sqlite3.Row) -> Task:
        """Convert database row to Task object."""
        return Task(
            id=row['id'],
            title=row['title'],
            description=row['description'] or "",
            agent_type=row['agent_type'],
            action=row['action'],
            params=json.loads(row['params'] or '{}'),
            state=TaskState(row['state']),
            priority=TaskPriority(row['priority']),
            created_at=row['created_at'],
            scheduled_at=row['scheduled_at'],
            started_at=row['started_at'],
            completed_at=row['completed_at'],
            result=json.loads(row['result']) if row['result'] else None,
            error=row['error'],
            parent_id=row['parent_id'],
            retry_count=row['retry_count'],
            max_retries=row['max_retries'],
            recurrence=row['recurrence'],
            metadata=json.loads(row['metadata']) if row['metadata'] else None
        )


# Singleton instance
_task_queue: Optional[TaskQueue] = None


def get_task_queue() -> TaskQueue:
    """Get the global TaskQueue instance.
    
    Returns:
        Singleton TaskQueue instance
    """
    global _task_queue
    if _task_queue is None:
        _task_queue = TaskQueue()
    return _task_queue