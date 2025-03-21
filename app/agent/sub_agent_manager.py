"""
Sub-agent manager for OpenManus.

This module handles the creation, management, and coordination of sub-agents
that can be dynamically generated to handle specific tasks.
"""

import asyncio
import importlib.util
import inspect
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Type, Union

from app.agent.base import BaseAgent
from app.config import Config
from app.logger import logger
from app.persistence.agent_store import AgentStore
from app.schema import AgentState, Memory
from app.llm import LLM


class SubAgentManager:
    """
    Manager for creating and coordinating sub-agents.
    
    This class enables:
    - Dynamic creation of specialized sub-agents
    - Loading and management of persistent agents
    - Coordination between multiple agents
    - Task delegation and result aggregation
    """
    
    _instance = None
    
    def __new__(cls):
        """Singleton pattern implementation."""
        if cls._instance is None:
            cls._instance = super(SubAgentManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize the sub-agent manager."""
        if self._initialized:
            return
            
        self.config = Config()
        self.agent_store = AgentStore()
        self.active_agents = {}  # Map of agent_id -> agent instance
        self.llm = LLM()
        self._initialized = True
        
    async def create_agent(self,
                          name: str,
                          agent_type: str,
                          description: str,
                          system_prompt: str,
                          code: Optional[str] = None,
                          parent_id: Optional[str] = None,
                          metadata: Optional[Dict] = None,
                          activate: bool = True) -> Optional[str]:
        """
        Create a new sub-agent.
        
        Args:
            name: Agent name
            agent_type: Type of agent
            description: Agent description
            system_prompt: System prompt for the agent
            code: Optional custom implementation code
            parent_id: Optional parent agent ID
            metadata: Optional metadata
            activate: Whether to activate the agent immediately
            
        Returns:
            Optional[str]: Agent ID if successful, None otherwise
        """
        try:
            # Generate code if not provided
            if not code:
                code = await self._generate_agent_code(name, agent_type, description, system_prompt)
                
            # Store agent in database
            agent_id = self.agent_store.create_agent(
                name=name,
                agent_type=agent_type,
                description=description,
                code=code,
                system_prompt=system_prompt,
                parent_id=parent_id,
                metadata=metadata
            )
            
            # Activate agent if requested
            if activate:
                await self.activate_agent(agent_id)
                
            return agent_id
            
        except Exception as e:
            logger.error(f"Error creating agent: {str(e)}")
            return None
            
    async def _generate_agent_code(self,
                                  name: str,
                                  agent_type: str,
                                  description: str,
                                  system_prompt: str) -> str:
        """
        Generate agent code using LLM.
        
        Args:
            name: Agent name
            agent_type: Type of agent
            description: Agent description
            system_prompt: System prompt for the agent
            
        Returns:
            str: Generated agent code
        """
        # Create a prompt for the LLM to generate agent code
        prompt = f"""
        Create a Python class for a specialized agent named '{name}' of type '{agent_type}'.
        
        Description: {description}
        
        The agent should:
        1. Inherit from BaseAgent
        2. Implement the step() method
        3. Use the system prompt: "{system_prompt}"
        4. Be optimized for its specific task
        
        Return only the Python code without any explanation or markdown formatting.
        """
        
        # Get code from LLM
        response = await self.llm.ask(prompt)
        
        # Extract code from response
        code = response.strip()
        
        # Add imports and ensure proper class structure
        if "from app.agent.base import BaseAgent" not in code:
            code = f"from app.agent.base import BaseAgent\nfrom app.schema import AgentState\n\n{code}"
            
        return code
        
    async def activate_agent(self, agent_id: str) -> Optional[BaseAgent]:
        """
        Activate an agent by loading it into memory.
        
        Args:
            agent_id: Agent ID
            
        Returns:
            Optional[BaseAgent]: Activated agent instance or None if failed
        """
        # Check if already active
        if agent_id in self.active_agents:
            return self.active_agents[agent_id]
            
        # Get agent data from store
        agent_data = self.agent_store.get_agent(agent_id)
        if not agent_data:
            logger.error(f"Agent {agent_id} not found")
            return None
            
        # Get agent code
        code = self.agent_store.get_agent_code(agent_id)
        if not code:
            logger.error(f"Agent code not found for {agent_id}")
            return None
            
        # Load agent class dynamically
        agent_class = self._load_agent_from_code(code, agent_data['name'])
        if not agent_class:
            return None
            
        # Create agent instance
        try:
            agent_instance = agent_class(
                name=agent_data['name'],
                description=agent_data['description'],
                system_prompt=agent_data['system_prompt'],
                llm=self.llm,
                memory=Memory(),
                state=AgentState.IDLE
            )
            
            # Store in active agents
            self.active_agents[agent_id] = agent_instance
            logger.info(f"Activated agent {agent_data['name']} ({agent_id})")
            
            return agent_instance
            
        except Exception as e:
            logger.error(f"Error instantiating agent {agent_id}: {str(e)}")
            return None
            
    def _load_agent_from_code(self, code: str, class_name: str) -> Optional[Type[BaseAgent]]:
        """
        Load an agent class from code string.
        
        Args:
            code: Agent code string
            class_name: Expected class name
            
        Returns:
            Optional[Type[BaseAgent]]: Agent class or None if loading failed
        """
        # Create a unique module name to avoid conflicts
        module_name = f"dynamic_agent_{uuid.uuid4().hex}"
        
        try:
            # Create a new module
            import types
            module = types.ModuleType(module_name)
            
            # Add required imports to module
            module.__dict__['BaseAgent'] = BaseAgent
            module.__dict__['AgentState'] = AgentState
            
            # Execute the code in the module's context
            exec(code, module.__dict__)
            
            # Find the agent class in the module
            agent_class = None
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (inspect.isclass(attr) and 
                    issubclass(attr, BaseAgent) and 
                    attr is not BaseAgent):
                    agent_class = attr
                    break
                    
            if not agent_class:
                logger.error(f"No valid agent class found in generated code")
                return None
                
            return agent_class
            
        except Exception as e:
            logger.error(f"Error loading agent from code: {str(e)}")
            return None
            
    async def deactivate_agent(self, agent_id: str) -> bool:
        """
        Deactivate an agent by removing it from memory.
        
        Args:
            agent_id: Agent ID
            
        Returns:
            bool: Success status
        """
        if agent_id not in self.active_agents:
            logger.warning(f"Agent {agent_id} not active")
            return False
            
        # Remove from active agents
        del self.active_agents[agent_id]
        logger.info(f"Deactivated agent {agent_id}")
        
        return True
        
    async def execute_agent(self, agent_id: str, request: str) -> str:
        """
        Execute an agent with a request.
        
        Args:
            agent_id: Agent ID
            request: Request to process
            
        Returns:
            str: Execution result
        """
        # Ensure agent is active
        agent = self.active_agents.get(agent_id)
        if not agent:
            agent = await self.activate_agent(agent_id)
            
        if not agent:
            return f"Error: Agent {agent_id} could not be activated"
            
        # Execute agent
        try:
            result = await agent.run(request)
            return result
        except Exception as e:
            logger.error(f"Error executing agent {agent_id}: {str(e)}")
            return f"Error executing agent: {str(e)}"
            
    async def delegate_task(self, task: str, agent_type: Optional[str] = None) -> Dict:
        """
        Delegate a task to the most appropriate agent.
        
        Args:
            task: Task description
            agent_type: Optional agent type filter
            
        Returns:
            Dict: Result with agent_id and response
        """
        # Find appropriate agent
        agent_id = await self._find_appropriate_agent(task, agent_type)
        
        if not agent_id:
            # Create a new agent if none found
            agent_id = await self._create_specialized_agent(task)
            
        if not agent_id:
            return {
                "success": False,
                "error": "Failed to find or create appropriate agent",
                "response": None
            }
            
        # Execute the task
        response = await self.execute_agent(agent_id, task)
        
        return {
            "success": True,
            "agent_id": agent_id,
            "response": response
        }
        
    async def _find_appropriate_agent(self, task: str, agent_type: Optional[str] = None) -> Optional[str]:
        """
        Find the most appropriate agent for a task.
        
        Args:
            task: Task description
            agent_type: Optional agent type filter
            
        Returns:
            Optional[str]: Agent ID or None if no appropriate agent found
        """
        # Get available agents
        agents = self.agent_store.list_agents(agent_type=agent_type)
        
        if not agents:
            return None
            
        # For now, use a simple approach - in the future, this could use embeddings or more sophisticated matching
        # Ask LLM to select the most appropriate agent
        agent_descriptions = "\n".join([
            f"{i+1}. {agent['name']}: {agent['description']}"
            for i, agent in enumerate(agents)
        ])
        
        prompt = f"""
        Task: {task}
        
        Available agents:
        {agent_descriptions}
        
        Which agent (1-{len(agents)}) is most appropriate for this task? 
        Respond with just the number.
        """
        
        response = await self.llm.ask(prompt)
        
        try:
            # Extract agent index from response
            agent_index = int(response.strip()) - 1
            if 0 <= agent_index < len(agents):
                return agents[agent_index]['id']
        except (ValueError, IndexError):
            pass
            
        # If no clear match or error, return the first agent if available
        return agents[0]['id'] if agents else None
        
    async def _create_specialized_agent(self, task: str) -> Optional[str]:
        """
        Create a specialized agent for a specific task.
        
        Args:
            task: Task description
            
        Returns:
            Optional[str]: Agent ID or None if creation failed
        """
        # Ask LLM to design a specialized agent
        prompt = f"""
        Design a specialized agent for the following task:
        
        {task}
        
        Provide the following details:
        1. Agent name (short and descriptive)
        2. Agent type (e.g., "document_processor", "code_generator", "data_analyzer")
        3. Description (1-2 sentences)
        4. System prompt (instructions for the agent)
        
        Format your response as JSON:
        {{
            "name": "...",
            "type": "...",
            "description": "...",
            "system_prompt": "..."
        }}
        """
        
        response = await self.llm.ask(prompt)
        
        try:
            import json
            agent_spec = json.loads(response)
            
            # Create the agent
            agent_id = await self.create_agent(
                name=agent_spec['name'],
                agent_type=agent_spec['type'],
                description=agent_spec['description'],
                system_prompt=agent_spec['system_prompt'],
                metadata={"created_for_task": task}
            )
            
            return agent_id
            
        except Exception as e:
            logger.error(f"Error creating specialized agent: {str(e)}")
            return None
            
    def list_active_agents(self) -> List[Dict]:
        """
        List all currently active agents.
        
        Returns:
            List[Dict]: List of active agent information
        """
        return [
            {
                "id": agent_id,
                "name": agent.name,
                "description": agent.description,
                "state": agent.state.value
            }
            for agent_id, agent in self.active_agents.items()
        ]
        
    async def shutdown(self):
        """Shutdown all active agents."""
        for agent_id in list(self.active_agents.keys()):
            await self.deactivate_agent(agent_id)
            
        logger.info(f"Shut down all active agents") 