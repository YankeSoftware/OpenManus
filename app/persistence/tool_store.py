"""
Tool persistence store.

Handles storage and retrieval of tool definitions, implementation code,
and usage statistics.
"""

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from app.logger import logger
from app.persistence.db_manager import DatabaseManager


class ToolStore:
    """
    Store for tool persistence and usage tracking.
    
    Handles:
    - Storing and retrieving tool metadata
    - Managing tool implementation code
    - Tracking tool usage statistics
    """
    
    def __init__(self):
        """Initialize the tool store with a database connection."""
        self.db = DatabaseManager()
        self.config = self.db.config
        self.tool_dir = self.config.get("tool_integration.tool_storage_path", "data/tools")
        self._ensure_tool_directory()
        
    def _ensure_tool_directory(self):
        """Ensure the tool directory exists."""
        Path(self.tool_dir).mkdir(parents=True, exist_ok=True)
        
    def register_tool(self, 
                     name: str, 
                     description: str = None, 
                     implementation_path: str = None,
                     metadata: Dict = None) -> str:
        """
        Register a tool in the database.
        
        Args:
            name: Tool name
            description: Tool description
            implementation_path: Path to the tool implementation
            metadata: Additional tool metadata
            
        Returns:
            str: ID of the registered tool
        """
        tool_id = str(uuid.uuid4())
        timestamp = datetime.now()
        
        # Prepare metadata JSON if provided
        metadata_json = json.dumps(metadata) if metadata else None
        
        # Insert tool record in the database
        with self.db.transaction():
            self.db.execute(
                """
                INSERT INTO tools 
                (id, name, description, implementation_path, creation_date, last_modified, 
                is_active, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (tool_id, name, description, implementation_path, timestamp, timestamp,
                 True, metadata_json)
            )
        
        logger.info(f"Registered tool '{name}' with ID {tool_id}")
        return tool_id
        
    def save_tool_code(self, tool_id: str, code: str) -> str:
        """
        Save the tool implementation code to disk.
        
        Args:
            tool_id: Tool ID
            code: Tool implementation code
            
        Returns:
            str: Path to the saved code file
        """
        # Create tool-specific directory
        tool_dir = os.path.join(self.tool_dir, tool_id)
        Path(tool_dir).mkdir(parents=True, exist_ok=True)
        
        # Save code to file
        code_path = os.path.join(tool_dir, "tool.py")
        with open(code_path, 'w') as f:
            f.write(code)
            
        # Create __init__.py to make it importable
        init_path = os.path.join(tool_dir, "__init__.py")
        with open(init_path, 'w') as f:
            f.write("")
            
        # Update the implementation path in the database
        with self.db.transaction():
            self.db.execute(
                "UPDATE tools SET implementation_path = ?, last_modified = ? WHERE id = ?",
                (code_path, datetime.now(), tool_id)
            )
            
        return code_path
        
    def get_tool(self, tool_id: str) -> Optional[Dict]:
        """
        Get a tool by ID.
        
        Args:
            tool_id: Tool ID
            
        Returns:
            Optional[Dict]: Tool data or None if not found
        """
        result = self.db.fetchone(
            "SELECT * FROM tools WHERE id = ?",
            (tool_id,)
        )
        
        if not result:
            return None
            
        tool_data = dict(result)
        
        # Parse metadata JSON if it exists
        if tool_data.get('metadata'):
            try:
                tool_data['metadata'] = json.loads(tool_data['metadata'])
            except json.JSONDecodeError:
                logger.error(f"Failed to parse metadata for tool {tool_id}")
                tool_data['metadata'] = {}
                
        return tool_data
        
    def get_tool_by_name(self, name: str) -> Optional[Dict]:
        """
        Get a tool by name.
        
        Args:
            name: Tool name
            
        Returns:
            Optional[Dict]: Tool data or None if not found
        """
        result = self.db.fetchone(
            "SELECT * FROM tools WHERE name = ? AND is_active = 1",
            (name,)
        )
        
        if not result:
            return None
            
        tool_data = dict(result)
        
        # Parse metadata JSON if it exists
        if tool_data.get('metadata'):
            try:
                tool_data['metadata'] = json.loads(tool_data['metadata'])
            except json.JSONDecodeError:
                logger.error(f"Failed to parse metadata for tool {name}")
                tool_data['metadata'] = {}
                
        return tool_data
        
    def get_tool_code(self, tool_id: str) -> Optional[str]:
        """
        Get the implementation code for a tool.
        
        Args:
            tool_id: Tool ID
            
        Returns:
            Optional[str]: Tool implementation code or None if not found
        """
        tool_data = self.get_tool(tool_id)
        if not tool_data or not tool_data.get('implementation_path'):
            return None
            
        try:
            with open(tool_data['implementation_path'], 'r') as f:
                return f.read()
        except FileNotFoundError:
            logger.error(f"Tool code file not found for tool {tool_id}")
            return None
            
    def update_tool(self, 
                   tool_id: str, 
                   name: str = None,
                   description: str = None,
                   is_active: bool = None,
                   metadata: Dict = None) -> bool:
        """
        Update an existing tool.
        
        Args:
            tool_id: Tool ID
            name: New tool name
            description: New tool description
            is_active: New active status
            metadata: New tool metadata
            
        Returns:
            bool: Success status
        """
        # Get current tool data
        tool_data = self.get_tool(tool_id)
        if not tool_data:
            logger.error(f"Tool {tool_id} not found for update")
            return False
            
        # Prepare update fields
        update_fields = {}
        
        if name is not None:
            update_fields['name'] = name
            
        if description is not None:
            update_fields['description'] = description
            
        if is_active is not None:
            update_fields['is_active'] = 1 if is_active else 0
            
        if metadata is not None:
            update_fields['metadata'] = json.dumps(metadata)
            
        if not update_fields:
            logger.warning(f"No updates provided for tool {tool_id}")
            return True
            
        # Add last_modified timestamp
        update_fields['last_modified'] = datetime.now()
        
        # Build SQL query
        field_updates = ", ".join([f"{key} = ?" for key in update_fields])
        query = f"UPDATE tools SET {field_updates} WHERE id = ?"
        
        # Execute update
        with self.db.transaction():
            self.db.execute(
                query,
                list(update_fields.values()) + [tool_id]
            )
            
        logger.info(f"Updated tool {tool_id}")
        return True
        
    def list_tools(self, active_only: bool = True) -> List[Dict]:
        """
        List all tools.
        
        Args:
            active_only: Whether to return only active tools
            
        Returns:
            List[Dict]: List of tool data dictionaries
        """
        query = "SELECT * FROM tools"
        params = []
        
        if active_only:
            query += " WHERE is_active = 1"
            
        # Execute query
        results = self.db.fetchall(query, params)
        
        # Process results
        tools = []
        for result in results:
            tool_data = dict(result)
            
            # Parse metadata JSON if it exists
            if tool_data.get('metadata'):
                try:
                    tool_data['metadata'] = json.loads(tool_data['metadata'])
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse metadata for tool {tool_data['id']}")
                    tool_data['metadata'] = {}
                    
            tools.append(tool_data)
            
        return tools
        
    def delete_tool(self, tool_id: str) -> bool:
        """
        Delete a tool by ID.
        
        Args:
            tool_id: Tool ID
            
        Returns:
            bool: Success status
        """
        # Get tool data first
        tool_data = self.get_tool(tool_id)
        if not tool_data:
            logger.error(f"Tool {tool_id} not found for deletion")
            return False
            
        # Begin transaction
        with self.db.transaction():
            # Mark tool as inactive rather than deleting
            self.db.execute(
                "UPDATE tools SET is_active = 0 WHERE id = ?",
                (tool_id,)
            )
            
        logger.info(f"Marked tool {tool_id} ({tool_data['name']}) as inactive")
        return True
        
    def record_tool_usage(self, agent_id: str, tool_id: str, success: bool, execution_time: float) -> bool:
        """
        Record tool usage statistics.
        
        Args:
            agent_id: Agent ID using the tool
            tool_id: Tool ID
            success: Whether the usage was successful
            execution_time: Execution time in seconds
            
        Returns:
            bool: Success status
        """
        # Get existing stats
        stats = self.db.fetchone(
            "SELECT * FROM tool_usage_stats WHERE agent_id = ? AND tool_id = ?",
            (agent_id, tool_id)
        )
        
        now = datetime.now()
        
        if stats:
            # Update existing stats
            usage_count = stats['usage_count'] + 1
            success_count = stats['success_count'] + (1 if success else 0)
            failure_count = stats['failure_count'] + (0 if success else 1)
            
            # Calculate new average execution time
            current_avg = stats['average_execution_time'] or 0
            new_avg = ((current_avg * (usage_count - 1)) + execution_time) / usage_count
            
            # Update record
            with self.db.transaction():
                self.db.execute(
                    """
                    UPDATE tool_usage_stats SET 
                    usage_count = ?, success_count = ?, failure_count = ?,
                    average_execution_time = ?, last_used = ?
                    WHERE agent_id = ? AND tool_id = ?
                    """,
                    (usage_count, success_count, failure_count, new_avg, now, agent_id, tool_id)
                )
        else:
            # Create new stats record
            with self.db.transaction():
                self.db.execute(
                    """
                    INSERT INTO tool_usage_stats
                    (agent_id, tool_id, usage_count, success_count, failure_count,
                    average_execution_time, last_used)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (agent_id, tool_id, 1, 1 if success else 0, 0 if success else 1,
                    execution_time, now)
                )
                
        return True
        
    def get_tool_usage_stats(self, agent_id: Optional[str] = None, tool_id: Optional[str] = None) -> List[Dict]:
        """
        Get tool usage statistics.
        
        Args:
            agent_id: Optional agent ID filter
            tool_id: Optional tool ID filter
            
        Returns:
            List[Dict]: Tool usage statistics
        """
        query = "SELECT * FROM tool_usage_stats"
        params = []
        where_clauses = []
        
        if agent_id:
            where_clauses.append("agent_id = ?")
            params.append(agent_id)
            
        if tool_id:
            where_clauses.append("tool_id = ?")
            params.append(tool_id)
            
        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)
            
        # Add sorting
        query += " ORDER BY usage_count DESC"
        
        # Execute query
        results = self.db.fetchall(query, params)
        
        # Process results
        return [dict(row) for row in results] 