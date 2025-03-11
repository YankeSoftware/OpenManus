import base64
import json
import os
from typing import Any, Dict, List, Literal, Optional, Tuple, Union

import aiohttp
from tenacity import (
    retry,
    stop_after_attempt,
    wait_random_exponential,
)

from app.config import LLMSettings, config
from app.llm.cost import Cost
from app.logger import logger
from app.schema import Message


class LLM:
    _instances: Dict[str, "LLM"] = {}

    def __new__(
        cls, config_name: str = "default", llm_config: Optional[LLMSettings] = None
    ):
        if config_name not in cls._instances:
            instance = super().__new__(cls)
            instance.__init__(config_name, llm_config)
            cls._instances[config_name] = instance
        return cls._instances[config_name]

    def __init__(
        self, config_name: str = "default", llm_config: Optional[LLMSettings] = None
    ):
        if not hasattr(
                self, "initialized"
        ):  # Only initialize if not already initialized
            llm_config = llm_config or config.llm
            llm_config = llm_config.get(config_name, llm_config["default"])

            self.model = getattr(llm_config, "model", "gpt-3.5-turbo")
            self.max_tokens = getattr(llm_config, "max_tokens", 4096)
            self.temperature = getattr(llm_config, "temperature", 0.7)
            self.top_p = getattr(llm_config, "top_p", 0.9)
            self.api_type = getattr(llm_config, "api_type", "openai")
            self.api_key = getattr(
                llm_config, "api_key", os.environ.get("OPENAI_API_KEY", "")
            )
            self.api_version = getattr(llm_config, "api_version", "")
            self.base_url = getattr(llm_config, "base_url", "https://api.openai.com/v1")
            self.timeout = getattr(llm_config, "timeout", 60)
            self.num_retries = getattr(llm_config, "num_retries", 3)
            self.retry_min_wait = getattr(llm_config, "retry_min_wait", 1)
            self.retry_max_wait = getattr(llm_config, "retry_max_wait", 10)
            self.custom_llm_provider = getattr(llm_config, "custom_llm_provider", None)

            # Initialize cost tracker
            self.cost_tracker = Cost()
            self.initialized = True

    @staticmethod
    def format_messages(messages: List[Union[dict, Message]]) -> List[dict]:
        """
        Format messages for LLM by converting them to OpenAI message format.

        Args:
            messages: List of messages that can be either dict or Message objects

        Returns:
            List[dict]: List of formatted messages in OpenAI format

        Raises:
            ValueError: If messages are invalid or missing required fields
            TypeError: If unsupported message types are provided
        """
        formatted_messages = []

        for message in messages:
            if isinstance(message, dict):
                # If message is already a dict, ensure it has required fields
                if "role" not in message:
                    raise ValueError("Message dict must contain 'role' field")
                formatted_messages.append(message)
            elif isinstance(message, Message):
                # If message is a Message object, convert it to dict
                formatted_messages.append(message.to_dict())
            else:
                raise TypeError(f"Unsupported message type: {type(message)}")

        # Validate all messages have required fields
        for msg in formatted_messages:
            if msg["role"] not in ["system", "user", "assistant", "tool"]:
                raise ValueError(f"Invalid role: {msg['role']}")
            if "content" not in msg and "tool_calls" not in msg:
                raise ValueError(
                    "Message must contain either 'content' or 'tool_calls'"
                )

        return formatted_messages

    def is_local(self) -> bool:
        """
        Check if the model is running locally.

        Returns:
            bool: True if the model is running locally, False otherwise
        """
        if self.base_url:
            return any(
                substring in self.base_url
                for substring in ["localhost", "127.0.0.1", "0.0.0.0"]
            )
        if self.model and (
                self.model.startswith("ollama") or "local" in self.model.lower()
        ):
            return True
        return False

    @staticmethod
    def encode_image(image_path: str) -> str:
        """
        Encode an image to base64.

        Args:
            image_path: Path to the image file

        Returns:
            str: Base64-encoded image
        """
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")

    def prepare_messages(
            self, text: str, image_path: Optional[str] = None
    ) -> List[dict]:
        """
        Prepare messages for completion, including multimodal content if needed.

        Args:
            text: Text content
            image_path: Optional path to an image file

        Returns:
            List[dict]: Formatted messages
        """
        messages = [{"role": "user", "content": text}]
        if image_path:
            base64_image = self.encode_image(image_path)
            messages[0]["content"] = [
                {"type": "text", "text": text},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
                },
            ]
        return messages

    async def _parse_stream(self, response) -> str:
        """Parse SSE stream from the API response.

        Args:
            response: aiohttp response object

        Returns:
            str: Concatenated content from the stream
        """
        collected = []
        async for line in response.content:
            if line:
                line = line.decode('utf-8').strip()
                if line.startswith('data: '):
                    json_str = line[6:].strip()
                    if json_str == "[DONE]":
                        break
                    try:
                        data = json.loads(json_str)
                        content = data['choices'][0]['delta'].get('content', '')
                        if content:
                            collected.append(content)
                            print(content, end="", flush=True)
                    except json.JSONDecodeError:
                        continue
        print()  # Add newline after streaming
        return "".join(collected)

    @retry(
        wait=wait_random_exponential(min=1, max=60),
        stop=stop_after_attempt(6),
    )
    async def ask(
        self,
        messages: List[Union[dict, Message]],
        system_msgs: Optional[List[Union[dict, Message]]] = None,
        stream: bool = True,
        temperature: Optional[float] = None,
    ) -> str:
        """
        Send a prompt to the LLM and get the response.

        Args:
            messages: List of conversation messages
            system_msgs: Optional system messages to prepend
            stream (bool): Whether to stream the response
            temperature (float): Sampling temperature for the response

        Returns:
            str: The generated response

        Raises:
            ValueError: If messages are invalid or response is empty
            Exception: For unexpected errors
        """
        try:
            # Format system and user messages
            if system_msgs:
                system_msgs = self.format_messages(system_msgs)
                messages = system_msgs + self.format_messages(messages)
            else:
                messages = self.format_messages(messages)

            logger.debug(f"Sending request with {len(messages)} messages")
            
            async with aiohttp.ClientSession() as session:
                payload = {
                    "model": self.model,
                    "messages": messages,
                    "max_tokens": self.max_tokens,
                    "temperature": temperature or self.temperature,
                    "stream": stream
                }

                async with session.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self.api_key}"
                    },
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    response.raise_for_status()
                    
                    if not stream:
                        result = await response.json()
                        content = result['choices'][0]['message']['content']
                        if not content or content.isspace():
                            raise ValueError("Empty response from LLM")
                        return content
                    
                    return await self._parse_stream(response)

        except aiohttp.ClientError as e:
            logger.error(f"Network error in ask: {str(e)}")
            raise
        except ValueError as ve:
            logger.error(f"Validation error in ask: {str(ve)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in ask: {str(e)}")
            raise

    @retry(
        wait=wait_random_exponential(min=1, max=60),
        stop=stop_after_attempt(6)
    )
    async def ask_tool(
         self,
         messages: List[Union[dict, Message]],
         system_msgs: Optional[List[Union[dict, Message]]] = None,
         timeout: Optional[int] = None,
         tools: Optional[List[dict]] = None,
         tool_choice: Literal["none", "auto", "required"] = "auto",
         temperature: Optional[float] = None,
    ):
        """Execute a tool-enabled chat completion."""
        try:
            # Format system and user messages
            if system_msgs:
                system_msgs = self.format_messages(system_msgs)
                messages = system_msgs + self.format_messages(messages)
            else:
                messages = self.format_messages(messages)

            logger.debug(f"Sending tool request with {len(messages)} messages")
            
            async with aiohttp.ClientSession() as session:
                payload = {
                    "model": self.model,
                    "messages": messages,
                    "max_tokens": self.max_tokens,
                    "temperature": temperature or self.temperature,
                    "tools": tools,
                    "tool_choice": tool_choice,
                    "stop": ["}}}}", "}}}", "]]", "```"]  # Add stop sequences to prevent garbage output
                }

                async with session.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self.api_key}"
                    },
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=timeout or self.timeout)
                ) as response:
                    response.raise_for_status()
                    result = await response.json()
                    
                    # Validate the response structure
                    if not isinstance(result, dict):
                        raise ValueError(f"Invalid response type: {type(result)}")
                    if 'choices' not in result:
                        raise ValueError("No 'choices' in response")
                    if not result['choices']:
                        raise ValueError("Empty choices in response")
                    
                    message = result['choices'][0]['message']
                    if not isinstance(message, dict):
                        raise ValueError(f"Invalid message type: {type(message)}")
                    
                    # Clean up any potential garbage in content
                    if 'content' in message:
                        content = message['content']
                        if content:
                            # Remove any garbage patterns
                            if any(pattern in content for pattern in ['}}}', ']]', '```', '\\n', '\\t']):
                                logger.warning("Found potential garbage in response content, cleaning...")
                                lines = content.split('\n')
                                content = '\n'.join(line for line in lines 
                                                  if not any(pattern in line 
                                                           for pattern in ['}}}', ']]', '```', '\\', ':', '{', '}']))
                                message['content'] = content.strip()
                    
                    # Handle tool calls
                    if 'tool_calls' in message:
                        tool_calls = message['tool_calls']
                        if not isinstance(tool_calls, list):
                            raise ValueError(f"Invalid tool_calls type: {type(tool_calls)}")
                        # Validate each tool call
                        for tool_call in tool_calls:
                            if not isinstance(tool_call, dict):
                                raise ValueError(f"Invalid tool call type: {type(tool_call)}")
                            if 'function' not in tool_call:
                                raise ValueError("No 'function' in tool call")
                            if 'name' not in tool_call['function']:
                                raise ValueError("No 'name' in tool call function")
                    
                    # Ensure we have either content or valid tool calls
                    if not message.get('content') and not message.get('tool_calls'):
                        raise ValueError("Response has neither content nor tool calls")
                        
                    return message

        except aiohttp.ClientError as e:
            logger.error(f"Network error in ask_tool: {str(e)}")
            raise
        except ValueError as ve:
            logger.error(f"Validation error in ask_tool: {str(ve)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in ask_tool: {str(e)}")
            raise

    def get_cost(self):
        """
        Get the current cost information.

        Returns:
            dict: Dictionary containing accumulated cost and individual costs
        """
        return self.cost_tracker.get()

    def log_cost(self):
        """
        Log the current cost information.

        Returns:
            str: Formatted string of cost information
        """
        return self.cost_tracker.log()

    def __str__(self):
        return f"LLM(model={self.model}, base_url={self.base_url})"

    def __repr__(self):
        return str(self)


# Example usage
if __name__ == "__main__":
    # Load environment variables if needed
    from dotenv import load_dotenv

    load_dotenv()

    # Create LLM instance
    llm = LLM()

    # Test text completion
    messages = llm.prepare_messages("Hello, how are you?")
    response, cost, total_cost = llm.do_completion(messages=messages)
    print(f"Response: {response['choices'][0]['message']['content']}")
    print(f"Cost: ${cost:.6f}, Total cost: ${total_cost:.6f}")

    # Test multimodal if image path is available
    image_path = os.getenv("TEST_IMAGE_PATH")
    if image_path and os.path.exists(image_path):
        multimodal_response, mm_cost, mm_total_cost = llm.do_multimodal_completion(
            "What's in this image?", image_path
        )
        print(
            f"Multimodal response: {multimodal_response['choices'][0]['message']['content']}"
        )
        print(f"Cost: ${mm_cost:.6f}, Total cost: ${mm_total_cost:.6f}")
