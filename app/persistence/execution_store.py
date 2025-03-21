"""
Execution history persistence store.

Handles storage and retrieval of agent execution sessions, execution steps,
and execution metrics.
"""

import json
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from app.logger import logger
from app.persistence.db_manager import DatabaseManager


class ExecutionStore:
    """
    Store for execution history and metrics.
    
    Handles:
    - Storing execution sessions and steps
    - Tracking execution metrics
    - Retrieving execution history
    """
    
    def __init__(self):
        """Initialize the execution store with a database connection."""
        self.db = DatabaseManager()
        
    def create_session(self, 
                      agent_id: str, 
                      request: str, 
                      metadata: Optional[Dict] = None) -> str:
        """
        Create a new execution session.
        
        Args:
            agent_id: Agent ID executing the session
            request: The initial request
            metadata: Additional session metadata
            
        Returns:
            str: Session ID
        """
        session_id = str(uuid.uuid4())
        timestamp = datetime.now()
        
        # Prepare metadata JSON if provided
        metadata_json = json.dumps(metadata) if metadata else None
        
        # Insert session record
        with self.db.transaction():
            self.db.execute(
                """
                INSERT INTO execution_sessions 
                (id, agent_id, start_time, status, request, metadata)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (session_id, agent_id, timestamp, "started", request, metadata_json)
            )
            
        logger.info(f"Created execution session {session_id} for agent {agent_id}")
        return session_id
        
    def add_execution_step(self,
                          session_id: str,
                          agent_id: str,
                          step_number: int,
                          tool_id: Optional[str] = None,
                          input_data: Optional[Dict] = None,
                          output_data: Optional[Dict] = None,
                          status: str = "completed",
                          error: Optional[str] = None) -> str:
        """
        Add an execution step to a session.
        
        Args:
            session_id: Session ID
            agent_id: Agent ID
            step_number: Step number in sequence
            tool_id: Optional tool ID used in the step
            input_data: Input data for the step
            output_data: Output data from the step
            status: Step status
            error: Optional error message
            
        Returns:
            str: Step ID
        """
        step_id = str(uuid.uuid4())
        start_time = datetime.now()
        
        # Prepare input/output JSON
        input_json = json.dumps(input_data) if input_data else None
        output_json = json.dumps(output_data) if output_data else None
        
        # Insert step record
        with self.db.transaction():
            self.db.execute(
                """
                INSERT INTO execution_steps 
                (id, session_id, agent_id, step_number, tool_id, input, output, 
                start_time, end_time, status, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (step_id, session_id, agent_id, step_number, tool_id, input_json, 
                output_json, start_time, datetime.now(), status, error)
            )
            
        logger.info(f"Added execution step {step_number} to session {session_id}")
        return step_id
        
    def update_step_status(self,
                          step_id: str,
                          status: str,
                          output_data: Optional[Dict] = None,
                          error: Optional[str] = None) -> bool:
        """
        Update the status of an execution step.
        
        Args:
            step_id: Step ID
            status: New status
            output_data: Updated output data
            error: Updated error message
            
        Returns:
            bool: Success status
        """
        # Prepare update fields
        update_fields = {"status": status, "end_time": datetime.now()}
        
        if output_data is not None:
            update_fields["output"] = json.dumps(output_data)
            
        if error is not None:
            update_fields["error"] = error
            
        # Build SQL query
        field_updates = ", ".join([f"{key} = ?" for key in update_fields])
        query = f"UPDATE execution_steps SET {field_updates} WHERE id = ?"
        
        # Execute update
        with self.db.transaction():
            self.db.execute(
                query,
                list(update_fields.values()) + [step_id]
            )
            
        logger.info(f"Updated execution step {step_id} status to {status}")
        return True
        
    def complete_session(self,
                        session_id: str,
                        status: str = "completed",
                        summary: Optional[str] = None) -> bool:
        """
        Mark an execution session as complete.
        
        Args:
            session_id: Session ID
            status: Final status
            summary: Optional execution summary
            
        Returns:
            bool: Success status
        """
        # Prepare update fields
        update_fields = {
            "status": status,
            "end_time": datetime.now(),
        }
        
        if summary is not None:
            update_fields["summary"] = summary
            
        # Build SQL query
        field_updates = ", ".join([f"{key} = ?" for key in update_fields])
        query = f"UPDATE execution_sessions SET {field_updates} WHERE id = ?"
        
        # Execute update
        with self.db.transaction():
            self.db.execute(
                query,
                list(update_fields.values()) + [session_id]
            )
            
        logger.info(f"Completed execution session {session_id} with status {status}")
        return True
        
    def get_session(self, session_id: str) -> Optional[Dict]:
        """
        Get an execution session by ID.
        
        Args:
            session_id: Session ID
            
        Returns:
            Optional[Dict]: Session data or None if not found
        """
        result = self.db.fetchone(
            "SELECT * FROM execution_sessions WHERE id = ?",
            (session_id,)
        )
        
        if not result:
            return None
            
        session_data = dict(result)
        
        # Parse metadata JSON if it exists
        if session_data.get('metadata'):
            try:
                session_data['metadata'] = json.loads(session_data['metadata'])
            except json.JSONDecodeError:
                logger.error(f"Failed to parse metadata for session {session_id}")
                session_data['metadata'] = {}
                
        return session_data
        
    def get_session_steps(self, session_id: str) -> List[Dict]:
        """
        Get all steps for an execution session.
        
        Args:
            session_id: Session ID
            
        Returns:
            List[Dict]: List of step data
        """
        results = self.db.fetchall(
            "SELECT * FROM execution_steps WHERE session_id = ? ORDER BY step_number",
            (session_id,)
        )
        
        steps = []
        for result in results:
            step_data = dict(result)
            
            # Parse input/output JSON if they exist
            if step_data.get('input'):
                try:
                    step_data['input'] = json.loads(step_data['input'])
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse input for step {step_data['id']}")
                    step_data['input'] = {}
                    
            if step_data.get('output'):
                try:
                    step_data['output'] = json.loads(step_data['output'])
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse output for step {step_data['id']}")
                    step_data['output'] = {}
                    
            steps.append(step_data)
            
        return steps
        
    def get_agent_sessions(self, agent_id: str, limit: int = 20) -> List[Dict]:
        """
        Get recent execution sessions for an agent.
        
        Args:
            agent_id: Agent ID
            limit: Maximum number of sessions to return
            
        Returns:
            List[Dict]: List of session data
        """
        results = self.db.fetchall(
            "SELECT * FROM execution_sessions WHERE agent_id = ? ORDER BY start_time DESC LIMIT ?",
            (agent_id, limit)
        )
        
        sessions = []
        for result in results:
            session_data = dict(result)
            
            # Parse metadata JSON if it exists
            if session_data.get('metadata'):
                try:
                    session_data['metadata'] = json.loads(session_data['metadata'])
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse metadata for session {session_data['id']}")
                    session_data['metadata'] = {}
                    
            sessions.append(session_data)
            
        return sessions
        
    def delete_session(self, session_id: str) -> bool:
        """
        Delete an execution session and all its steps.
        
        Args:
            session_id: Session ID
            
        Returns:
            bool: Success status
        """
        # Begin transaction
        with self.db.transaction():
            # Delete steps first (foreign key constraint)
            self.db.execute("DELETE FROM execution_steps WHERE session_id = ?", (session_id,))
            
            # Delete session
            self.db.execute("DELETE FROM execution_sessions WHERE id = ?", (session_id,))
            
        logger.info(f"Deleted execution session {session_id} and all its steps")
        return True
        
    def get_execution_metrics(self, agent_id: Optional[str] = None, 
                             days: int = 30) -> Dict:
        """
        Get execution metrics.
        
        Args:
            agent_id: Optional agent ID to filter metrics
            days: Number of days to include in metrics
            
        Returns:
            Dict: Execution metrics
        """
        # Calculate date cutoff
        from datetime import timedelta
        cutoff_date = datetime.now() - timedelta(days=days)
        
        # Base query condition
        condition = "start_time >= ?"
        params = [cutoff_date]
        
        # Add agent filter if specified
        if agent_id:
            condition += " AND agent_id = ?"
            params.append(agent_id)
            
        # Get session stats
        session_stats = self.db.fetchone(
            f"""
            SELECT 
                COUNT(*) as total_sessions,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed_sessions,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed_sessions,
                AVG(JULIANDAY(end_time) - JULIANDAY(start_time)) * 86400 as avg_duration_seconds
            FROM execution_sessions
            WHERE {condition}
            """,
            params
        )
        
        # Get step stats
        step_stats = self.db.fetchone(
            f"""
            SELECT 
                COUNT(*) as total_steps,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed_steps,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed_steps,
                AVG(JULIANDAY(end_time) - JULIANDAY(start_time)) * 86400 as avg_step_duration_seconds
            FROM execution_steps
            WHERE {condition}
            """,
            params
        )
        
        # Get tool usage stats
        tool_usage = self.db.fetchall(
            f"""
            SELECT 
                tool_id, 
                COUNT(*) as usage_count,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as success_count,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failure_count
            FROM execution_steps
            WHERE {condition} AND tool_id IS NOT NULL
            GROUP BY tool_id
            ORDER BY usage_count DESC
            """,
            params
        )
        
        # Compile metrics
        metrics = {
            "sessions": dict(session_stats) if session_stats else {},
            "steps": dict(step_stats) if step_stats else {},
            "tool_usage": [dict(row) for row in tool_usage],
            "time_period_days": days
        }
        
        if agent_id:
            metrics["agent_id"] = agent_id
            
        return metrics 