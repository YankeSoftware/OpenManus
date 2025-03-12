from typing import Dict, List, Union

from app.agent.base import BaseAgent
from app.flow.base import BaseFlow, FlowType
from app.flow.planning import PlanningFlow
from app.flow.trust_verify import TrustVerifyFlow


class FlowFactory:
    """Factory class for creating different types of flows"""

    @staticmethod
    def create_flow(
        flow_type: FlowType,
        agents: Union[BaseAgent, List[BaseAgent], Dict[str, BaseAgent]],
        **kwargs,
    ) -> BaseFlow:
        """Create a flow based on type"""
        if flow_type == FlowType.PLANNING:
            return PlanningFlow(agents=agents, **kwargs)
        elif flow_type == FlowType.TRUST_VERIFY:
            return TrustVerifyFlow(agents=agents, **kwargs)
        else:
            raise ValueError(f"Unknown flow type: {flow_type}")
