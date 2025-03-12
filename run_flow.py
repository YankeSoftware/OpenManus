import asyncio
import time

from app.agent.manus import Manus
from app.agent.trust_verify import TrustVerifyAgent
from app.flow.base import FlowType
from app.flow.flow_factory import FlowFactory
from app.llm import LLM
from app.logger import logger
from app.schema import AgentState, Memory


def print_welcome():
    """Print a welcome message with system information"""
    print("\n🤖 Welcome to OpenManus AI Assistant!")
    print("----------------------------------------")
    print("This system features two execution modes:")
    print("1. Planning Flow - Traditional task planning and execution")
    print("2. Trust-Verify Flow - Enhanced safety with Chain-of-Action verification")
    print("   - Action verification based on trust levels")
    print("   - Human-in-the-loop approval for critical actions")
    print("   - Transparent execution tracking")
    print("----------------------------------------\n")


async def run_flow():
    # Create LLM instance
    llm = LLM()
    memory = Memory()
    
    # Initialize agents with LLM and Memory
    agents = {
        "manus": Manus(
            name="manus",
            description="A versatile agent that can solve various tasks using multiple tools",
            llm=llm,
            memory=memory,
            state=AgentState.IDLE
        ),
        "trust_verify": TrustVerifyAgent(
            name="trust_verify",
            description="An agent that implements Chain-of-Action with human verification",
            llm=llm,
            memory=memory,
            state=AgentState.IDLE
        ),
    }

    print_welcome()

    while True:
        try:
            # Show the available flow types
            print("\nSelect execution mode:")
            print("1. Planning Flow")
            print("2. Trust-Verify Chain-of-Action Flow (Recommended)")
            
            flow_choice = input("\nChoose mode (1/2) [2]: ").strip() or "2"
            
            flow_type = FlowType.PLANNING
            if flow_choice == "2":
                flow_type = FlowType.TRUST_VERIFY
                logger.info("✓ Using Trust-Verify Chain-of-Action Flow")
            else:
                logger.info("✓ Using Planning Flow")

            print("\nEnter your request below. The system will:")
            print("1. Evaluate the safety and feasibility of your request")
            print("2. Break down the task into clear steps")
            print("3. Execute with appropriate safety checks")
            print("4. Provide a detailed summary of actions taken\n")

            prompt = input("Your request (or 'exit' to quit): ")
            if prompt.lower() == "exit":
                print("\n👋 Thank you for using OpenManus! Goodbye!")
                break

            # Create the appropriate flow based on selection
            flow = FlowFactory.create_flow(
                flow_type=flow_type,
                agents=agents,
            )
            
            if prompt.strip() == "" or prompt.strip().isspace():
                logger.warning("⚠️ Skipping empty prompt.")
                continue
                
            print("\n🔄 Processing your request...")

            try:
                start_time = time.time()
                result = await asyncio.wait_for(
                    flow.execute(prompt),
                    timeout=3600,  # 60 minute timeout
                )
                elapsed_time = time.time() - start_time
                logger.info(f"✓ Request processed in {elapsed_time:.2f} seconds")
                print("\n📋 Execution Summary:")
                print("----------------------------------------")
                print(result)
                print("----------------------------------------\n")
            except asyncio.TimeoutError:
                logger.error("⚠️ Request processing timed out after 1 hour")
                print("\nℹ️ Suggestion: Please try breaking down your request into smaller tasks.")

        except KeyboardInterrupt:
            print("\n\n👋 Operation cancelled. Thank you for using OpenManus!")
            break
        except Exception as e:
            logger.error(f"❌ Error: {str(e)}")
            print("\nℹ️ If this error persists, please check the logs or report the issue.")


if __name__ == "__main__":
    try:
        asyncio.run(run_flow())
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
        print("\n❌ An unexpected error occurred. Please check the logs for details.")
