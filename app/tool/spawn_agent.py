"""
Spawn Agent Tool.

This tool allows agents to dynamically create and execute specialized sub-agents
for specific tasks.
"""

from typing import Dict, Optional

from app.agent.sub_agent_manager import SubAgentManager
from app.logger import logger
from app.tool.base import BaseTool


class SpawnAgent(BaseTool):
    """
    Tool for spawning specialized sub-agents to handle specific tasks.
    
    This tool enables:
    - Creating new specialized agents
    - Delegating tasks to existing agents
    - Managing agent lifecycle
    """
    
    name: str = "spawn_agent"
    description: str = "Spawn a specialized agent to handle a specific task. Can create a new agent or use an existing one."
    parameters: dict = {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "The task to delegate to a specialized agent.",
            },
            "agent_type": {
                "type": "string",
                "description": "Optional type of agent to use (e.g., 'document_processor', 'code_generator').",
            },
            "create_new": {
                "type": "boolean",
                "description": "Whether to create a new agent even if a suitable one exists.",
            },
            "agent_name": {
                "type": "string",
                "description": "Optional name for the new agent if creating one.",
            },
            "agent_description": {
                "type": "string",
                "description": "Optional description for the new agent if creating one.",
            },
            "system_prompt": {
                "type": "string",
                "description": "Optional system prompt for the new agent if creating one.",
            },
        },
        "required": ["task"],
    }
    
    async def execute(
        self,
        task: str,
        agent_type: Optional[str] = None,
        create_new: bool = False,
        agent_name: Optional[str] = None,
        agent_description: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ) -> Dict:
        """
        Execute the tool by spawning or finding an agent and delegating the task.
        
        Args:
            task: The task to delegate
            agent_type: Optional type of agent to use
            create_new: Whether to create a new agent
            agent_name: Optional name for the new agent
            agent_description: Optional description for the new agent
            system_prompt: Optional system prompt for the new agent
            
        Returns:
            Dict: Result with agent information and response
        """
        try:
            # Get the sub-agent manager
            manager = SubAgentManager()
            
            if create_new:
                # Create a new agent
                if not agent_name or not agent_description or not system_prompt:
                    # Generate agent specs using LLM
                    agent_specs = await self._generate_agent_specs(task, agent_type)
                    
                    agent_name = agent_specs.get("name") or agent_name
                    agent_type = agent_specs.get("type") or agent_type
                    agent_description = agent_specs.get("description") or agent_description
                    system_prompt = agent_specs.get("system_prompt") or system_prompt
                
                # Create the agent
                agent_id = await manager.create_agent(
                    name=agent_name,
                    agent_type=agent_type or "specialized_agent",
                    description=agent_description or f"Agent for task: {task[:50]}...",
                    system_prompt=system_prompt or f"You are a specialized agent for: {task}",
                    metadata={"created_for_task": task}
                )
                
                if not agent_id:
                    return {
                        "success": False,
                        "error": "Failed to create agent",
                        "observation": "Could not create specialized agent."
                    }
                    
                # Execute the task with the new agent
                result = await manager.execute_agent(agent_id, task)
                
                return {
                    "success": True,
                    "agent_id": agent_id,
                    "agent_name": agent_name,
                    "agent_type": agent_type,
                    "observation": result
                }
                
            else:
                # Delegate to existing agent or create if needed
                result = await manager.delegate_task(task, agent_type)
                
                if not result.get("success"):
                    return {
                        "success": False,
                        "error": result.get("error", "Unknown error"),
                        "observation": "Failed to delegate task to agent."
                    }
                    
                return {
                    "success": True,
                    "agent_id": result.get("agent_id"),
                    "observation": result.get("response")
                }
                
        except Exception as e:
            logger.error(f"Error in SpawnAgent tool: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "observation": f"Error spawning agent: {str(e)}"
            }
            
    async def _generate_agent_specs(self, task: str, agent_type: Optional[str] = None) -> Dict:
        """
        Generate agent specifications using LLM.
        
        Args:
            task: The task description
            agent_type: Optional agent type hint
            
        Returns:
            Dict: Agent specifications
        """
        # Get the sub-agent manager
        manager = SubAgentManager()
        
        # Create prompt for LLM
        type_hint = f" of type '{agent_type}'" if agent_type else ""
        prompt = f"""
        Design a specialized agent{type_hint} for the following task:
        
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
        
        # Get response from LLM
        response = await manager.llm.ask(prompt)
        
        try:
            import json
            return json.loads(response)
        except Exception as e:
            logger.error(f"Error parsing agent specs: {str(e)}")
            # Return default values
            return {
                "name": f"Agent_{task[:10].replace(' ', '_')}",
                "type": agent_type or "specialized_agent",
                "description": f"Specialized agent for: {task[:50]}",
                "system_prompt": f"You are a specialized agent for: {task}"
            } 