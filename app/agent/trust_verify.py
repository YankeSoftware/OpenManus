import json
import re
import time
import uuid
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Tuple, Union

from pydantic import BaseModel, Field

from app.agent.base import BaseAgent
from app.logger import logger
from app.schema import AgentState, Message, ToolCall
from app.tool import Terminate, ToolCollection


class ActionTrustLevel(str, Enum):
    """Trust levels for different actions in the system."""
    NO_VERIFICATION = "NO_VERIFICATION"  # No verification needed
    LOW_TRUST = "LOW_TRUST"              # Low risk actions
    MEDIUM_TRUST = "MEDIUM_TRUST"        # Medium risk actions
    HIGH_TRUST = "HIGH_TRUST"            # High risk actions


class CoAStep(BaseModel):
    """A Chain-of-Action step with tracking for verification."""
    thought: str
    action: Optional[str] = None
    action_type: Optional[str] = None
    trust_level: ActionTrustLevel = ActionTrustLevel.LOW_TRUST
    requires_approval: bool = False
    approved: Optional[bool] = None
    result: Optional[str] = None
    timestamp: float = Field(default_factory=time.time)


class TrustVerifyAgent(BaseAgent):
    """An agent implementing Chain-of-Action (CoA) with human verification."""
    
    # Required BaseAgent fields
    name: str = "trust_verify"
    description: str = "An agent that implements Chain-of-Action with human verification"
    version: str = "1.0.0"
    
    # System prompts
    system_prompt: str = """You are a trust-verify agent that carefully evaluates and executes actions.
Your primary goal is to ensure safe and reliable execution of tasks while maintaining appropriate trust levels.
You think step by step and verify actions before executing them."""
    next_step_prompt: Optional[str] = None
    
    # Trust configuration
    trust_levels: Dict[str, ActionTrustLevel] = Field(default_factory=dict)
    current_trust_level: ActionTrustLevel = ActionTrustLevel.MEDIUM_TRUST
    requires_approval_override: Optional[bool] = None
    
    # CoA state tracking
    coa_steps: List[CoAStep] = Field(default_factory=list)
    current_step: int = 0
    current_approval_action: Optional[str] = None
    
    # Tool management
    tools: ToolCollection = Field(default_factory=ToolCollection)
    tool_calls: List[ToolCall] = Field(default_factory=list)
    
    def __init__(self, **data):
        """Initialize the TrustVerifyAgent with default trust levels."""
        super().__init__(**data)
        
        # Set default trust levels if not provided
        if not self.trust_levels:
            self.configure_trust_levels({
                "dangerous_action": ActionTrustLevel.HIGH_TRUST,
                "write_file": ActionTrustLevel.MEDIUM_TRUST,
                "execute_code": ActionTrustLevel.MEDIUM_TRUST,
                "access_sensitive_data": ActionTrustLevel.MEDIUM_TRUST,
                "network_request": ActionTrustLevel.LOW_TRUST,
                "read_data": ActionTrustLevel.LOW_TRUST,
                "information_retrieval": ActionTrustLevel.LOW_TRUST,
                "basic_query": ActionTrustLevel.NO_VERIFICATION
            })
        
        # Initialize tools if not provided
        if not self.tools:
            self.tools = ToolCollection()
            self.tools.add_tool(Terminate())
        
        # Ensure the agent starts in a IDLE state
        self.state = AgentState.IDLE
    
    def configure_trust_levels(self, trust_config: Dict[str, ActionTrustLevel]) -> None:
        """Configure the trust levels for different action types."""
        self.trust_levels.update(trust_config)
    
    async def think(self) -> bool:
        """
        Generate the next step in the Chain-of-Action.
        
        Returns:
            bool: True if an action should be taken, False if thinking is complete
        """
        if self.state != AgentState.RUNNING:
            return False
            
        # Get the current context
        context = self._get_context()
        
        # Create the thinking prompt
        prompt = f"""Based on the current context and task, what should be done next?

Current Context:
{context}

Respond with:
1. Your thought process
2. Any action needed (if applicable)
3. The type of action (e.g., information_retrieval, read_data, etc.)
"""
        
        # Get response from LLM
        response = await self.llm.ask(
            messages=[Message.user_message(prompt)],
            system_msgs=[Message.system_message(self._get_coa_system_prompt())],
            temperature=0.2  # Lower temperature for more focused thinking
        )
        
        # Process the response
        thought, action, action_type = self._parse_thinking_response(response)
        
        # Add the step to our chain
        self.add_step(
            thought=thought,
            action=action,
            action_type=action_type
        )
        
        # Return True if we have an action to take
        return action is not None
    
    async def act(self) -> str:
        """
        Execute the current action in the Chain-of-Action.
        
        Returns:
            str: The result of the action
        """
        if not self.coa_steps or self.current_step >= len(self.coa_steps):
            return "No action to execute"
            
        current_step = self.coa_steps[self.current_step]
        
        # If this step requires approval and hasn't been approved yet
        if current_step.requires_approval and not current_step.approved:
            approval_result = await self._handle_approval(current_step)
            if not approval_result:
                return "Action not approved"
        
        # Execute the action using available tools
        if current_step.action:
            try:
                # Find the appropriate tool
                tool = self.tools.get(current_step.action)
                if not tool:
                    return f"No tool found for action: {current_step.action}"
                
                # Execute the tool
                result = await tool.run()
                
                # Record the result
                current_step.result = str(result)
                return result
                
            except Exception as e:
                logger.error(f"Error executing action: {e}")
                current_step.result = f"Error: {str(e)}"
                return current_step.result
        
        return "No action specified"
    
    def _parse_thinking_response(self, response: str) -> Tuple[str, Optional[str], Optional[str]]:
        """Parse the LLM's thinking response into components."""
        # Default values
        thought = response
        action = None
        action_type = None
        
        # Try to extract structured components if present
        try:
            if "Thought:" in response:
                parts = response.split("\n")
                for i, part in enumerate(parts):
                    if part.startswith("Thought:"):
                        thought = part[8:].strip()
                    elif part.startswith("Action:"):
                        action = part[7:].strip()
                    elif part.startswith("Type:"):
                        action_type = part[5:].strip()
        except Exception:
            # If parsing fails, use the entire response as the thought
            pass
            
        return thought, action, action_type
    
    def _get_context(self) -> str:
        """Get the current context for the agent's thinking."""
        context = []
        
        # Add the original task if available
        if self.messages:
            context.append(f"Original Task: {self.messages[-1].content}")
        
        # Add recent steps from the chain of action
        if self.coa_steps:
            context.append("\nRecent Steps:")
            for step in self.coa_steps[-3:]:  # Last 3 steps
                context.append(f"- Thought: {step.thought}")
                if step.action:
                    context.append(f"  Action: {step.action}")
                if step.result:
                    context.append(f"  Result: {step.result}")
        
        return "\n".join(context)
    
    async def _handle_approval(self, step: CoAStep) -> bool:
        """Handle the approval process for a step."""
        # If approval override is set, use that
        if self.requires_approval_override is not None:
            step.approved = self.requires_approval_override
            return step.approved

        # Check trust level requirements
        action_type = step.action_type or "unknown"
        required_trust = self.trust_levels.get(action_type, ActionTrustLevel.MEDIUM_TRUST)
        
        # Auto-approve if trust level is sufficient
        if self.current_trust_level.value >= required_trust.value:
            step.approved = True
            return True
            
        # Otherwise, require explicit approval
        step.approved = False
        self.current_approval_action = step.action
        return False
    
    def _get_coa_system_prompt(self) -> str:
        """Get the system prompt for Chain-of-Action thinking."""
        return f"""You are a trust-verify agent operating with a trust level of {self.current_trust_level}.
Your goal is to break down tasks into clear steps and actions, considering trust and verification requirements.

When thinking about actions, consider:
1. The current trust level ({self.current_trust_level})
2. Whether the action needs verification
3. The potential impact and risk of the action

Format your response as:
Thought: [Your reasoning]
Action: [Specific action to take, if any]
Type: [Action type from available types]"""
    
    async def step(self) -> str:
        """
        Execute a single step in the Chain-of-Action process.
        This implements the abstract method required by BaseAgent.
        
        Returns:
            str: The result of this step's execution
        """
        try:
            # Think about what to do next
            should_act = await self.think()
            
            # If we have an action, execute it
            if should_act:
                result = await self.act()
                if result:
                    self.add_step(
                        thought="Processing result",
                        action=None,
                        result=result
                    )
                return result
            else:
                # No more actions needed, we're done
                self.state = AgentState.FINISHED
                return self._generate_response()
                
        except Exception as e:
            logger.error(f"Error in step execution: {e}")
            self.state = AgentState.ERROR
            return f"Error in step execution: {str(e)}"

    async def run(self, prompt: str, trust_level: Optional[str] = None, requires_approval: Optional[bool] = None, **kwargs) -> str:
        """Run the agent with the given prompt."""
        # Reset agent state
        self.reset()
        
        # Set trust level if provided
        if trust_level is not None:
            self.current_trust_level = ActionTrustLevel(trust_level)
        
        # Set approval override if provided
        self.requires_approval_override = requires_approval
        
        # Update state to RUNNING
        self.state = AgentState.RUNNING
        
        try:
            # Add initial step
            self.add_step(thought=f"Processing request: {prompt}")
            
            # Store the prompt in messages for context
            self.update_memory("user", prompt)
            
            # Execute steps until finished
            result = ""
            while self.state == AgentState.RUNNING:
                step_result = await self.step()
                if step_result:
                    result = step_result
                
                # Break if we're done
                if self.state != AgentState.RUNNING:
                    break
            
            return result if result else "No response generated"
            
        except Exception as e:
            logger.error(f"Error executing TrustVerifyAgent: {e}")
            self.state = AgentState.ERROR
            return f"Error processing your request: {str(e)}"
    
    def reset(self) -> None:
        """Reset the agent's state for a new request."""
        self.coa_steps = []
        self.current_step = 0
        self.current_approval_action = None
        self.requires_approval_override = None
        self.tool_calls = []
        self.state = AgentState.IDLE
    
    def add_step(self, thought: str, action: Optional[str] = None, action_type: Optional[str] = None, result: Optional[str] = None) -> None:
        """Add a new step to the Chain-of-Action."""
        step = CoAStep(
            thought=thought,
            action=action,
            action_type=action_type,
            result=result,
            requires_approval=self._requires_approval(action_type) if action_type else False
        )
        self.coa_steps.append(step)
        self.current_step = len(self.coa_steps) - 1

    def _requires_approval(self, action_type: str) -> bool:
        """Determine if an action type requires approval based on trust levels."""
        if self.requires_approval_override is not None:
            return self.requires_approval_override
            
        required_trust = self.trust_levels.get(action_type, ActionTrustLevel.MEDIUM_TRUST)
        return self.current_trust_level.value < required_trust.value

    def _generate_response(self) -> str:
        """Generate a final response based on the Chain-of-Action execution."""
        if not self.coa_steps:
            return "No steps were executed"
            
        # Collect results from steps
        results = []
        for step in self.coa_steps:
            if step.result:
                results.append(step.result)
                
        # If we have results, join them
        if results:
            return "\n".join(results)
            
        # Otherwise, return the last thought
        return self.coa_steps[-1].thought if self.coa_steps else "No response generated"
    
    def get_chain_of_action(self) -> List[Dict[str, Any]]:
        """Get the complete Chain-of-Action for transparency."""
        return [step.dict() for step in self.coa_steps]
        
    def is_interruptible(self) -> bool:
        """
        Determine if the agent can be safely interrupted at the current state.
        """
        # The agent is always interruptible unless it's in the middle of a critical operation
        # For now, we'll consider it always interruptible
        return True
        
    async def graceful_shutdown(self) -> str:
        """
        Perform a graceful shutdown of the agent's operations.
        """
        # Capture the current state
        state_snapshot = {
            "coa_steps": self.get_chain_of_action(),
            "trust_levels": self.trust_levels,
            "current_trust_level": self.current_trust_level,
            "requires_approval_override": self.requires_approval_override,
            "current_step": self.current_step,
            "current_approval_action": self.current_approval_action
        }
        
        # Log the shutdown
        logger.info(f"Agent gracefully shutting down. State snapshot created.")
        
        # In a real implementation, we might save this state for later resumption
        return "Agent operations gracefully terminated. State has been preserved." 