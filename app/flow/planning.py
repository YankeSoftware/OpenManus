"""Planning flow implementation optimized for DeepSeek-R1's reasoning capabilities.

This module implements a sophisticated planning flow that leverages DeepSeek-R1's
strengths in hierarchical reasoning and knowledge manipulation. It maintains
clear reasoning chains while managing the operational space and knowledge graph.
"""

import json
import time
import uuid
from typing import Dict, List, Optional, Tuple, Union

from pydantic import Field

from app.agent.base import BaseAgent
from app.flow.base import BaseFlow, OperationalNode, PlanStepStatus
from app.llm import LLM
from app.logger import logger
from app.schema import AgentState, Message
from app.tool import PlanningTool


class ReasoningChain:
    """Manages DeepSeek-R1's reasoning chain for better context awareness."""
    
    def __init__(self, max_steps: int = 5, overlap: float = 0.3):
        self.steps = []
        self.max_steps = max_steps
        self.overlap = overlap
        
    def add_step(self, thought: str, action: Optional[str] = None, result: Optional[str] = None):
        """Add a reasoning step while maintaining the chain's coherence."""
        step = {
            "thought": thought,
            "action": action,
            "result": result,
            "timestamp": time.time()
        }
        self.steps.append(step)
        
        # Maintain chain length while preserving context
        if len(self.steps) > self.max_steps:
            # Keep first step, last few steps based on overlap
            keep_count = max(1, int(self.max_steps * self.overlap))
            self.steps = [self.steps[0]] + self.steps[-(keep_count-1):]
            
    def get_context(self) -> str:
        """Get the current reasoning context for DeepSeek-R1."""
        context = "Previous reasoning steps:\n\n"
        for i, step in enumerate(self.steps, 1):
            context += f"Step {i}:\n"
            context += f"Thought: {step['thought']}\n"
            if step['action']:
                context += f"Action: {step['action']}\n"
            if step['result']:
                context += f"Result: {step['result']}\n"
            context += "\n"
        return context


class PlanningFlow(BaseFlow):
    """A flow optimized for DeepSeek-R1's hierarchical planning capabilities.
    
    This flow leverages DeepSeek-R1's strengths in:
    1. Structured reasoning chains
    2. Context-aware decision making
    3. Dynamic knowledge graph manipulation
    4. Clear action planning and verification
    
    The flow maintains both a traditional operational space and a
    DeepSeek-R1-specific reasoning chain for optimal performance.
    """

    llm: LLM = Field(default_factory=lambda: LLM())
    planning_tool: PlanningTool = Field(default_factory=PlanningTool)
    executor_keys: List[str] = Field(default_factory=list)
    active_plan_id: str = Field(default_factory=lambda: f"plan_{int(time.time())}")
    current_step_index: Optional[int] = None
    reasoning_chain: ReasoningChain = Field(default_factory=ReasoningChain)

    def __init__(
        self, agents: Union[BaseAgent, List[BaseAgent], Dict[str, BaseAgent]], **data
    ):
        """Initialize the planning flow with DeepSeek-R1 optimizations."""
        super().__init__(agents, **data)
        
        # Initialize DeepSeek-R1 specific components
        self.reasoning_chain = ReasoningChain(
            max_steps=self.config.get("deepseek.max_reasoning_steps", 5),
            overlap=self.config.get("deepseek.context_overlap", 0.3)
        )
        
        # Initialize operational space
        self._initialize_operational_space()

    def _initialize_operational_space(self):
        """Initialize the operational space with core system nodes."""
        # Add planning control node
        self.update_operational_space(
            node_id="planning_control",
            node_type=OperationalNode.SYSTEM,
            data={
                "active_plan": self.active_plan_id,
                "status": "initialized",
                "current_step": None
            }
        )
        
        # Add knowledge graph node
        self.update_operational_space(
            node_id="knowledge_graph",
            node_type=OperationalNode.MUTABLE,
            data={
                "contexts": {},
                "relationships": {}
            }
        )
        
        # Add function registry node
        self.update_operational_space(
            node_id="function_registry",
            node_type=OperationalNode.FUNCTION,
            data={
                "available_tools": [tool.name for tool in (self.tools or [])]
            }
        )

    def get_executor(self, step_type: Optional[str] = None) -> BaseAgent:
        """Get an appropriate executor agent based on step requirements."""
        # Update operational space with executor selection
        executor_node_id = f"executor_{uuid.uuid4().hex[:8]}"
        
        # If step type is provided and matches an agent key, use that agent
        if step_type and step_type in self.agents:
            agent = self.agents[step_type]
            self.update_operational_space(
                node_id=executor_node_id,
                node_type=OperationalNode.AGENT,
                data={
                    "agent_type": step_type,
                    "capabilities": agent.__class__.__name__,
                    "status": "selected"
                }
            )
            return agent

        # Otherwise use the first available executor or fall back to primary agent
        for key in self.executor_keys:
            if key in self.agents:
                agent = self.agents[key]
                self.update_operational_space(
                    node_id=executor_node_id,
                    node_type=OperationalNode.AGENT,
                    data={
                        "agent_type": key,
                        "capabilities": agent.__class__.__name__,
                        "status": "selected"
                    }
                )
                return agent

        # Fallback to primary agent
        agent = self.primary_agent
        self.update_operational_space(
            node_id=executor_node_id,
            node_type=OperationalNode.AGENT,
            data={
                "agent_type": "primary",
                "capabilities": agent.__class__.__name__,
                "status": "selected"
            }
        )
        return agent

    async def execute(self, input_text: str) -> str:
        """Execute the hierarchical planning flow following the operational space model."""
        try:
            if not self.primary_agent:
                raise ValueError("No primary agent available")

            # 1. Process User Inquiry
            event_node_id = f"event_{uuid.uuid4().hex[:8]}"
            self.update_operational_space(
                node_id=event_node_id,
                node_type=OperationalNode.EXTERNAL,
                data={
                    "type": "user_inquiry",
                    "content": input_text,
                    "timestamp": time.time()
                }
            )

            # 2. Pre-reasoning and Plan Creation
            if input_text:
                await self._create_initial_plan(input_text)
                
                # Verify plan creation
                if self.active_plan_id not in self.planning_tool.plans:
                    logger.error(f"Plan creation failed. Plan ID {self.active_plan_id} not found.")
                    return f"Failed to create plan for: {input_text}"

            # 3. Execute Plan with Goal Tracking
            result = ""
            while True:
                # Get current step and update operational space
                self.current_step_index, step_info = await self._get_current_step_info()
                
                # Exit if no more steps
                if self.current_step_index is None:
                    result += await self._finalize_plan()
                    break

                # Execute step with appropriate agent
                step_type = step_info.get("type") if step_info else None
                executor = self.get_executor(step_type)
                
                # Update step in operational space
                step_node_id = f"step_{self.current_step_index}"
                self.update_operational_space(
                    node_id=step_node_id,
                    node_type=OperationalNode.SYSTEM,
                    data={
                        "index": self.current_step_index,
                        "type": step_type,
                        "status": "executing",
                        "executor": executor.__class__.__name__
                    }
                )
                
                # Execute and capture result
                step_result = await self._execute_step(executor, step_info)
                result += step_result + "\n"
                
                # Update step completion in operational space
                self.update_operational_space(
                    node_id=step_node_id,
                    node_type=OperationalNode.SYSTEM,
                    data={
                        "index": self.current_step_index,
                        "type": step_type,
                        "status": "completed",
                        "result": step_result
                    }
                )

                # Check for termination
                if hasattr(executor, "state") and executor.state == AgentState.FINISHED:
                    break

            return result
            
        except Exception as e:
            logger.error(f"Error in PlanningFlow: {str(e)}")
            # Update error in operational space
            self.update_operational_space(
                node_id=f"error_{uuid.uuid4().hex[:8]}",
                node_type=OperationalNode.SYSTEM,
                data={
                    "type": "execution_error",
                    "message": str(e),
                    "timestamp": time.time()
                }
            )
            return f"Execution failed: {str(e)}"

    async def _create_initial_plan(self, request: str) -> None:
        """Create an initial plan using DeepSeek-R1's structured reasoning."""
        logger.info(f"Creating initial plan with ID: {self.active_plan_id}")

        # Create a system message optimized for DeepSeek-R1
        system_message = Message.system_message(
            "You are a planning assistant powered by DeepSeek-R1. "
            "Create a structured, hierarchical plan that:\n"
            "1. Breaks down complex tasks into logical sub-tasks\n"
            "2. Maintains clear dependencies between steps\n"
            "3. Includes verification points for critical actions\n"
            "4. Considers both task completion and safety requirements"
        )

        # Add reasoning context
        context = self.reasoning_chain.get_context()
        
        # Create planning prompt
        planning_prompt = f"""
        CONTEXT:
        {context}

        TASK REQUEST:
        {request}

        Please create a detailed plan that:
        1. Identifies key objectives
        2. Breaks down complex actions
        3. Includes verification steps
        4. Maintains logical flow

        Format each step as: [TYPE] Step description
        Types: ANALYZE, PLAN, EXECUTE, VERIFY, REPORT
        """

        # Call LLM with planning-specific temperature
        response = await self.llm.ask_tool(
            messages=[Message.user_message(planning_prompt)],
            system_msgs=[system_message],
            tools=[self.planning_tool.to_param()],
            tool_choice="required",
            temperature=self.config.get("deepseek.planning_temperature", 0.2)
        )

        # Process and store the reasoning step
        self.reasoning_chain.add_step(
            thought="Initial plan creation",
            action="Create structured plan",
            result=str(response)
        )

        # Process tool calls and create plan
        if response.tool_calls:
            for tool_call in response.tool_calls:
                if tool_call.function.name == "planning":
                    try:
                        args = json.loads(tool_call.function.arguments)
                        args["plan_id"] = self.active_plan_id
                        result = await self.planning_tool.execute(**args)
                        logger.info(f"Plan creation result: {str(result)}")
                        return
                    except Exception as e:
                        logger.error(f"Error processing plan creation: {e}")

        # Create default plan if needed
        await self._create_default_plan(request)

    async def _get_current_step_info(self) -> tuple[Optional[int], Optional[dict]]:
        """
        Parse the current plan to identify the first non-completed step's index and info.
        Returns (None, None) if no active step is found.
        """
        if (
            not self.active_plan_id
            or self.active_plan_id not in self.planning_tool.plans
        ):
            logger.error(f"Plan with ID {self.active_plan_id} not found")
            return None, None

        try:
            # Direct access to plan data from planning tool storage
            plan_data = self.planning_tool.plans[self.active_plan_id]
            steps = plan_data.get("steps", [])
            step_statuses = plan_data.get("step_statuses", [])

            # Find first non-completed step
            for i, step in enumerate(steps):
                if i >= len(step_statuses):
                    status = PlanStepStatus.NOT_STARTED.value
                else:
                    status = step_statuses[i]

                if status in PlanStepStatus.get_active_statuses():
                    # Extract step type/category if available
                    step_info = {"text": step}

                    # Try to extract step type from the text (e.g., [SEARCH] or [CODE])
                    import re

                    type_match = re.search(r"\[([A-Z_]+)\]", step)
                    if type_match:
                        step_info["type"] = type_match.group(1).lower()

                    # Mark current step as in_progress
                    try:
                        await self.planning_tool.execute(
                            command="mark_step",
                            plan_id=self.active_plan_id,
                            step_index=i,
                            step_status=PlanStepStatus.IN_PROGRESS.value,
                        )
                    except Exception as e:
                        logger.warning(f"Error marking step as in_progress: {e}")
                        # Update step status directly if needed
                        if i < len(step_statuses):
                            step_statuses[i] = PlanStepStatus.IN_PROGRESS.value
                        else:
                            while len(step_statuses) < i:
                                step_statuses.append(PlanStepStatus.NOT_STARTED.value)
                            step_statuses.append(PlanStepStatus.IN_PROGRESS.value)

                        plan_data["step_statuses"] = step_statuses

                    return i, step_info

            return None, None  # No active step found

        except Exception as e:
            logger.warning(f"Error finding current step index: {e}")
            return None, None

    async def _execute_step(self, executor: BaseAgent, step_info: dict) -> str:
        """Execute a step with DeepSeek-R1's reasoning capabilities."""
        # Get current context
        context = self.reasoning_chain.get_context()
        plan_status = await self._get_plan_text()
        step_text = step_info.get("text", f"Step {self.current_step_index}")

        # Create a DeepSeek-R1 optimized prompt
        step_prompt = f"""
        CURRENT CONTEXT:
        {context}

        PLAN STATUS:
        {plan_status}

        CURRENT STEP:
        You are executing step {self.current_step_index}: "{step_text}"

        Approach this step by:
        1. Analyzing requirements and constraints
        2. Planning specific actions
        3. Executing with appropriate tools
        4. Verifying results
        5. Updating the knowledge graph

        Maintain awareness of:
        - Previous reasoning steps
        - Overall plan context
        - Safety requirements
        - Verification needs
        """

        try:
            # Execute with reasoning-specific temperature
            step_result = await executor.run(
                step_prompt,
                temperature=self.config.get("deepseek.reasoning_temperature", 0.1)
            )

            # Store the reasoning step
            self.reasoning_chain.add_step(
                thought=f"Executing step {self.current_step_index}",
                action=step_text,
                result=step_result
            )

            # Mark completion and update operational space
            await self._mark_step_completed()
            
            return step_result
        except Exception as e:
            logger.error(f"Error executing step {self.current_step_index}: {e}")
            return f"Error executing step {self.current_step_index}: {str(e)}"

    async def _mark_step_completed(self) -> None:
        """Mark the current step as completed."""
        if self.current_step_index is None:
            return

        try:
            # Mark the step as completed
            await self.planning_tool.execute(
                command="mark_step",
                plan_id=self.active_plan_id,
                step_index=self.current_step_index,
                step_status=PlanStepStatus.COMPLETED.value,
            )
            logger.info(
                f"Marked step {self.current_step_index} as completed in plan {self.active_plan_id}"
            )
        except Exception as e:
            logger.warning(f"Failed to update plan status: {e}")
            # Update step status directly in planning tool storage
            if self.active_plan_id in self.planning_tool.plans:
                plan_data = self.planning_tool.plans[self.active_plan_id]
                step_statuses = plan_data.get("step_statuses", [])

                # Ensure the step_statuses list is long enough
                while len(step_statuses) <= self.current_step_index:
                    step_statuses.append(PlanStepStatus.NOT_STARTED.value)

                # Update the status
                step_statuses[self.current_step_index] = PlanStepStatus.COMPLETED.value
                plan_data["step_statuses"] = step_statuses

    async def _get_plan_text(self) -> str:
        """Get the current plan as formatted text."""
        try:
            result = await self.planning_tool.execute(
                command="get", plan_id=self.active_plan_id
            )
            return result.output if hasattr(result, "output") else str(result)
        except Exception as e:
            logger.error(f"Error getting plan: {e}")
            return self._generate_plan_text_from_storage()

    def _generate_plan_text_from_storage(self) -> str:
        """Generate plan text directly from storage if the planning tool fails."""
        try:
            if self.active_plan_id not in self.planning_tool.plans:
                return f"Error: Plan with ID {self.active_plan_id} not found"

            plan_data = self.planning_tool.plans[self.active_plan_id]
            title = plan_data.get("title", "Untitled Plan")
            steps = plan_data.get("steps", [])
            step_statuses = plan_data.get("step_statuses", [])
            step_notes = plan_data.get("step_notes", [])

            # Ensure step_statuses and step_notes match the number of steps
            while len(step_statuses) < len(steps):
                step_statuses.append(PlanStepStatus.NOT_STARTED.value)
            while len(step_notes) < len(steps):
                step_notes.append("")

            # Count steps by status
            status_counts = {status: 0 for status in PlanStepStatus.get_all_statuses()}

            for status in step_statuses:
                if status in status_counts:
                    status_counts[status] += 1

            completed = status_counts[PlanStepStatus.COMPLETED.value]
            total = len(steps)
            progress = (completed / total) * 100 if total > 0 else 0

            plan_text = f"Plan: {title} (ID: {self.active_plan_id})\n"
            plan_text += "=" * len(plan_text) + "\n\n"

            plan_text += (
                f"Progress: {completed}/{total} steps completed ({progress:.1f}%)\n"
            )
            plan_text += f"Status: {status_counts[PlanStepStatus.COMPLETED.value]} completed, {status_counts[PlanStepStatus.IN_PROGRESS.value]} in progress, "
            plan_text += f"{status_counts[PlanStepStatus.BLOCKED.value]} blocked, {status_counts[PlanStepStatus.NOT_STARTED.value]} not started\n\n"
            plan_text += "Steps:\n"

            status_marks = PlanStepStatus.get_status_marks()

            for i, (step, status, notes) in enumerate(
                zip(steps, step_statuses, step_notes)
            ):
                # Use status marks to indicate step status
                status_mark = status_marks.get(
                    status, status_marks[PlanStepStatus.NOT_STARTED.value]
                )

                plan_text += f"{i}. {status_mark} {step}\n"
                if notes:
                    plan_text += f"   Notes: {notes}\n"

            return plan_text
        except Exception as e:
            logger.error(f"Error generating plan text from storage: {e}")
            return f"Error: Unable to retrieve plan with ID {self.active_plan_id}"

    async def _finalize_plan(self) -> str:
        """Finalize the plan and provide a summary using the flow's LLM directly."""
        plan_text = await self._get_plan_text()

        # Create a summary using the flow's LLM directly
        try:
            system_message = Message.system_message(
                "You are a planning assistant. Your task is to summarize the completed plan."
            )

            user_message = Message.user_message(
                f"The plan has been completed. Here is the final plan status:\n\n{plan_text}\n\nPlease provide a summary of what was accomplished and any final thoughts."
            )

            response = await self.llm.ask(
                messages=[user_message], system_msgs=[system_message]
            )

            return f"Plan completed:\n\n{response}"
        except Exception as e:
            logger.error(f"Error finalizing plan with LLM: {e}")

            # Fallback to using an agent for the summary
            try:
                agent = self.primary_agent
                summary_prompt = f"""
                The plan has been completed. Here is the final plan status:

                {plan_text}

                Please provide a summary of what was accomplished and any final thoughts.
                """
                summary = await agent.run(summary_prompt)
                return f"Plan completed:\n\n{summary}"
            except Exception as e2:
                logger.error(f"Error finalizing plan with agent: {e2}")
                return "Plan completed. Error generating summary."
