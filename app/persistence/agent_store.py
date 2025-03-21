"""
Agent persistence store.

Handles storage and retrieval of agent data, including dynamically generated
agent code, agent metadata, and agent relationships.
"""

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Union

from app.logger import logger
from app.persistence.db_manager import DatabaseManager


class AgentStore:
    """
    Store for agent persistence and code management.
    
    Handles:
    - Storing and retrieving agent metadata
    - Managing agent relationships
    - Storing and retrieving dynamically generated agent code
    - Agent versioning
    """
    
    def __init__(self):
        """Initialize the agent store with a database connection."""
        self.db = DatabaseManager()
        self.config = self.db.config
        self.agent_dir = self.config.get("sub_agents.agent_storage_dir", "agents/generated")
        self._ensure_agent_directory()
        
    def _ensure_agent_directory(self):
        """Ensure the agent code directory exists."""
        Path(self.agent_dir).mkdir(parents=True, exist_ok=True)
        
    def create_agent(self, 
                     name: str, 
                     agent_type: str, 
                     description: str = None, 
                     code: str = None, 
                     system_prompt: str = None,
                     parent_id: str = None,
                     metadata: Dict = None) -> str:
        """
        Create a new agent and store it in the database.
        
        Args:
            name: Agent name
            agent_type: Type of agent
            description: Agent description
            code: Agent implementation code
            system_prompt: Agent system prompt
            parent_id: Parent agent ID if this is a derived agent
            metadata: Additional agent metadata
            
        Returns:
            str: ID of the created agent
        """
        agent_id = str(uuid.uuid4())
        timestamp = datetime.now()
        code_path = None
        
        if code:
            # Store the agent code to disk
            code_path = self._save_agent_code(agent_id, code)
        
        # Prepare metadata JSON if provided
        metadata_json = json.dumps(metadata) if metadata else None
        
        # Insert agent record in the database
        with self.db.transaction():
            self.db.execute(
                """
                INSERT INTO agents 
                (id, name, type, description, creation_date, last_modified, 
                code_path, system_prompt, parent_id, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (agent_id, name, agent_type, description, timestamp, timestamp,
                 code_path, system_prompt, parent_id, metadata_json)
            )
        
        logger.info(f"Created agent '{name}' with ID {agent_id}")
        return agent_id
        
    def _save_agent_code(self, agent_id: str, code: str) -> str:
        """
        Save the agent code to disk.
        
        Args:
            agent_id: Agent ID
            code: Agent implementation code
            
        Returns:
            str: Path to the saved code file
        """
        # Create agent-specific directory
        agent_dir = os.path.join(self.agent_dir, agent_id)
        Path(agent_dir).mkdir(parents=True, exist_ok=True)
        
        # Save code to file
        code_path = os.path.join(agent_dir, "agent.py")
        with open(code_path, 'w') as f:
            f.write(code)
            
        return code_path
        
    def get_agent(self, agent_id: str) -> Optional[Dict]:
        """
        Get an agent by ID.
        
        Args:
            agent_id: Agent ID
            
        Returns:
            Optional[Dict]: Agent data or None if not found
        """
        result = self.db.fetchone(
            "SELECT * FROM agents WHERE id = ?",
            (agent_id,)
        )
        
        if not result:
            return None
            
        agent_data = dict(result)
        
        # Parse metadata JSON if it exists
        if agent_data.get('metadata'):
            try:
                agent_data['metadata'] = json.loads(agent_data['metadata'])
            except json.JSONDecodeError:
                logger.error(f"Failed to parse metadata for agent {agent_id}")
                agent_data['metadata'] = {}
                
        return agent_data
        
    def get_agent_by_name(self, name: str) -> Optional[Dict]:
        """
        Get an agent by name.
        
        Args:
            name: Agent name
            
        Returns:
            Optional[Dict]: Agent data or None if not found
        """
        result = self.db.fetchone(
            "SELECT * FROM agents WHERE name = ?",
            (name,)
        )
        
        if not result:
            return None
            
        agent_data = dict(result)
        
        # Parse metadata JSON if it exists
        if agent_data.get('metadata'):
            try:
                agent_data['metadata'] = json.loads(agent_data['metadata'])
            except json.JSONDecodeError:
                logger.error(f"Failed to parse metadata for agent {name}")
                agent_data['metadata'] = {}
                
        return agent_data
        
    def get_agent_code(self, agent_id: str) -> Optional[str]:
        """
        Get the implementation code for an agent.
        
        Args:
            agent_id: Agent ID
            
        Returns:
            Optional[str]: Agent implementation code or None if not found
        """
        agent_data = self.get_agent(agent_id)
        if not agent_data or not agent_data.get('code_path'):
            return None
            
        try:
            with open(agent_data['code_path'], 'r') as f:
                return f.read()
        except FileNotFoundError:
            logger.error(f"Agent code file not found for agent {agent_id}")
            return None
            
    def update_agent(self, 
                     agent_id: str, 
                     name: str = None,
                     description: str = None,
                     code: str = None,
                     system_prompt: str = None,
                     is_active: bool = None,
                     metadata: Dict = None) -> bool:
        """
        Update an existing agent.
        
        Args:
            agent_id: Agent ID
            name: New agent name
            description: New agent description
            code: New agent implementation code
            system_prompt: New agent system prompt
            is_active: New active status
            metadata: New agent metadata
            
        Returns:
            bool: Success status
        """
        # Get current agent data
        agent_data = self.get_agent(agent_id)
        if not agent_data:
            logger.error(f"Agent {agent_id} not found for update")
            return False
            
        # Prepare update fields
        update_fields = {}
        
        if name is not None:
            update_fields['name'] = name
            
        if description is not None:
            update_fields['description'] = description
            
        if system_prompt is not None:
            update_fields['system_prompt'] = system_prompt
            
        if is_active is not None:
            update_fields['is_active'] = 1 if is_active else 0
            
        if metadata is not None:
            update_fields['metadata'] = json.dumps(metadata)
            
        if code is not None:
            # Save new code version
            code_path = self._save_agent_code(agent_id, code)
            update_fields['code_path'] = code_path
            
        if not update_fields:
            logger.warning(f"No updates provided for agent {agent_id}")
            return True
            
        # Add last_modified timestamp and increment version
        update_fields['last_modified'] = datetime.now()
        update_fields['version'] = agent_data['version'] + 1
        
        # Build SQL query
        field_updates = ", ".join([f"{key} = ?" for key in update_fields])
        query = f"UPDATE agents SET {field_updates} WHERE id = ?"
        
        # Execute update
        with self.db.transaction():
            self.db.execute(
                query,
                list(update_fields.values()) + [agent_id]
            )
            
        logger.info(f"Updated agent {agent_id} (version {update_fields.get('version')})")
        return True
        
    def list_agents(self, agent_type: str = None, active_only: bool = True) -> List[Dict]:
        """
        List agents, optionally filtered by type and active status.
        
        Args:
            agent_type: Optional agent type filter
            active_only: Whether to return only active agents
            
        Returns:
            List[Dict]: List of agent data dictionaries
        """
        query = "SELECT * FROM agents"
        params = []
        
        # Add filters
        where_clauses = []
        
        if agent_type:
            where_clauses.append("type = ?")
            params.append(agent_type)
            
        if active_only:
            where_clauses.append("is_active = 1")
            
        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)
            
        # Execute query
        results = self.db.fetchall(query, params)
        
        # Process results
        agents = []
        for result in results:
            agent_data = dict(result)
            
            # Parse metadata JSON if it exists
            if agent_data.get('metadata'):
                try:
                    agent_data['metadata'] = json.loads(agent_data['metadata'])
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse metadata for agent {agent_data['id']}")
                    agent_data['metadata'] = {}
                    
            agents.append(agent_data)
            
        return agents
        
    def delete_agent(self, agent_id: str) -> bool:
        """
        Delete an agent by ID.
        
        Args:
            agent_id: Agent ID
            
        Returns:
            bool: Success status
        """
        # Get agent data first
        agent_data = self.get_agent(agent_id)
        if not agent_data:
            logger.error(f"Agent {agent_id} not found for deletion")
            return False
            
        # Begin transaction
        with self.db.transaction():
            # Delete agent record
            self.db.execute("DELETE FROM agents WHERE id = ?", (agent_id,))
            
            # Delete related records
            self.db.execute("DELETE FROM agent_capabilities WHERE agent_id = ?", (agent_id,))
            self.db.execute("DELETE FROM tool_usage_stats WHERE agent_id = ?", (agent_id,))
            self.db.execute("DELETE FROM agent_memory WHERE agent_id = ?", (agent_id,))
            self.db.execute("DELETE FROM agent_relationships WHERE agent1_id = ? OR agent2_id = ?", 
                           (agent_id, agent_id))
            
        # Delete agent code directory if it exists
        agent_dir = os.path.join(self.agent_dir, agent_id)
        if os.path.exists(agent_dir):
            try:
                import shutil
                shutil.rmtree(agent_dir)
            except Exception as e:
                logger.error(f"Failed to delete agent directory: {str(e)}")
                
        logger.info(f"Deleted agent {agent_id} ({agent_data['name']})")
        return True
        
    def add_agent_relationship(self, 
                               agent1_id: str, 
                               agent2_id: str, 
                               relationship_type: str, 
                               metadata: Dict = None) -> bool:
        """
        Add a relationship between two agents.
        
        Args:
            agent1_id: First agent ID
            agent2_id: Second agent ID
            relationship_type: Type of relationship
            metadata: Additional relationship metadata
            
        Returns:
            bool: Success status
        """
        # Validate agents exist
        if not self.get_agent(agent1_id) or not self.get_agent(agent2_id):
            logger.error(f"One or both agents not found for relationship: {agent1_id}, {agent2_id}")
            return False
            
        # Prepare metadata
        metadata_json = json.dumps(metadata) if metadata else None
        
        # Insert or replace relationship
        with self.db.transaction():
            self.db.execute(
                """
                INSERT OR REPLACE INTO agent_relationships 
                (agent1_id, agent2_id, relationship_type, created_date, metadata)
                VALUES (?, ?, ?, ?, ?)
                """,
                (agent1_id, agent2_id, relationship_type, datetime.now(), metadata_json)
            )
            
        logger.info(f"Added relationship '{relationship_type}' between agents {agent1_id} and {agent2_id}")
        return True
        
    def get_agent_relationships(self, agent_id: str, relationship_type: str = None) -> List[Dict]:
        """
        Get relationships for an agent.
        
        Args:
            agent_id: Agent ID
            relationship_type: Optional relationship type filter
            
        Returns:
            List[Dict]: List of relationship data
        """
        query = """
            SELECT * FROM agent_relationships 
            WHERE (agent1_id = ? OR agent2_id = ?)
        """
        params = [agent_id, agent_id]
        
        if relationship_type:
            query += " AND relationship_type = ?"
            params.append(relationship_type)
            
        results = self.db.fetchall(query, params)
        
        relationships = []
        for result in results:
            rel_data = dict(result)
            
            # Parse metadata JSON if it exists
            if rel_data.get('metadata'):
                try:
                    rel_data['metadata'] = json.loads(rel_data['metadata'])
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse metadata for relationship")
                    rel_data['metadata'] = {}
                    
            # Add related agent info
            related_agent_id = rel_data['agent2_id'] if rel_data['agent1_id'] == agent_id else rel_data['agent1_id']
            rel_data['related_agent_id'] = related_agent_id
            
            relationships.append(rel_data)
            
        return relationships 