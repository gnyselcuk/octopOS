"""Scheduler - Task scheduling and cron job management for octopOS.

This module implements the Scheduler that:
- Manages recurring tasks using APScheduler
- Integrates with TaskQueue for persistence
- Supports cron expressions for complex schedules
- Triggers tasks at specified intervals
"""

import asyncio
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
from uuid import UUID, uuid4

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from croniter import croniter

from src.engine.message import MessageType, OctoMessage, TaskPayload, get_message_queue
from src.tasks.task_queue import TaskQueue, TaskState
from src.utils.config import get_config
from src.utils.logger import get_logger

logger = get_logger()


class ScheduledJob:
    """A scheduled job configuration."""
    
    def __init__(
        self,
        job_id: str,
        task_id: str,
        agent_type: str,
        action: str,
        params: Dict[str, Any],
        schedule_type: str,  # "cron", "interval", "date"
        schedule_expr: str,  # cron expression or interval seconds
        enabled: bool = True,
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.job_id = job_id
        self.task_id = task_id
        self.agent_type = agent_type
        self.action = action
        self.params = params
        self.schedule_type = schedule_type
        self.schedule_expr = schedule_expr
        self.enabled = enabled
        self.metadata = metadata or {}
        self.last_run: Optional[str] = None
        self.next_run: Optional[str] = None
        self.run_count: int = 0


class Scheduler:
    """Task scheduler for recurring and scheduled tasks.
    
    Manages scheduled jobs using APScheduler with persistent storage.
    Integrates with the TaskQueue for task execution.
    
    Example:
        >>> scheduler = Scheduler()
        >>> await scheduler.start()
        >>> job_id = await scheduler.schedule_cron(
        ...     agent_type="Worker",
        ...     action="check_logs",
        ...     params={"path": "/var/log"},
        ...     cron_expr="0 */6 * * *"  # Every 6 hours
        ... )
    """
    
    def __init__(self, task_queue: Optional[TaskQueue] = None) -> None:
        """Initialize the scheduler.
        
        Args:
            task_queue: TaskQueue instance for persistence
        """
        self._config = get_config()
        self._task_queue = task_queue or TaskQueue()
        self._scheduler: Optional[AsyncIOScheduler] = None
        self._jobs: Dict[str, ScheduledJob] = {}
        self._running = False
        
        logger.info("Scheduler initialized")
    
    async def start(self) -> None:
        """Start the scheduler."""
        if self._running:
            return
        
        try:
            # Create async scheduler
            self._scheduler = AsyncIOScheduler()
            
            # Add event listeners
            self._scheduler.add_listener(
                self._on_job_executed,
                EVENT_JOB_EXECUTED
            )
            self._scheduler.add_listener(
                self._on_job_error,
                EVENT_JOB_ERROR
            )
            
            # Start the scheduler
            self._scheduler.start()
            self._running = True
            
            # Load existing scheduled jobs from database
            await self._load_scheduled_jobs()
            
            logger.info("Scheduler started successfully")
            
        except Exception as e:
            logger.error(f"Failed to start scheduler: {e}")
            raise
    
    async def stop(self) -> None:
        """Stop the scheduler."""
        if not self._running or not self._scheduler:
            return
        
        try:
            self._scheduler.shutdown(wait=True)
            self._running = False
            logger.info("Scheduler stopped")
        except Exception as e:
            logger.error(f"Error stopping scheduler: {e}")
    
    async def schedule_cron(
        self,
        agent_type: str,
        action: str,
        params: Dict[str, Any],
        cron_expr: str,
        job_id: Optional[str] = None,
        title: Optional[str] = None
    ) -> str:
        """Schedule a task with a cron expression.
        
        Args:
            agent_type: Type of agent to handle the task
            action: Action to perform
            params: Parameters for the action
            cron_expr: Cron expression (e.g., "0 */6 * * *")
            job_id: Optional job ID (generated if not provided)
            title: Optional task title
            
        Returns:
            Job ID
            
        Raises:
            ValueError: If cron expression is invalid
        """
        # Validate cron expression
        if not croniter.is_valid(cron_expr):
            raise ValueError(f"Invalid cron expression: {cron_expr}")
        
        job_id = job_id or str(uuid4())
        
        # Create task in queue
        task_id = self._task_queue.create_task(
            title=title or f"Scheduled: {action}",
            description=f"Cron: {cron_expr}",
            agent_type=agent_type,
            action=action,
            params=params,
            recurrence=cron_expr
        )
        
        # Create scheduled job
        job = ScheduledJob(
            job_id=job_id,
            task_id=task_id,
            agent_type=agent_type,
            action=action,
            params=params,
            schedule_type="cron",
            schedule_expr=cron_expr
        )
        
        # Add to APScheduler
        trigger = CronTrigger.from_crontab(cron_expr)
        self._scheduler.add_job(
            func=self._execute_scheduled_task,
            trigger=trigger,
            id=job_id,
            args=[job_id],
            replace_existing=True
        )
        
        self._jobs[job_id] = job
        
        logger.info(f"Scheduled cron job {job_id}: {cron_expr}")
        return job_id
    
    async def schedule_interval(
        self,
        agent_type: str,
        action: str,
        params: Dict[str, Any],
        seconds: int = 0,
        minutes: int = 0,
        hours: int = 0,
        days: int = 0,
        job_id: Optional[str] = None,
        title: Optional[str] = None
    ) -> str:
        """Schedule a task to run at intervals.
        
        Args:
            agent_type: Type of agent to handle the task
            action: Action to perform
            params: Parameters for the action
            seconds: Interval in seconds
            minutes: Interval in minutes
            hours: Interval in hours
            days: Interval in days
            job_id: Optional job ID
            title: Optional task title
            
        Returns:
            Job ID
        """
        job_id = job_id or str(uuid4())
        
        # Create task in queue
        interval_desc = f"{days}d {hours}h {minutes}m {seconds}s"
        task_id = self._task_queue.create_task(
            title=title or f"Scheduled: {action}",
            description=f"Interval: {interval_desc}",
            agent_type=agent_type,
            action=action,
            params=params,
            recurrence=f"interval:{seconds + minutes*60 + hours*3600 + days*86400}"
        )
        
        # Create scheduled job
        job = ScheduledJob(
            job_id=job_id,
            task_id=task_id,
            agent_type=agent_type,
            action=action,
            params=params,
            schedule_type="interval",
            schedule_expr=str(seconds + minutes*60 + hours*3600 + days*86400)
        )
        
        # Add to APScheduler
        self._scheduler.add_job(
            func=self._execute_scheduled_task,
            trigger=IntervalTrigger(
                seconds=seconds,
                minutes=minutes,
                hours=hours,
                days=days
            ),
            id=job_id,
            args=[job_id],
            replace_existing=True
        )
        
        self._jobs[job_id] = job
        
        logger.info(f"Scheduled interval job {job_id}: {interval_desc}")
        return job_id
    
    async def schedule_once(
        self,
        agent_type: str,
        action: str,
        params: Dict[str, Any],
        run_at: datetime,
        job_id: Optional[str] = None,
        title: Optional[str] = None
    ) -> str:
        """Schedule a one-time task.
        
        Args:
            agent_type: Type of agent to handle the task
            action: Action to perform
            params: Parameters for the action
            run_at: When to run the task
            job_id: Optional job ID
            title: Optional task title
            
        Returns:
            Job ID
        """
        job_id = job_id or str(uuid4())
        
        # Create task in queue
        task_id = self._task_queue.create_task(
            title=title or f"One-time: {action}",
            description=f"Run at: {run_at.isoformat()}",
            agent_type=agent_type,
            action=action,
            params=params,
            scheduled_at=run_at.isoformat()
        )
        
        # Create scheduled job
        job = ScheduledJob(
            job_id=job_id,
            task_id=task_id,
            agent_type=agent_type,
            action=action,
            params=params,
            schedule_type="date",
            schedule_expr=run_at.isoformat()
        )
        
        # Add to APScheduler
        self._scheduler.add_job(
            func=self._execute_scheduled_task,
            trigger=DateTrigger(run_date=run_at),
            id=job_id,
            args=[job_id],
            replace_existing=True
        )
        
        self._jobs[job_id] = job
        
        logger.info(f"Scheduled one-time job {job_id} at {run_at}")
        return job_id
    
    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a scheduled job.
        
        Args:
            job_id: ID of the job to cancel
            
        Returns:
            True if cancelled successfully
        """
        try:
            if job_id in self._jobs:
                job = self._jobs[job_id]
                job.enabled = False
                
                # Remove from scheduler
                self._scheduler.remove_job(job_id)
                
                # Cancel task in queue
                self._task_queue.cancel_task(job.task_id)
                
                del self._jobs[job_id]
                
                logger.info(f"Cancelled scheduled job: {job_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error cancelling job {job_id}: {e}")
            return False
    
    def get_job(self, job_id: str) -> Optional[ScheduledJob]:
        """Get a scheduled job by ID.
        
        Args:
            job_id: Job ID
            
        Returns:
            ScheduledJob or None
        """
        return self._jobs.get(job_id)
    
    def list_jobs(self) -> List[ScheduledJob]:
        """List all scheduled jobs.
        
        Returns:
            List of ScheduledJob objects
        """
        return list(self._jobs.values())
    
    async def pause_job(self, job_id: str) -> bool:
        """Pause a scheduled job.
        
        Args:
            job_id: Job ID to pause
            
        Returns:
            True if paused successfully
        """
        try:
            if job_id in self._jobs:
                self._scheduler.pause_job(job_id)
                self._jobs[job_id].enabled = False
                logger.info(f"Paused job: {job_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error pausing job {job_id}: {e}")
            return False
    
    async def resume_job(self, job_id: str) -> bool:
        """Resume a paused job.
        
        Args:
            job_id: Job ID to resume
            
        Returns:
            True if resumed successfully
        """
        try:
            if job_id in self._jobs:
                self._scheduler.resume_job(job_id)
                self._jobs[job_id].enabled = True
                logger.info(f"Resumed job: {job_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error resuming job {job_id}: {e}")
            return False
    
    async def _execute_scheduled_task(self, job_id: str) -> None:
        """Execute a scheduled task.
        
        This is called by APScheduler when a job triggers.
        
        Args:
            job_id: ID of the job to execute
        """
        if job_id not in self._jobs:
            logger.error(f"Job {job_id} not found")
            return
        
        job = self._jobs[job_id]
        job.last_run = datetime.utcnow().isoformat()
        job.run_count += 1
        
        try:
            # Update task state
            self._task_queue.update_task_state(job.task_id, TaskState.IN_PROGRESS)
            
            # Send message to appropriate agent
            message_queue = get_message_queue()
            
            task_payload = TaskPayload(
                action=job.action,
                params=job.params,
                task_id=job.task_id
            )
            
            message = OctoMessage.create_task(
                sender="Scheduler",
                receiver=job.agent_type,
                task_payload=task_payload
            )
            
            await message_queue.send(message)
            
            logger.info(f"Executed scheduled job {job_id}: {job.action}")
            
        except Exception as e:
            logger.error(f"Error executing scheduled job {job_id}: {e}")
            self._task_queue.update_task_state(
                job.task_id,
                TaskState.FAILED,
                error=str(e)
            )
    
    def _on_job_executed(self, event: Any) -> None:
        """Handle job execution success.
        
        Args:
            event: APScheduler job event
        """
        job_id = event.job_id
        if job_id in self._jobs:
            logger.debug(f"Job {job_id} executed successfully")
    
    def _on_job_error(self, event: Any) -> None:
        """Handle job execution error.
        
        Args:
            event: APScheduler job event
        """
        job_id = event.job_id
        if job_id in self._jobs:
            job = self._jobs[job_id]
            error = str(event.exception) if event.exception else "Unknown error"
            logger.error(f"Job {job_id} failed: {error}")
            self._task_queue.update_task_state(job.task_id, TaskState.FAILED, error=error)
    
    async def _load_scheduled_jobs(self) -> None:
        """Load scheduled jobs from persistent storage."""
        try:
            # Get scheduled tasks from task queue
            scheduled_tasks = self._task_queue.list_tasks(
                state=TaskState.SCHEDULED
            )
            
            for task in scheduled_tasks:
                if task.recurrence:
                    # Determine schedule type
                    if task.recurrence.startswith("interval:"):
                        seconds = int(task.recurrence.split(":")[1])
                        await self.schedule_interval(
                            agent_type=task.agent_type,
                            action=task.action,
                            params=task.params,
                            seconds=seconds,
                            job_id=f"restored_{task.id}",
                            title=task.title
                        )
                    elif croniter.is_valid(task.recurrence):
                        await self.schedule_cron(
                            agent_type=task.agent_type,
                            action=task.action,
                            params=task.params,
                            cron_expr=task.recurrence,
                            job_id=f"restored_{task.id}",
                            title=task.title
                        )
            
            logger.info(f"Loaded {len(scheduled_tasks)} scheduled jobs from storage")
            
        except Exception as e:
            logger.error(f"Error loading scheduled jobs: {e}")


# Global scheduler instance
_scheduler_instance: Optional[Scheduler] = None


def get_scheduler() -> Scheduler:
    """Get the global scheduler instance.
    
    Returns:
        Scheduler instance
    """
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = Scheduler()
    return _scheduler_instance
