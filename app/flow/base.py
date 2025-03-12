"""Base module for hierarchical planning and execution flows.

This module implements the core architecture for hierarchical planning and
operational space management through knowledge graphs. It defines the base
classes and types that coordinate different components of the system.
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, List, Optional, Union

from pydantic import BaseModel, Field

from app.agent.base import BaseAgent


class FlowType(str, Enum):
    """Flow types supported by the system.
    
    The system supports different execution flows that implement various
    planning and verification strategies:
    
    - PLANNING: Traditional hierarchical planning with operational space management
    - TRUST_VERIFY: Enhanced planning with Chain-of-Action verification
    """
    PLANNING = "planning"
    TRUST_VERIFY = "trust_verify"


class OperationalNode(str, Enum):
    """Types of nodes in the operational space/knowledge graph.
    
    The system's operational space consists of different types of nodes
    that serve specific roles in the execution flow:
    
    - SYSTEM: Core processing units managing flow control
    - EXTERNAL: Interface nodes for external system interaction
    - AGENT: Autonomous decision-making nodes
    - FUNCTION: Executable operation nodes
    - MUTABLE: Dynamic state storage nodes
    """
    SYSTEM = "system"
    EXTERNAL = "external"
    AGENT = "agent"
    FUNCTION = "function"
    MUTABLE = "mutable"


class BaseFlow(BaseModel, ABC):
    """Base class for hierarchical execution flows supporting multiple agents.
    
    This class implements the core architecture for hierarchical planning and
    operational space management. It coordinates the interaction between different
    components of the system through a dynamic knowledge graph.
    
    Architecture Layers:
    1. Event Processing
       - Handles user input and external events
       - Initializes execution context
    
    2. Reasoning
       - Pre-reasoning with knowledge graph context
       - Operational space manipulation
       - Goal identification and evaluation
    
    3. Action
       - Task decomposition and planning
       - Data aggregation and processing
       - Outcome verification
    
    4. Execution
       - Function execution
       - Data flow management
       - Result verification
    
    The flow maintains a dynamic operational space represented as a knowledge
    graph, where different types of nodes (system, external, agent, function,
    mutable) interact to accomplish tasks.
    """

    agents: Dict[str, BaseAgent] = Field(
        description="Dictionary mapping agent keys to agent instances"
    )
    tools: Optional[List] = Field(
        default=None,
        description="Optional list of available tools"
    )
    primary_agent_key: Optional[str] = Field(
        default=None,
        description="Key of the primary agent in the flow"
    )
    operational_space: Dict[str, Dict] = Field(
        default_factory=dict,
        description="Dynamic knowledge graph of the current operation"
    )

    class Config:
        arbitrary_types_allowed = True

    def __init__(
        self, agents: Union[BaseAgent, List[BaseAgent], Dict[str, BaseAgent]], **data
    ):
        """Initialize the flow with agents and set up the operational space.
        
        Args:
            agents: Agent(s) to use in the flow. Can be:
                   - Single agent instance
                   - List of agents
                   - Dictionary mapping keys to agents
            **data: Additional configuration data
        """
        # Handle different ways of providing agents
        if isinstance(agents, BaseAgent):
            agents_dict = {"default": agents}
        elif isinstance(agents, list):
            agents_dict = {f"agent_{i}": agent for i, agent in enumerate(agents)}
        else:
            agents_dict = agents

        # If primary agent not specified, use first agent
        primary_key = data.get("primary_agent_key")
        if not primary_key and agents_dict:
            primary_key = next(iter(agents_dict))
            data["primary_agent_key"] = primary_key

        # Set the agents dictionary
        data["agents"] = agents_dict

        # Initialize using BaseModel's init
        super().__init__(**data)

    @property
    def primary_agent(self) -> Optional[BaseAgent]:
        """Get the primary agent for the flow."""
        return self.agents.get(self.primary_agent_key)

    def get_agent(self, key: str) -> Optional[BaseAgent]:
        """Get a specific agent by key."""
        return self.agents.get(key)

    def add_agent(self, key: str, agent: BaseAgent) -> None:
        """Add a new agent to the flow."""
        self.agents[key] = agent

    def update_operational_space(
        self,
        node_id: str,
        node_type: OperationalNode,
        data: Dict,
        connections: List[str] = None
    ) -> None:
        """Update the operational space with new node information.
        
        Args:
            node_id: Unique identifier for the node
            node_type: Type of the node (system, external, agent, etc.)
            data: Node data/state
            connections: List of connected node IDs
        """
        self.operational_space[node_id] = {
            "type": node_type,
            "data": data,
            "connections": connections or []
        }

    @abstractmethod
    async def execute(self, input_text: str) -> str:
        """Execute the flow with given input.
        
        This method should implement the hierarchical planning process:
        1. Process the input event
        2. Perform pre-reasoning
        3. Identify goals
        4. Plan actions
        5. Execute with verification
        
        Args:
            input_text: The user's input request
            
        Returns:
            Execution result with verification status
        """


class PlanStepStatus(str, Enum):
    """Status tracking for hierarchical planning steps.
    
    These statuses track the progress of individual steps in the
    hierarchical planning process:
    
    - NOT_STARTED: Step is planned but not yet begun
    - IN_PROGRESS: Step is currently executing
    - COMPLETED: Step has finished successfully
    - BLOCKED: Step cannot proceed due to dependencies or constraints
    """

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"

    @classmethod
    def get_all_statuses(cls) -> list[str]:
        """Return a list of all possible step status values."""
        return [status.value for status in cls]

    @classmethod
    def get_active_statuses(cls) -> list[str]:
        """Return a list of values representing active statuses."""
        return [cls.NOT_STARTED.value, cls.IN_PROGRESS.value]

    @classmethod
    def get_status_marks(cls) -> Dict[str, str]:
        """Return a mapping of statuses to their marker symbols."""
        return {
            cls.COMPLETED.value: "[✓]",
            cls.IN_PROGRESS.value: "[→]",
            cls.BLOCKED.value: "[!]",
            cls.NOT_STARTED.value: "[ ]",
        }
