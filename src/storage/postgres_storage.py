"""
PostgreSQL storage implementation for task persistence.

This implementation stores task data in a PostgreSQL database.
Data persists across service restarts.
"""
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import logging
import json
import asyncio

from .base import TaskStorage, TaskData

logger = logging.getLogger(__name__)

# Import PostgreSQL library conditionally
try:
    import asyncpg
    POSTGRES_AVAILABLE = True
except ImportError:
    POSTGRES_AVAILABLE = False
    asyncpg = None
    logger.warning("`asyncpg` not installed. PostgreSQL storage will not be available.")


class PostgresStorage(TaskStorage):
    """
    PostgreSQL storage implementation.
    
    This implementation stores task data in a PostgreSQL database,
    providing persistence across service restarts.
    """
    
    # SQL schema for tasks table (base schema without new fields)
    CREATE_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS agent_tasks (
        task_id VARCHAR(255) PRIMARY KEY,
        status VARCHAR(50) NOT NULL,
        query TEXT NOT NULL,
        max_steps INTEGER NOT NULL,
        final_state VARCHAR(50),
        timestamp_dir TEXT,
        execution_statistics JSONB,
        sandbox_info JSONB,
        request_data JSONB,
        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMP NOT NULL DEFAULT NOW()
    );
    
    CREATE INDEX IF NOT EXISTS idx_agent_tasks_status ON agent_tasks(status);
    CREATE INDEX IF NOT EXISTS idx_agent_tasks_created_at ON agent_tasks(created_at);
    """
    
    # Migration SQL to add new columns for existing tables
    MIGRATION_SQL = [
        # Add finished_output column if not exists
        """
        DO $$ 
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name='agent_tasks' AND column_name='finished_output'
            ) THEN
                ALTER TABLE agent_tasks ADD COLUMN finished_output TEXT;
            END IF;
        END $$;
        """,
        # Add llm_context column if not exists
        """
        DO $$ 
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name='agent_tasks' AND column_name='llm_context'
            ) THEN
                ALTER TABLE agent_tasks ADD COLUMN llm_context JSONB;
            END IF;
        END $$;
        """,
        # Add cancel_requested column if not exists
        """
        DO $$ 
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name='agent_tasks' AND column_name='cancel_requested'
            ) THEN
                ALTER TABLE agent_tasks ADD COLUMN cancel_requested BOOLEAN DEFAULT FALSE;
            END IF;
        END $$;
        """,
        # Add cancelled_at column if not exists
        """
        DO $$ 
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name='agent_tasks' AND column_name='cancelled_at'
            ) THEN
                ALTER TABLE agent_tasks ADD COLUMN cancelled_at TIMESTAMP;
            END IF;
        END $$;
        """,
        # Create index on cancel_requested if not exists
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name='agent_tasks' AND column_name='cancel_requested'
            ) THEN
                CREATE INDEX IF NOT EXISTS idx_agent_tasks_cancel_requested ON agent_tasks(cancel_requested);
            END IF;
        END $$;
        """
    ]
    
    def __init__(self, connection_string: str):
        """
        Initialize PostgreSQL storage.
        
        Args:
            connection_string: PostgreSQL connection string
                Format: postgresql://user:password@host:port/database
        """
        if not POSTGRES_AVAILABLE:
            raise ImportError(
                "asyncpg is required for PostgreSQL storage. "
                "Install it with: pip install asyncpg"
            )
        
        self.connection_string = connection_string
        self._pool: Optional[asyncpg.Pool] = None
        self._initialized = False
        self._init_lock = asyncio.Lock()
        self._notification_listeners = {}  # task_id -> list of callbacks
        self._listener_connection: Optional[asyncpg.Connection] = None
        self._listener_task: Optional[asyncio.Task] = None
        logger.info("Initialized PostgresStorage for task persistence")
    
    async def _ensure_initialized(self):
        """Ensure database connection pool is initialized and schema is created."""
        if self._initialized:
            return
        
        async with self._init_lock:
            # Double-check after acquiring lock
            if self._initialized:
                return
            
            if not self._pool:
                try:
                    self._pool = await asyncpg.create_pool(
                        self.connection_string,
                        min_size=2,
                        max_size=10,
                        command_timeout=60
                    )
                    logger.info("PostgreSQL connection pool created")
                except Exception as e:
                    logger.error(f"Failed to create PostgreSQL connection pool: {e}")
                    raise
            
            # Create table if not exists
            try:
                async with self._pool.acquire() as conn:
                    await conn.execute(self.CREATE_TABLE_SQL)
                    logger.info("PostgreSQL schema initialized")
                    
                    # Run migrations to add new columns if they don't exist
                    for migration_sql in self.MIGRATION_SQL:
                        try:
                            await conn.execute(migration_sql)
                        except Exception as e:
                            logger.warning(f"Migration execution warning: {e}")
                    
                    logger.info("PostgreSQL schema migrations completed")
            except Exception as e:
                logger.error(f"Failed to initialize PostgreSQL schema: {e}")
                raise
            
            # Start LISTEN/NOTIFY listener for task cancellation
            try:
                await self._start_notification_listener()
            except Exception as e:
                logger.warning(f"Failed to start notification listener: {e}")
            
            self._initialized = True
    
    async def _column_exists(self, conn, column_name: str) -> bool:
        """Check if a column exists in agent_tasks table."""
        result = await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name='agent_tasks' AND column_name=$1
            )
            """,
            column_name
        )
        return result
    
    async def _start_notification_listener(self):
        """Start a dedicated connection for LISTEN/NOTIFY."""
        try:
            self._listener_connection = await asyncpg.connect(self.connection_string)
            await self._listener_connection.add_listener('task_cancel', self._handle_cancel_notification)
            logger.info("Started PostgreSQL NOTIFY listener for task cancellation")
        except Exception as e:
            logger.error(f"Failed to start NOTIFY listener: {e}")
            raise
    
    async def _handle_cancel_notification(self, connection, pid, channel, payload):
        """Handle incoming cancel notifications."""
        try:
            task_id = payload
            logger.info(f"Received cancel notification for task {task_id}")
            
            # Trigger any registered callbacks for this task
            if task_id in self._notification_listeners:
                for callback in self._notification_listeners[task_id]:
                    try:
                        if asyncio.iscoroutinefunction(callback):
                            await callback(task_id)
                        else:
                            callback(task_id)
                    except Exception as e:
                        logger.error(f"Error in cancel notification callback: {e}")
        except Exception as e:
            logger.error(f"Error handling cancel notification: {e}")
    
    def register_cancel_listener(self, task_id: str, callback):
        """Register a callback for cancel notifications on a specific task."""
        if task_id not in self._notification_listeners:
            self._notification_listeners[task_id] = []
        self._notification_listeners[task_id].append(callback)
        logger.debug(f"Registered cancel listener for task {task_id}")
    
    def unregister_cancel_listener(self, task_id: str, callback=None):
        """Unregister cancel listeners for a task."""
        if callback:
            if task_id in self._notification_listeners:
                self._notification_listeners[task_id].remove(callback)
        else:
            self._notification_listeners.pop(task_id, None)
        logger.debug(f"Unregistered cancel listener for task {task_id}")
    
    async def close(self):
        """Close the database connection pool."""
        if self._listener_connection:
            try:
                await self._listener_connection.close()
                self._listener_connection = None
                logger.info("PostgreSQL notification listener closed")
            except Exception as e:
                logger.error(f"Error closing notification listener: {e}")
        
        if self._pool:
            await self._pool.close()
            self._pool = None
            self._initialized = False
            logger.info("PostgreSQL connection pool closed")
    
    async def create_task(self, task_data: TaskData) -> bool:
        """
        Create a new task entry in PostgreSQL.
        
        Args:
            task_data: TaskData object containing task information
            
        Returns:
            bool: True if creation was successful
        """
        await self._ensure_initialized()
        
        try:
            async with self._pool.acquire() as conn:
                # Check which columns exist
                has_finished_output = await self._column_exists(conn, 'finished_output')
                has_llm_context = await self._column_exists(conn, 'llm_context')
                has_cancel_requested = await self._column_exists(conn, 'cancel_requested')
                has_cancelled_at = await self._column_exists(conn, 'cancelled_at')
                
                # Build dynamic INSERT statement based on available columns
                columns = [
                    'task_id', 'status', 'query', 'max_steps', 'final_state',
                    'timestamp_dir', 'execution_statistics', 'sandbox_info',
                    'request_data', 'created_at', 'updated_at'
                ]
                values = [
                    task_data.task_id,
                    task_data.status,
                    task_data.query,
                    task_data.max_steps,
                    task_data.final_state,
                    task_data.timestamp_dir,
                    json.dumps(task_data.execution_statistics) if task_data.execution_statistics else None,
                    json.dumps(task_data.sandbox_info) if task_data.sandbox_info else None,
                    json.dumps(task_data.request_data) if task_data.request_data else None,
                    task_data.created_at or datetime.now(),
                    task_data.updated_at or datetime.now()
                ]
                
                if has_finished_output:
                    columns.append('finished_output')
                    values.append(task_data.finished_output)
                
                if has_llm_context:
                    columns.append('llm_context')
                    values.append(json.dumps(task_data.llm_context) if task_data.llm_context else None)
                
                if has_cancel_requested:
                    columns.append('cancel_requested')
                    values.append(task_data.cancel_requested)
                
                if has_cancelled_at:
                    columns.append('cancelled_at')
                    values.append(task_data.cancelled_at)
                
                # Generate placeholders ($1, $2, ...)
                placeholders = ', '.join(f'${i+1}' for i in range(len(values)))
                
                query = f"""
                    INSERT INTO agent_tasks ({', '.join(columns)})
                    VALUES ({placeholders})
                """
                
                await conn.execute(query, *values)
                logger.debug(f"Created task {task_data.task_id} in PostgreSQL")
                return True
        except asyncpg.UniqueViolationError:
            logger.warning(f"Task {task_data.task_id} already exists in PostgreSQL")
            return False
        except Exception as e:
            logger.error(f"Failed to create task {task_data.task_id} in PostgreSQL: {e}")
            return False
    
    async def get_task(self, task_id: str) -> Optional[TaskData]:
        """
        Retrieve task data by task ID from PostgreSQL.
        
        Args:
            task_id: Unique identifier for the task
            
        Returns:
            TaskData if found, None otherwise
        """
        await self._ensure_initialized()
        
        try:
            async with self._pool.acquire() as conn:
                # Check which columns exist
                has_finished_output = await self._column_exists(conn, 'finished_output')
                has_llm_context = await self._column_exists(conn, 'llm_context')
                has_cancel_requested = await self._column_exists(conn, 'cancel_requested')
                has_cancelled_at = await self._column_exists(conn, 'cancelled_at')
                
                # Build dynamic SELECT statement
                columns = [
                    'task_id', 'status', 'query', 'max_steps', 'final_state',
                    'timestamp_dir', 'execution_statistics', 'sandbox_info',
                    'request_data', 'created_at', 'updated_at'
                ]
                
                if has_finished_output:
                    columns.append('finished_output')
                if has_llm_context:
                    columns.append('llm_context')
                if has_cancel_requested:
                    columns.append('cancel_requested')
                if has_cancelled_at:
                    columns.append('cancelled_at')
                
                query = f"""
                    SELECT {', '.join(columns)}
                    FROM agent_tasks WHERE task_id = $1
                """
                
                row = await conn.fetchrow(query, task_id)
                
                if not row:
                    return None
                
                # Convert row to TaskData
                task_data = TaskData(
                    task_id=row['task_id'],
                    status=row['status'],
                    query=row['query'],
                    max_steps=row['max_steps'],
                    final_state=row['final_state'],
                    timestamp_dir=row['timestamp_dir'],
                    execution_statistics=json.loads(row['execution_statistics']) if row['execution_statistics'] else None,
                    sandbox_info=json.loads(row['sandbox_info']) if row['sandbox_info'] else None,
                    request_data=json.loads(row['request_data']) if row['request_data'] else None,
                    finished_output=row.get('finished_output') if has_finished_output else None,
                    llm_context=json.loads(row['llm_context']) if has_llm_context and row.get('llm_context') else None,
                    cancel_requested=row.get('cancel_requested', False) if has_cancel_requested else False,
                    cancelled_at=row.get('cancelled_at') if has_cancelled_at else None,
                    created_at=row['created_at'],
                    updated_at=row['updated_at']
                )
                
                logger.debug(f"Retrieved task {task_id} from PostgreSQL")
                return task_data
        except Exception as e:
            logger.error(f"Failed to retrieve task {task_id} from PostgreSQL: {e}")
            return None
    
    async def update_task(self, task_id: str, updates: Dict[str, Any]) -> bool:
        """
        Update task data in PostgreSQL.
        
        Args:
            task_id: Unique identifier for the task
            updates: Dictionary of fields to update
            
        Returns:
            bool: True if update was successful
        """
        await self._ensure_initialized()
        
        # Build dynamic UPDATE query based on provided fields
        set_clauses = []
        values = []
        param_idx = 1
        
        allowed_update_fields = {
            'status', 'final_state', 'timestamp_dir',
            'execution_statistics', 'sandbox_info', 'request_data',
            'finished_output', 'llm_context', 'query', 'cancel_requested', 'cancelled_at'
        }
        
        for key, value in updates.items():
            if key in allowed_update_fields:
                set_clauses.append(f"{key} = ${param_idx}")
                
                # Serialize dicts to JSON for JSONB columns
                if key in ['execution_statistics', 'sandbox_info', 'request_data', 'llm_context'] and value is not None:
                    value = json.dumps(value)
                
                values.append(value)
                param_idx += 1
        
        if not set_clauses:
            logger.warning(f"No valid fields to update for task {task_id}")
            return False
        
        # Always update the updated_at timestamp
        set_clauses.append(f"updated_at = ${param_idx}")
        values.append(datetime.now())
        param_idx += 1
        
        # Add task_id as the last parameter for WHERE clause
        values.append(task_id)
        
        query = f"""
            UPDATE agent_tasks 
            SET {', '.join(set_clauses)}
            WHERE task_id = ${param_idx}
        """
        
        try:
            async with self._pool.acquire() as conn:
                result = await conn.execute(query, *values)
                
                # Check if any row was updated
                updated_count = int(result.split()[-1]) if result and result.startswith("UPDATE") else 0
                if updated_count == 0:
                    logger.warning(f"Task {task_id} not found for update in PostgreSQL")
                    return False
                
                logger.debug(f"Updated task {task_id} in PostgreSQL")
                return True
        except Exception as e:
            logger.error(f"Failed to update task {task_id} in PostgreSQL: {e}")
            return False
    
    async def delete_task(self, task_id: str) -> bool:
        """
        Delete a task entry from PostgreSQL.
        
        Args:
            task_id: Unique identifier for the task
            
        Returns:
            bool: True if deletion was successful
        """
        await self._ensure_initialized()
        
        try:
            async with self._pool.acquire() as conn:
                result = await conn.execute(
                    "DELETE FROM agent_tasks WHERE task_id = $1",
                    task_id
                )
                
                deleted_count = int(result.split()[-1]) if result and result.startswith("DELETE") else 0
                if deleted_count == 0:
                    logger.warning(f"Task {task_id} not found for deletion in PostgreSQL")
                    return False
                
                logger.debug(f"Deleted task {task_id} from PostgreSQL")
                return True
        except Exception as e:
            logger.error(f"Failed to delete task {task_id} from PostgreSQL: {e}")
            return False
    
    async def list_tasks(self, 
                        status: Optional[str] = None,
                        limit: Optional[int] = None,
                        offset: int = 0) -> List[TaskData]:
        """
        List tasks with optional filtering from PostgreSQL.
        
        Args:
            status: Filter by task status (optional)
            limit: Maximum number of tasks to return (optional)
            offset: Number of tasks to skip (for pagination)
            
        Returns:
            List of TaskData objects
        """
        await self._ensure_initialized()
        
        try:
            async with self._pool.acquire() as conn:
                # Check which columns exist
                has_finished_output = await self._column_exists(conn, 'finished_output')
                has_llm_context = await self._column_exists(conn, 'llm_context')
                has_cancel_requested = await self._column_exists(conn, 'cancel_requested')
                has_cancelled_at = await self._column_exists(conn, 'cancelled_at')
                
                # Build dynamic SELECT statement
                columns = [
                    'task_id', 'status', 'query', 'max_steps', 'final_state',
                    'timestamp_dir', 'execution_statistics', 'sandbox_info',
                    'request_data', 'created_at', 'updated_at'
                ]
                
                if has_finished_output:
                    columns.append('finished_output')
                if has_llm_context:
                    columns.append('llm_context')
                if has_cancel_requested:
                    columns.append('cancel_requested')
                if has_cancelled_at:
                    columns.append('cancelled_at')
                
                query = f"""
                    SELECT {', '.join(columns)}
                    FROM agent_tasks
                """
                
                params = []
                param_idx = 1
                
                if status:
                    query += f" WHERE status = ${param_idx}"
                    params.append(status)
                    param_idx += 1
                
                query += " ORDER BY created_at DESC"
                
                if limit:
                    query += f" LIMIT ${param_idx}"
                    params.append(limit)
                    param_idx += 1
                
                if offset > 0:
                    query += f" OFFSET ${param_idx}"
                    params.append(offset)
                
                rows = await conn.fetch(query, *params)
                
                tasks = []
                for row in rows:
                    task_data = TaskData(
                        task_id=row['task_id'],
                        status=row['status'],
                        query=row['query'],
                        max_steps=row['max_steps'],
                        final_state=row['final_state'],
                        timestamp_dir=row['timestamp_dir'],
                        execution_statistics=json.loads(row['execution_statistics']) if row['execution_statistics'] else None,
                        sandbox_info=json.loads(row['sandbox_info']) if row['sandbox_info'] else None,
                        request_data=json.loads(row['request_data']) if row['request_data'] else None,
                        finished_output=row.get('finished_output') if has_finished_output else None,
                        llm_context=json.loads(row['llm_context']) if has_llm_context and row.get('llm_context') else None,
                        cancel_requested=row.get('cancel_requested', False) if has_cancel_requested else False,
                        cancelled_at=row.get('cancelled_at') if has_cancelled_at else None,
                        created_at=row['created_at'],
                        updated_at=row['updated_at']
                    )
                    tasks.append(task_data)
                
                logger.debug(f"Listed {len(tasks)} tasks from PostgreSQL")
                return tasks
        except Exception as e:
            logger.error(f"Failed to list tasks from PostgreSQL: {e}")
            return []
    
    async def count_active_tasks(self) -> int:
        """
        Count tasks with status 'pending' or 'running' in PostgreSQL.
        
        Returns:
            Number of active tasks
        """
        await self._ensure_initialized()
        
        try:
            async with self._pool.acquire() as conn:
                count = await conn.fetchval(
                    """
                    SELECT COUNT(*) FROM agent_tasks 
                    WHERE status IN ('pending', 'running')
                    """
                )
                logger.debug(f"Counted {count} active tasks in PostgreSQL")
                return count or 0
        except Exception as e:
            logger.error(f"Failed to count active tasks in PostgreSQL: {e}")
            return 0
    
    async def cleanup_old_tasks(self, older_than_days: int) -> int:
        """
        Clean up old task records from PostgreSQL.
        
        Args:
            older_than_days: Delete tasks older than this many days
            
        Returns:
            Number of tasks deleted
        """
        await self._ensure_initialized()
        
        try:
            cutoff_date = datetime.now() - timedelta(days=older_than_days)
            
            async with self._pool.acquire() as conn:
                result = await conn.execute(
                    """
                    DELETE FROM agent_tasks 
                    WHERE created_at < $1 
                    AND status IN ('finished', 'error', 'cancelled')
                    """,
                    cutoff_date
                )
                
                # Parse result to get number of deleted rows
                deleted_count = int(result.split()[-1]) if result else 0
                
                logger.info(f"Cleaned up {deleted_count} old tasks from PostgreSQL")
                return deleted_count
        except Exception as e:
            logger.error(f"Failed to cleanup old tasks from PostgreSQL: {e}")
            return 0
    
    async def request_cancel_task(self, task_id: str) -> bool:
        """
        Request cancellation of a task (stateless operation).
        
        This method updates the database and sends a NOTIFY to all listening instances.
        
        Args:
            task_id: Unique identifier for the task to cancel
            
        Returns:
            bool: True if the cancellation request was recorded successfully
        """
        await self._ensure_initialized()
        
        try:
            async with self._pool.acquire() as conn:
                # Check if cancel_requested column exists
                has_cancel_requested = await self._column_exists(conn, 'cancel_requested')
                has_cancelled_at = await self._column_exists(conn, 'cancelled_at')
                
                if not has_cancel_requested:
                    logger.error(f"cancel_requested column does not exist, cannot cancel task {task_id}")
                    return False
                
                # First check if task exists and its current status
                current_status = await conn.fetchval(
                    "SELECT status FROM agent_tasks WHERE task_id = $1",
                    task_id
                )
                
                if current_status is None:
                    logger.warning(f"Task {task_id} not found")
                    return False
                
                # If already cancelled, return success (idempotent)
                if current_status == 'cancelled':
                    logger.info(f"Task {task_id} is already cancelled")
                    return True
                
                # If task is finished or errored, cannot cancel
                if current_status in ('finished', 'error'):
                    logger.warning(f"Task {task_id} is already {current_status}, cannot cancel")
                    return False
                
                # For pending/running tasks, update cancel_requested flag
                logger.debug(f"Task {task_id} is in '{current_status}' state, proceeding with cancellation")
                
                # Build UPDATE statement based on available columns
                set_clauses = ["cancel_requested = TRUE", "updated_at = $1"]
                params = [datetime.now()]
                param_idx = 2
                
                if has_cancelled_at:
                    set_clauses.append(f"cancelled_at = ${param_idx}")
                    params.append(datetime.now())
                    param_idx += 1
                
                params.append(task_id)
                
                query = f"""
                    UPDATE agent_tasks 
                    SET {', '.join(set_clauses)}
                    WHERE task_id = ${param_idx}
                    AND status IN ('pending', 'running')
                """
                
                result = await conn.execute(query, *params)
                
                updated_count = int(result.split()[-1]) if result and result.startswith("UPDATE") else 0
                logger.debug(f"Updated {updated_count} rows for task {task_id}")
                
                # Send NOTIFY to all listening instances
                # Note: NOTIFY doesn't support parameterized queries, must use string formatting
                await conn.execute(f"NOTIFY task_cancel, '{task_id}'")
                
                logger.info(f"Cancellation requested for task {task_id}")
                return True
        except Exception as e:
            logger.error(f"Failed to request cancellation for task {task_id}: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def check_cancel_requested(self, task_id: str) -> bool:
        """
        Check if cancellation has been requested for a task.
        
        This method queries the database to check the cancel_requested flag.
        
        Args:
            task_id: Unique identifier for the task
            
        Returns:
            bool: True if cancellation has been requested
        """
        await self._ensure_initialized()
        
        try:
            async with self._pool.acquire() as conn:
                cancel_requested = await conn.fetchval(
                    "SELECT cancel_requested FROM agent_tasks WHERE task_id = $1",
                    task_id
                )
                return cancel_requested if cancel_requested is not None else False
        except Exception as e:
            logger.error(f"Failed to check cancel status for task {task_id}: {e}")
            return False
