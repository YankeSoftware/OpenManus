"""
Agent memory persistence store.

Handles storage and retrieval of agent memory items, including key-value data,
access statistics, and expiration management.
"""

import json
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union

from app.logger import logger
from app.persistence.db_manager import DatabaseManager


class MemoryStore:
    """
    Store for agent memory persistence.
    
    Handles:
    - Storing and retrieving agent memory items
    - Memory item expiration and access tracking
    - Memory management and querying
    """
    
    def __init__(self):
        """Initialize the memory store with a database connection."""
        self.db = DatabaseManager()
        
    def store(self, 
             agent_id: str, 
             key: str, 
             value: Any,
             expiry_seconds: Optional[int] = None) -> str:
        """
        Store a memory item.
        
        Args:
            agent_id: Agent ID
            key: Memory key
            value: Memory value (will be serialized to JSON)
            expiry_seconds: Optional expiry time in seconds
            
        Returns:
            str: Memory item ID
        """
        memory_id = str(uuid.uuid4())
        timestamp = datetime.now()
        
        # Calculate expiry date if provided
        expiry_date = None
        if expiry_seconds is not None:
            expiry_date = timestamp + timedelta(seconds=expiry_seconds)
            
        # Serialize value to JSON
        if not isinstance(value, str):
            value_json = json.dumps(value)
        else:
            value_json = value
            
        # Check if memory item with same key exists
        existing = self.db.fetchone(
            "SELECT id FROM agent_memory WHERE agent_id = ? AND key = ?",
            (agent_id, key)
        )
        
        with self.db.transaction():
            if existing:
                # Update existing memory item
                self.db.execute(
                    """
                    UPDATE agent_memory SET
                    value = ?, creation_date = ?, last_accessed = ?, expiry_date = ?, access_count = 0
                    WHERE id = ?
                    """,
                    (value_json, timestamp, timestamp, expiry_date, existing['id'])
                )
                memory_id = existing['id']
            else:
                # Insert new memory item
                self.db.execute(
                    """
                    INSERT INTO agent_memory
                    (id, agent_id, key, value, creation_date, last_accessed, expiry_date, access_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (memory_id, agent_id, key, value_json, timestamp, timestamp, expiry_date, 0)
                )
                
        logger.info(f"Stored memory item '{key}' for agent {agent_id}")
        return memory_id
        
    def retrieve(self, agent_id: str, key: str) -> Optional[Any]:
        """
        Retrieve a memory item by key.
        
        Args:
            agent_id: Agent ID
            key: Memory key
            
        Returns:
            Optional[Any]: Memory value or None if not found
        """
        # Get memory item, checking expiry
        result = self.db.fetchone(
            """
            SELECT * FROM agent_memory 
            WHERE agent_id = ? AND key = ?
            AND (expiry_date IS NULL OR expiry_date > CURRENT_TIMESTAMP)
            """,
            (agent_id, key)
        )
        
        if not result:
            return None
            
        # Update access stats
        with self.db.transaction():
            self.db.execute(
                """
                UPDATE agent_memory SET
                last_accessed = CURRENT_TIMESTAMP,
                access_count = access_count + 1
                WHERE id = ?
                """,
                (result['id'],)
            )
            
        # Parse value from JSON if possible
        try:
            return json.loads(result['value'])
        except json.JSONDecodeError:
            # Return as-is if not valid JSON
            return result['value']
            
    def retrieve_many(self, agent_id: str, key_prefix: str = None) -> Dict[str, Any]:
        """
        Retrieve multiple memory items.
        
        Args:
            agent_id: Agent ID
            key_prefix: Optional key prefix to filter by
            
        Returns:
            Dict[str, Any]: Dictionary mapping keys to values
        """
        query = """
            SELECT id, key, value FROM agent_memory 
            WHERE agent_id = ?
            AND (expiry_date IS NULL OR expiry_date > CURRENT_TIMESTAMP)
        """
        params = [agent_id]
        
        if key_prefix:
            query += " AND key LIKE ?"
            params.append(f"{key_prefix}%")
            
        results = self.db.fetchall(query, params)
        
        # Update access stats for all retrieved items
        if results:
            with self.db.transaction():
                for result in results:
                    self.db.execute(
                        """
                        UPDATE agent_memory SET
                        last_accessed = CURRENT_TIMESTAMP,
                        access_count = access_count + 1
                        WHERE id = ?
                        """,
                        (result['id'],)
                    )
                    
        # Build result dictionary
        memory_dict = {}
        for result in results:
            try:
                memory_dict[result['key']] = json.loads(result['value'])
            except json.JSONDecodeError:
                memory_dict[result['key']] = result['value']
                
        return memory_dict
        
    def delete(self, agent_id: str, key: str) -> bool:
        """
        Delete a memory item.
        
        Args:
            agent_id: Agent ID
            key: Memory key
            
        Returns:
            bool: Success status
        """
        with self.db.transaction():
            self.db.execute(
                "DELETE FROM agent_memory WHERE agent_id = ? AND key = ?",
                (agent_id, key)
            )
            
        logger.info(f"Deleted memory item '{key}' for agent {agent_id}")
        return True
        
    def delete_all(self, agent_id: str, key_prefix: str = None) -> int:
        """
        Delete multiple memory items.
        
        Args:
            agent_id: Agent ID
            key_prefix: Optional key prefix to filter by
            
        Returns:
            int: Number of items deleted
        """
        query = "DELETE FROM agent_memory WHERE agent_id = ?"
        params = [agent_id]
        
        if key_prefix:
            query += " AND key LIKE ?"
            params.append(f"{key_prefix}%")
            
        with self.db.transaction():
            cursor = self.db.execute(query, params)
            
        deleted_count = cursor.rowcount
        logger.info(f"Deleted {deleted_count} memory items for agent {agent_id}")
        return deleted_count
        
    def clear_expired(self) -> int:
        """
        Clear all expired memory items.
        
        Returns:
            int: Number of items deleted
        """
        with self.db.transaction():
            cursor = self.db.execute(
                "DELETE FROM agent_memory WHERE expiry_date IS NOT NULL AND expiry_date <= CURRENT_TIMESTAMP"
            )
            
        deleted_count = cursor.rowcount
        logger.info(f"Cleared {deleted_count} expired memory items")
        return deleted_count
        
    def list_keys(self, agent_id: str, key_prefix: str = None) -> List[str]:
        """
        List memory keys.
        
        Args:
            agent_id: Agent ID
            key_prefix: Optional key prefix to filter by
            
        Returns:
            List[str]: List of memory keys
        """
        query = "SELECT key FROM agent_memory WHERE agent_id = ?"
        params = [agent_id]
        
        if key_prefix:
            query += " AND key LIKE ?"
            params.append(f"{key_prefix}%")
            
        results = self.db.fetchall(query, params)
        return [result['key'] for result in results]
        
    def get_memory_stats(self, agent_id: str) -> Dict:
        """
        Get memory statistics for an agent.
        
        Args:
            agent_id: Agent ID
            
        Returns:
            Dict: Memory statistics
        """
        # Get total count
        total_count = self.db.fetchone(
            "SELECT COUNT(*) as count FROM agent_memory WHERE agent_id = ?",
            (agent_id,)
        )
        
        # Get count by age
        last_day = self.db.fetchone(
            """
            SELECT COUNT(*) as count FROM agent_memory 
            WHERE agent_id = ? AND creation_date >= datetime('now', '-1 day')
            """,
            (agent_id,)
        )
        
        last_week = self.db.fetchone(
            """
            SELECT COUNT(*) as count FROM agent_memory 
            WHERE agent_id = ? AND creation_date >= datetime('now', '-7 day')
            """,
            (agent_id,)
        )
        
        # Get most accessed items
        most_accessed = self.db.fetchall(
            """
            SELECT key, access_count FROM agent_memory 
            WHERE agent_id = ?
            ORDER BY access_count DESC
            LIMIT 10
            """,
            (agent_id,)
        )
        
        # Get recently accessed items
        recently_accessed = self.db.fetchall(
            """
            SELECT key, last_accessed FROM agent_memory 
            WHERE agent_id = ?
            ORDER BY last_accessed DESC
            LIMIT 10
            """,
            (agent_id,)
        )
        
        # Compile stats
        stats = {
            "total_items": total_count['count'] if total_count else 0,
            "items_last_day": last_day['count'] if last_day else 0,
            "items_last_week": last_week['count'] if last_week else 0,
            "most_accessed": [dict(item) for item in most_accessed],
            "recently_accessed": [
                {
                    "key": item['key'],
                    "last_accessed": item['last_accessed']
                } 
                for item in recently_accessed
            ]
        }
        
        return stats 