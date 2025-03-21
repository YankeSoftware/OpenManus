"""
Capability persistence store.

Handles storage and retrieval of agent capabilities, including implementation
code, metadata, and versioning.
"""

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from app.logger import logger
from app.persistence.db_manager import DatabaseManager


class CapabilityStore:
    """
    Store for capability persistence and code management.
    
    Handles:
    - Storing and retrieving capability metadata
    - Managing capability implementation code
    - Capability versioning
    """
    
    def __init__(self):
        """Initialize the capability store with a database connection."""
        self.db = DatabaseManager()
        self.config = self.db.config
        self.capability_dir = self.config.get("agent_capabilities.capability_storage_path", "data/capabilities")
        self._ensure_capability_directory()
        
    def _ensure_capability_directory(self):
        """Ensure the capability code directory exists."""
        Path(self.capability_dir).mkdir(parents=True, exist_ok=True)
        
    def create_capability(self, 
                         name: str, 
                         description: str = None, 
                         implementation: str = None,
                         metadata: Dict = None) -> str:
        """
        Create a new capability and store it in the database.
        
        Args:
            name: Capability name
            description: Capability description
            implementation: Capability implementation code
            metadata: Additional capability metadata
            
        Returns:
            str: ID of the created capability
        """
        capability_id = str(uuid.uuid4())
        timestamp = datetime.now()
        implementation_path = None
        
        if implementation:
            # Store the capability code to disk
            implementation_path = self._save_capability_code(capability_id, implementation)
        
        # Prepare metadata JSON if provided
        metadata_json = json.dumps(metadata) if metadata else None
        
        # Insert capability record in the database
        with self.db.transaction():
            self.db.execute(
                """
                INSERT INTO capabilities 
                (id, name, description, implementation_path, creation_date, last_modified, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (capability_id, name, description, implementation_path, timestamp, timestamp, metadata_json)
            )
        
        logger.info(f"Created capability '{name}' with ID {capability_id}")
        return capability_id
        
    def _save_capability_code(self, capability_id: str, code: str) -> str:
        """
        Save the capability code to disk.
        
        Args:
            capability_id: Capability ID
            code: Capability implementation code
            
        Returns:
            str: Path to the saved code file
        """
        # Create capability-specific directory
        capability_dir = os.path.join(self.capability_dir, capability_id)
        Path(capability_dir).mkdir(parents=True, exist_ok=True)
        
        # Save code to file
        code_path = os.path.join(capability_dir, "capability.py")
        with open(code_path, 'w') as f:
            f.write(code)
            
        return code_path
        
    def get_capability(self, capability_id: str) -> Optional[Dict]:
        """
        Get a capability by ID.
        
        Args:
            capability_id: Capability ID
            
        Returns:
            Optional[Dict]: Capability data or None if not found
        """
        result = self.db.fetchone(
            "SELECT * FROM capabilities WHERE id = ?",
            (capability_id,)
        )
        
        if not result:
            return None
            
        capability_data = dict(result)
        
        # Parse metadata JSON if it exists
        if capability_data.get('metadata'):
            try:
                capability_data['metadata'] = json.loads(capability_data['metadata'])
            except json.JSONDecodeError:
                logger.error(f"Failed to parse metadata for capability {capability_id}")
                capability_data['metadata'] = {}
                
        return capability_data
        
    def get_capability_by_name(self, name: str) -> Optional[Dict]:
        """
        Get a capability by name.
        
        Args:
            name: Capability name
            
        Returns:
            Optional[Dict]: Capability data or None if not found
        """
        result = self.db.fetchone(
            "SELECT * FROM capabilities WHERE name = ?",
            (name,)
        )
        
        if not result:
            return None
            
        capability_data = dict(result)
        
        # Parse metadata JSON if it exists
        if capability_data.get('metadata'):
            try:
                capability_data['metadata'] = json.loads(capability_data['metadata'])
            except json.JSONDecodeError:
                logger.error(f"Failed to parse metadata for capability {name}")
                capability_data['metadata'] = {}
                
        return capability_data
        
    def get_capability_code(self, capability_id: str) -> Optional[str]:
        """
        Get the implementation code for a capability.
        
        Args:
            capability_id: Capability ID
            
        Returns:
            Optional[str]: Capability implementation code or None if not found
        """
        capability_data = self.get_capability(capability_id)
        if not capability_data or not capability_data.get('implementation_path'):
            return None
            
        try:
            with open(capability_data['implementation_path'], 'r') as f:
                return f.read()
        except FileNotFoundError:
            logger.error(f"Capability code file not found for capability {capability_id}")
            return None
            
    def update_capability(self, 
                         capability_id: str, 
                         name: str = None,
                         description: str = None,
                         implementation: str = None,
                         metadata: Dict = None) -> bool:
        """
        Update an existing capability.
        
        Args:
            capability_id: Capability ID
            name: New capability name
            description: New capability description
            implementation: New capability implementation code
            metadata: New capability metadata
            
        Returns:
            bool: Success status
        """
        # Get current capability data
        capability_data = self.get_capability(capability_id)
        if not capability_data:
            logger.error(f"Capability {capability_id} not found for update")
            return False
            
        # Prepare update fields
        update_fields = {}
        
        if name is not None:
            update_fields['name'] = name
            
        if description is not None:
            update_fields['description'] = description
            
        if metadata is not None:
            update_fields['metadata'] = json.dumps(metadata)
            
        if implementation is not None:
            # Save new code version
            implementation_path = self._save_capability_code(capability_id, implementation)
            update_fields['implementation_path'] = implementation_path
            
        if not update_fields:
            logger.warning(f"No updates provided for capability {capability_id}")
            return True
            
        # Add last_modified timestamp and increment version
        update_fields['last_modified'] = datetime.now()
        update_fields['version'] = capability_data['version'] + 1
        
        # Build SQL query
        field_updates = ", ".join([f"{key} = ?" for key in update_fields])
        query = f"UPDATE capabilities SET {field_updates} WHERE id = ?"
        
        # Execute update
        with self.db.transaction():
            self.db.execute(
                query,
                list(update_fields.values()) + [capability_id]
            )
            
        logger.info(f"Updated capability {capability_id} (version {update_fields.get('version')})")
        return True
        
    def list_capabilities(self) -> List[Dict]:
        """
        List all capabilities.
        
        Returns:
            List[Dict]: List of capability data dictionaries
        """
        # Execute query
        results = self.db.fetchall("SELECT * FROM capabilities")
        
        # Process results
        capabilities = []
        for result in results:
            capability_data = dict(result)
            
            # Parse metadata JSON if it exists
            if capability_data.get('metadata'):
                try:
                    capability_data['metadata'] = json.loads(capability_data['metadata'])
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse metadata for capability {capability_data['id']}")
                    capability_data['metadata'] = {}
                    
            capabilities.append(capability_data)
            
        return capabilities
        
    def delete_capability(self, capability_id: str) -> bool:
        """
        Delete a capability by ID.
        
        Args:
            capability_id: Capability ID
            
        Returns:
            bool: Success status
        """
        # Get capability data first
        capability_data = self.get_capability(capability_id)
        if not capability_data:
            logger.error(f"Capability {capability_id} not found for deletion")
            return False
            
        # Begin transaction
        with self.db.transaction():
            # Delete capability record
            self.db.execute("DELETE FROM capabilities WHERE id = ?", (capability_id,))
            
            # Delete agent-capability mappings
            self.db.execute("DELETE FROM agent_capabilities WHERE capability_id = ?", (capability_id,))
            
        # Delete capability code directory if it exists
        capability_dir = os.path.join(self.capability_dir, capability_id)
        if os.path.exists(capability_dir):
            try:
                import shutil
                shutil.rmtree(capability_dir)
            except Exception as e:
                logger.error(f"Failed to delete capability directory: {str(e)}")
                
        logger.info(f"Deleted capability {capability_id} ({capability_data['name']})")
        return True
        
    def assign_capability_to_agent(self, agent_id: str, capability_id: str) -> bool:
        """
        Assign a capability to an agent.
        
        Args:
            agent_id: Agent ID
            capability_id: Capability ID
            
        Returns:
            bool: Success status
        """
        # Check if capability exists
        if not self.get_capability(capability_id):
            logger.error(f"Capability {capability_id} not found for assignment")
            return False
            
        # Check if agent exists (using DatabaseManager directly to avoid circular imports)
        agent_exists = self.db.fetchone(
            "SELECT id FROM agents WHERE id = ?", 
            (agent_id,)
        )
        
        if not agent_exists:
            logger.error(f"Agent {agent_id} not found for capability assignment")
            return False
            
        # Insert assignment
        with self.db.transaction():
            self.db.execute(
                """
                INSERT OR REPLACE INTO agent_capabilities
                (agent_id, capability_id, added_date)
                VALUES (?, ?, ?)
                """,
                (agent_id, capability_id, datetime.now())
            )
            
        logger.info(f"Assigned capability {capability_id} to agent {agent_id}")
        return True
        
    def get_agent_capabilities(self, agent_id: str) -> List[Dict]:
        """
        Get all capabilities assigned to an agent.
        
        Args:
            agent_id: Agent ID
            
        Returns:
            List[Dict]: List of capability data
        """
        results = self.db.fetchall(
            """
            SELECT c.* FROM capabilities c
            JOIN agent_capabilities ac ON c.id = ac.capability_id
            WHERE ac.agent_id = ?
            """,
            (agent_id,)
        )
        
        capabilities = []
        for result in results:
            capability_data = dict(result)
            
            # Parse metadata JSON if it exists
            if capability_data.get('metadata'):
                try:
                    capability_data['metadata'] = json.loads(capability_data['metadata'])
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse metadata for capability {capability_data['id']}")
                    capability_data['metadata'] = {}
                    
            capabilities.append(capability_data)
            
        return capabilities
        
    def remove_capability_from_agent(self, agent_id: str, capability_id: str) -> bool:
        """
        Remove a capability from an agent.
        
        Args:
            agent_id: Agent ID
            capability_id: Capability ID
            
        Returns:
            bool: Success status
        """
        with self.db.transaction():
            self.db.execute(
                "DELETE FROM agent_capabilities WHERE agent_id = ? AND capability_id = ?",
                (agent_id, capability_id)
            )
            
        logger.info(f"Removed capability {capability_id} from agent {agent_id}")
        return True 