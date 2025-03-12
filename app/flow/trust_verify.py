import json
import time
import uuid
from enum import Enum
from typing import Dict, List, Optional, Union

from pydantic import BaseModel, Field

from app.agent.base import BaseAgent
from app.agent.trust_verify import ActionTrustLevel, TrustVerifyAgent
from app.flow.base import BaseFlow, OperationalNode
from app.llm import LLM
from app.logger import logger
from app.schema import AgentState, Message

class TaskEvaluation(BaseModel):
    """Result of task suitability evaluation."""
    is_suitable: bool = True
    reason: str = ""
    risk_level: str = "low"  # low, medium, high
    trust_level_required: str = "LOW_TRUST"
    requires_human_approval: bool = False

class TrustVerifyFlow(BaseFlow):
    """A flow that implements Chain-of-Action (CoA) with human verification.
    
    Key features:
    1. Task evaluation - Evaluates if a task is suitable for automated execution
    2. Action trust levels - Assigns trust levels to different actions
    3. Human verification - Requests approval for sensitive actions
    4. Execution logging - Maintains detailed logs of all actions
    5. Transparent summary - Provides a clear summary of the execution
    """
    
    llm: LLM = Field(default_factory=lambda: LLM())
    chain_of_action: List[Dict] = Field(default_factory=list)
    show_thinking: bool = Field(default=True)
    show_approvals: bool = Field(default=True)
    
    async def execute(self, input_text: str) -> str:
        """Execute the trust verification flow for the given input."""
        try:
            # Ensure we have a TrustVerifyAgent as primary
            if not isinstance(self.primary_agent, TrustVerifyAgent):
                logger.warning("Primary agent is not a TrustVerifyAgent, creating one...")
                # Create a new agent dictionary with a TrustVerifyAgent as primary
                agent_dict = {}
                for key, agent in self.agents.items():
                    agent_dict[key] = agent
                # Add TrustVerifyAgent as primary if not already present
                if "primary" not in agent_dict or not isinstance(agent_dict["primary"], TrustVerifyAgent):
                    agent_dict["primary"] = TrustVerifyAgent()
                # Update agents
                self.agents = agent_dict
            
            # Ensure primary agent is in a fresh state
            if hasattr(self.primary_agent, "state"):
                self.primary_agent.state = AgentState.IDLE
            
            # 1. Evaluate if the task is suitable for execution
            evaluation = await self._evaluate_task_suitability(input_text)
            logger.info(f"Starting execution for task: {input_text}")
            logger.info(f"Task evaluation: {evaluation.dict()}")
            
            # 2. Initialize chain of action with task information and trust levels
            await self._initialize_chain_of_action(input_text, evaluation)
            
            # 3. Execute the task with the agent
            if isinstance(self.primary_agent, TrustVerifyAgent):
                # Use the TrustVerifyAgent's specialized run method with trust levels
                result = await self.primary_agent.run(
                    input_text,
                    trust_level=evaluation.trust_level_required,
                    requires_approval=evaluation.requires_human_approval
                )
            else:
                # Fallback to standard BaseAgent run method which only accepts the request
                result = await self.primary_agent.run(input_text)
            
            # 4. Generate execution summary
            summary = self._generate_summary(input_text, result, evaluation)
            return summary
            
        except Exception as e:
            logger.error(f"Error in TrustVerifyFlow: {str(e)}")
            return f"Error processing your request: {str(e)}\n\nPlease try again with a more specific request."
    
    async def _evaluate_task_suitability(self, input_text: str) -> TaskEvaluation:
        """Evaluate if the task is suitable for execution and determine trust level."""
        try:
            # Reasonable default values if evaluation fails
            default_evaluation = TaskEvaluation(
                is_suitable=True,
                reason="",
                risk_level="low",
                trust_level_required="LOW_TRUST",
                requires_human_approval=False
            )
            
            # Skip detailed evaluation for simple informational requests
            if len(input_text.split()) < 15 or any(term in input_text.lower() for term in [
                "what is", "how to", "explain", "tell me about", "information on", "describe"
            ]):
                return default_evaluation
            
            # Create system prompt for evaluation
            system_prompt = """You are a task evaluator for an AI assistant. 
            Assess the input text to determine if it is:
            1. Free from harmful intent (no illegal, unethical, or dangerous requests)
            2. Technically feasible (within AI capabilities)
            3. Appropriate for automated handling (considering risk level)
            
            Respond with a JSON containing:
            - is_suitable: boolean (true unless definitively harmful)
            - reason: string (empty if suitable, explanation if not)
            - risk_level: string ("low", "medium", "high")
            - trust_level_required: string ("LOW_TRUST", "MEDIUM_TRUST", "HIGH_TRUST")
            - requires_human_approval: boolean (true for medium-high risk or edge cases)
            
            Be reasonable and permissive rather than overly restrictive. Research, information gathering, 
            and similar academic activities should generally be allowed with LOW or MEDIUM trust levels.
            """
            
            # Call LLM for evaluation
            response = await self.llm.ask(
                messages=[Message.user_message(f"Evaluate this task: {input_text}")],
                system_msgs=[Message.system_message(system_prompt)],
                temperature=0.1  # Low temperature for consistent evaluation
            )
            
            # Extract JSON response
            json_str = self._extract_json(response)
            if json_str:
                evaluation_dict = json.loads(json_str)
                evaluation = TaskEvaluation(**evaluation_dict)
                
                # Override excessively cautious evaluations for common tasks
                if evaluation.risk_level == "high" and not any(harmful_term in input_text.lower() for harmful_term in [
                    "hack", "exploit", "bypass", "illegal", "steal", "attack", "vulnerability"
                ]):
                    evaluation.risk_level = "medium"
                    
                if "find" in input_text.lower() and "document" in input_text.lower():
                    # Information/document retrieval should not be high risk
                    evaluation.risk_level = "low"
                    evaluation.trust_level_required = "LOW_TRUST"
                    evaluation.requires_human_approval = False
                
                return evaluation
            
            return default_evaluation
            
        except Exception as e:
            logger.error(f"Error evaluating task suitability: {e}")
            # Default to permissive evaluation if there's an error
            return TaskEvaluation()
    
    def _extract_json(self, text: str) -> Optional[str]:
        """Extract JSON from LLM response text."""
        try:
            if not text:
                return None
                
            # Try to find JSON block
            if "{" in text and "}" in text:
                json_start = text.find("{")
                json_end = text.rfind("}") + 1
                if json_start < json_end:
                    json_str = text[json_start:json_end]
                    # Validate by parsing
                    json.loads(json_str)
                    return json_str
            
            return None
        except:
            return None
    
    async def _initialize_chain_of_action(self, input_text: str, evaluation: TaskEvaluation) -> None:
        """Initialize the chain of action with task information and trust levels."""
        # Reset chain of action
        self.chain_of_action = []
        
        # Add task information
        task_entry = {
            "type": "task_initialization",
            "timestamp": time.time(),
            "content": input_text,
            "evaluation": evaluation.dict(),
            "node_id": f"coa_task_{uuid.uuid4().hex[:8]}"
        }
        self.chain_of_action.append(task_entry)
        
        # Update operational space
        self.update_operational_space(
            node_id=task_entry["node_id"],
            node_type=OperationalNode.EXTERNAL,
            data={
                "type": "task",
                "content": input_text,
                "evaluation": evaluation.dict(),
                "timestamp": task_entry["timestamp"]
            }
        )
        
        # Set trust levels in primary agent
        if isinstance(self.primary_agent, TrustVerifyAgent):
            # Configure trust levels
            self.primary_agent.configure_trust_levels({
                "dangerous_action": ActionTrustLevel.HIGH_TRUST,
                "write_file": ActionTrustLevel.MEDIUM_TRUST,
                "execute_code": ActionTrustLevel.MEDIUM_TRUST,
                "access_sensitive_data": ActionTrustLevel.MEDIUM_TRUST,
                "network_request": ActionTrustLevel.LOW_TRUST,
                "read_data": ActionTrustLevel.LOW_TRUST,
                "information_retrieval": ActionTrustLevel.LOW_TRUST,
                "basic_query": ActionTrustLevel.NO_VERIFICATION
            })
            
            # Reset agent state to ensure fresh start
            self.primary_agent.state = AgentState.IDLE
    
    def _generate_summary(self, input_text: str, result: str, evaluation: TaskEvaluation) -> str:
        """Generate a summary of the execution."""
        # Start with a basic summary
        summary = f"📝 Task Summary: \"{input_text}\"\n\n"
        
        # Add execution details
        coa_steps = len([step for step in self.chain_of_action if step.get("type") == "action"])
        approvals = len([step for step in self.chain_of_action if step.get("type") == "approval"])
        
        summary += f"Chain-of-Action contained {coa_steps} steps"
        if approvals > 0:
            summary += f" with {approvals} human approval{'' if approvals == 1 else 's'}"
        summary += ".\n\n"
        
        # Add execution result
        summary += f"🔍 Result:\n\n{result}\n\n"
        
        # Add transparency information if enabled
        if self.show_thinking:
            thinking_steps = [step for step in self.chain_of_action if step.get("type") == "thinking"]
            if thinking_steps:
                summary += "🧠 Reasoning Process:\n"
                for step in thinking_steps:
                    summary += f"- {step.get('content', 'N/A')}\n"
                summary += "\n"
        
        if self.show_approvals:
            approval_steps = [step for step in self.chain_of_action if step.get("type") == "approval"]
            if approval_steps:
                summary += "✅ Approval Record:\n"
                for step in approval_steps:
                    summary += f"- {step.get('action', 'N/A')}: {step.get('status', 'N/A')}\n"
                summary += "\n"
        
        return summary 