"""Universal AI provider router for OpenAI, Claude, Grok and other LLM models.

This module provides a unified interface for interacting with various LLM providers.
It routes requests to the appropriate client based on the model ID and user preferences.

For using tools and automating workflows:
- Use langchain's tools framework for defining and executing tool actions
- Use crewai for orchestrating multi-agent workflows with LLM tools
- These frameworks handle tool calling automatically with the appropriate models
"""

import asyncio
import os
from contextlib import asynccontextmanager
from enum import Enum, auto
from typing import Any, Dict, List, Optional, TypedDict, Union

from openai import AsyncOpenAI

from pancaik.core.config import logger


class TextContent(TypedDict):
    """Type definition for text content in a message."""

    type: str  # "text"
    text: str


class ImageUrlContent(TypedDict):
    """Type definition for image URL content in a message."""

    type: str  # "image_url"
    image_url: Dict[str, str]  # {"url": "data:image/jpeg;base64,..."}


class MessageDict(TypedDict):
    """Type definition for a chat message."""

    role: str
    content: Union[str, List[Union[TextContent, ImageUrlContent]]]


class Provider(Enum):
    """Enum representing the available AI providers."""

    OPENAI = auto()
    ANTHROPIC = auto()
    XAI = auto()  # Grok
    OPENROUTER = auto()
    UNKNOWN = auto()


class AIRouter:
    """Universal router for AI model providers."""

    # Model ID prefixes for various providers
    MODEL_PREFIXES = {
        "gpt-": Provider.OPENAI,
        "o1-": Provider.OPENAI,
        "o3-": Provider.OPENAI,
        "dall-e-": Provider.OPENAI,
        "claude-": Provider.ANTHROPIC,
        "claude-3-": Provider.ANTHROPIC,
        "claude-3": Provider.ANTHROPIC,
        "anthropic.claude-": Provider.ANTHROPIC,
        "grok-": Provider.XAI,
        "x-ai/grok-": Provider.XAI,
        # OpenRouter specific prefixes
        "deepseek/": Provider.OPENROUTER,
        "meta-llama/": Provider.OPENROUTER,
        "mistralai/": Provider.OPENROUTER,
        "google/": Provider.OPENROUTER,
    }

    # Default models per provider
    DEFAULT_MODELS = {
        Provider.OPENAI: "o3-mini",
        Provider.ANTHROPIC: "claude-3-haiku-20240307",
        Provider.XAI: "grok-beta",
        Provider.OPENROUTER: "deepseek/deepseek-chat",
    }

    # Base URLs for direct API access
    BASE_URLS = {
        Provider.OPENAI: "https://api.openai.com/v1",
        Provider.ANTHROPIC: "https://api.anthropic.com/v1",
        Provider.XAI: "https://api.x.ai/v1",
        Provider.OPENROUTER: "https://openrouter.ai/api/v1",
    }

    def __init__(self, default_provider: Provider = Provider.OPENROUTER, use_openrouter: bool = False, max_concurrent_requests: int = 100):
        """Initialize the AI router with configuration settings.

        Args:
            default_provider: The default provider to use
            use_openrouter: Whether to route requests through OpenRouter
            max_concurrent_requests: Maximum number of concurrent requests
        """
        self.default_provider = default_provider
        self.use_openrouter = use_openrouter
        self._semaphore = asyncio.Semaphore(max_concurrent_requests)

        # Track provider-specific clients
        self._clients: Dict[Provider, Optional[AsyncOpenAI]] = {p: None for p in Provider}

    def detect_provider(self, model_id: str) -> Provider:
        """Detect the provider based on model ID prefix.

        Args:
            model_id: The model identifier string

        Returns:
            The detected provider
        """
        for prefix, provider in self.MODEL_PREFIXES.items():
            if model_id.startswith(prefix):
                return provider
        return Provider.UNKNOWN

    def get_base_url(self, provider: Provider) -> str:
        """Get the base URL for a provider.

        Args:
            provider: The provider to get the base URL for

        Returns:
            The base URL for the provider's API
        """
        return self.BASE_URLS.get(provider, self.BASE_URLS[Provider.OPENROUTER])

    def get_api_key(self, provider: Provider) -> Optional[str]:
        """Get the API key for a provider.

        Args:
            provider: The provider to get the API key for

        Returns:
            The API key for the provider or None if not available
        """
        # Load API keys at runtime
        api_keys = {
            Provider.OPENAI: os.environ.get("OPENAI_API_KEY"),
            Provider.ANTHROPIC: os.environ.get("ANTHROPIC_API_KEY"),
            Provider.XAI: os.environ.get("GROK_API_KEY"),
            Provider.OPENROUTER: os.environ.get("OPENROUTER_API_KEY"),
        }

        # If using OpenRouter, always return the OpenRouter API key
        if self.use_openrouter and provider != Provider.OPENROUTER:
            return api_keys[Provider.OPENROUTER]
        return api_keys[provider]

    def get_effective_model_id(self, model_id: str, provider: Provider) -> str:
        """Get the effective model ID to use based on routing preferences.

        Args:
            model_id: The original model ID
            provider: The detected provider

        Returns:
            The effective model ID to use
        """
        # If using OpenRouter and the provider supports it, adjust the model ID format
        if self.use_openrouter and provider != Provider.OPENROUTER:
            if provider == Provider.OPENAI:
                return f"openai/{model_id}"
            elif provider == Provider.ANTHROPIC:
                return f"anthropic/{model_id}"
            elif provider == Provider.XAI:
                return "x-ai/grok-beta"
        # If the model is already an OpenRouter model (has provider-specific prefix), return as-is
        return model_id

    @asynccontextmanager
    async def get_client(self, provider: Provider):
        """Get an async client for the specified provider.

        Args:
            provider: The provider to get a client for

        Yields:
            An AsyncOpenAI client configured for the provider
        """
        base_url = self.get_base_url(Provider.OPENROUTER if self.use_openrouter else provider)
        api_key = self.get_api_key(provider)

        # Create a new client if none exists
        client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
        )
        try:
            yield client
        finally:
            await client.close()

    async def get_completion(
        self,
        prompt: Union[str, List[MessageDict]],
        model_id: Optional[str] = None,
        provider: Optional[Provider] = None,
        use_openrouter: Optional[bool] = None,
        response_model: Any = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
        **kwargs,
    ) -> Union[str, Dict[str, Any]]:
        """Get a completion from the specified model.

        Args:
            prompt: The prompt or list of message dictionaries
            model_id: The model identifier to use
            provider: Override the auto-detected provider
            use_openrouter: Override the default OpenRouter setting
            response_model: Response model for structured output
            temperature: Temperature for generation (only included if explicitly set)
            max_tokens: Maximum tokens to generate (only included if explicitly set)
            tools: List of tools available for the model to call
            tool_choice: How the model should choose tools ("auto", "none", or specific tool)
            **kwargs: Additional arguments to pass to the provider

        Returns:
            The model's completion text or structured response

        Raises:
            ValueError: If no API keys are available for any provider
        """
        async with self._semaphore:
            # Determine which provider and model to use
            use_router = self.use_openrouter if use_openrouter is None else use_openrouter

            # If no model specified, try to find an available provider with API key
            if model_id is None and provider is None:
                # First try default provider
                if self.get_api_key(self.default_provider):
                    provider = self.default_provider
                    model = self.DEFAULT_MODELS[provider]
                # Then try OpenRouter if we're using it
                elif use_router and self.get_api_key(Provider.OPENROUTER):
                    provider = Provider.OPENROUTER
                    model = self.DEFAULT_MODELS[provider]
                # Otherwise try each provider with an API key
                else:
                    for p in Provider:
                        if self.get_api_key(p):
                            provider = p
                            model = self.DEFAULT_MODELS[p]
                            break
                    else:
                        # If no API keys available, raise error
                        raise ValueError("No API keys available for any provider")
            else:
                # Use the provided model ID or fallback to default
                model = model_id or self.DEFAULT_MODELS[self.default_provider]

            # Auto-detect provider from model ID if not explicitly provided
            detected_provider = provider or self.detect_provider(model)
            effective_provider = Provider.OPENROUTER if use_router else detected_provider

            # Get the effective model ID based on routing choice
            effective_model = self.get_effective_model_id(model, detected_provider)

            # Verify we have an API key before proceeding
            api_key = self.get_api_key(effective_provider)
            if not api_key:
                raise ValueError(f"No API key available for provider {effective_provider.name}")

            # Format messages
            messages = [{"role": "user", "content": prompt}] if isinstance(prompt, str) else prompt

            # Log the request
            try:
                preview = messages[-1]["content"][:50].strip().replace("\n", " ")
                logger.info(f"{effective_provider.name} {effective_model}: {preview}")
            except Exception as e:
                pass

            # Prepare kwargs for API call, only including parameters that have values
            api_kwargs = kwargs.copy()
            if max_tokens is not None:
                api_kwargs["max_tokens"] = max_tokens
            if temperature is not None:
                api_kwargs["temperature"] = temperature
            if tools is not None:
                api_kwargs["tools"] = tools
            if tool_choice is not None:
                api_kwargs["tool_choice"] = tool_choice

            try:
                async with self.get_client(effective_provider) as client:
                    # Single completion call that handles all cases
                    completion_args = {"model": effective_model, "messages": messages, **api_kwargs}

                    # Use beta.chat.completions.parse for structured responses
                    if response_model:
                        completion = await client.beta.chat.completions.parse(
                            model=effective_model, messages=messages, response_format=response_model, **api_kwargs
                        )
                        return completion.choices[0].message.parsed
                    else:
                        # Make the API call for standard responses
                        completion = await client.chat.completions.create(**completion_args)

                        # If there are tool calls, return the full completion object for processing
                        if tools and hasattr(completion.choices[0].message, "tool_calls") and completion.choices[0].message.tool_calls:
                            return completion

                        return completion.choices[0].message.content
            except Exception as e:
                if getattr(e, "status_code", None) == 429:
                    logger.warning(f"{effective_provider.name}: API rate limit exceeded")
                    raise
                logger.error(f"Error in {effective_provider.name} API call: {str(e)}")
                raise


# Create singleton instances for convenient access
default_router = AIRouter(use_openrouter=False)
openrouter = AIRouter(use_openrouter=True)


async def get_completion(
    prompt: Union[str, List[MessageDict]],
    model_id: Optional[str] = None,
    use_openrouter: bool = True,
    response_model: Any = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
    agent_mode: bool = False,
    max_iterations: int = 10,
    verbose: bool = False,
    system_message: Optional[str] = None,
    **kwargs,
) -> Union[str, Dict[str, Any]]:
    """Get a completion from an AI model using pre-initialized router.

    Args:
        prompt: The prompt or list of message dictionaries
        model_id: The model identifier to use
        use_openrouter: Whether to route through OpenRouter
        response_model: Response model for structured output
        temperature: Temperature for generation (only included if explicitly set)
        max_tokens: Maximum tokens to generate (only included if explicitly set)
        tools: List of tools available for the model to call
        tool_choice: How the model should choose tools ("auto", "none", or specific tool)
        agent_mode: If True, use LangChain agent for iterative tool calling
        max_iterations: Maximum iterations for agent mode
        verbose: Enable verbose logging for agent mode
        system_message: System message for the agent (tools instruction will be appended in agent mode)
        **kwargs: Additional arguments to pass to the provider

    Returns:
        The model's completion text or structured response
    """
    # If agent_mode is True and tools are provided, use LangChain agent
    if agent_mode and tools:
        return await get_agent_completion(
            prompt=prompt,
            tools=tools,
            model_id=model_id,
            use_openrouter=use_openrouter,
            temperature=temperature,
            max_tokens=max_tokens,
            max_iterations=max_iterations,
            verbose=verbose,
            system_message=system_message,
            **kwargs,
        )

    # Otherwise use the standard completion
    router = openrouter if use_openrouter else default_router

    # Create kwargs for the router's get_completion method
    router_kwargs = kwargs.copy()
    if temperature is not None:
        router_kwargs["temperature"] = temperature
    if max_tokens is not None:
        router_kwargs["max_tokens"] = max_tokens
    if tools is not None:
        router_kwargs["tools"] = tools
    if tool_choice is not None:
        router_kwargs["tool_choice"] = tool_choice

    return await router.get_completion(
        prompt=prompt, model_id=model_id, use_openrouter=use_openrouter, response_model=response_model, **router_kwargs
    )


async def get_agent_completion(
    prompt: Union[str, List[MessageDict]],
    tools: List[Any],  # LangChain tools
    model_id: Optional[str] = None,
    use_openrouter: bool = True,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    max_iterations: int = 10,
    verbose: bool = False,
    system_message: Optional[str] = None,
    **kwargs,
) -> Dict[str, Any]:
    """Get a completion using LangChain agent with iterative tool calling.

    Args:
        prompt: The prompt or list of message dictionaries
        tools: List of LangChain tools
        model_id: The model identifier to use
        use_openrouter: Whether to route through OpenRouter
        temperature: Temperature for generation
        max_tokens: Maximum tokens to generate
        max_iterations: Maximum iterations for the agent
        verbose: Enable verbose logging
        system_message: Complete system message for the agent (caller has full control)
        **kwargs: Additional arguments

    Returns:
        Dictionary with agent results including final output and intermediate steps
    """
    try:
        import os

        from langchain.agents import AgentExecutor, create_tool_calling_agent
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_openai import ChatOpenAI

        # Get API configuration
        if use_openrouter:
            api_key = os.environ.get("OPENROUTER_API_KEY")
            base_url = "https://openrouter.ai/api/v1"

            # Handle model ID for OpenRouter
            if model_id:
                # Check if it's already an OpenRouter model (has provider prefix)
                openrouter_prefixes = ["deepseek/", "meta-llama/", "mistralai/", "google/", "anthropic/", "x-ai/"]
                if any(model_id.startswith(prefix) for prefix in openrouter_prefixes):
                    effective_model = model_id  # Use as-is for OpenRouter native models
                elif model_id.startswith("openai/"):
                    effective_model = model_id  # Already has openai/ prefix
                else:
                    effective_model = f"openai/{model_id}"  # Add openai/ for OpenAI models
            else:
                effective_model = "openai/gpt-4"  # Default OpenAI model via OpenRouter
        else:
            api_key = os.environ.get("OPENAI_API_KEY")
            base_url = "https://api.openai.com/v1"
            effective_model = model_id or "gpt-4"

        if not api_key:
            raise ValueError(f"No API key found for {'OpenRouter' if use_openrouter else 'OpenAI'}")

        # Initialize the LLM
        llm_kwargs = {
            "model": effective_model,
            "api_key": api_key,
            "base_url": base_url,
        }
        if temperature is not None:
            llm_kwargs["temperature"] = temperature
        if max_tokens is not None:
            llm_kwargs["max_tokens"] = max_tokens

        llm = ChatOpenAI(**llm_kwargs)

        # Use the caller's system message or provide a minimal default
        final_system_message = system_message or "You are a helpful assistant."

        prompt_template = ChatPromptTemplate.from_messages(
            [
                ("system", final_system_message),
                ("human", "{input}"),
                ("placeholder", "{agent_scratchpad}"),
            ]
        )

        # Create the agent
        agent = create_tool_calling_agent(llm, tools, prompt_template)

        # Create agent executor
        agent_executor = AgentExecutor(
            agent=agent, tools=tools, verbose=verbose, max_iterations=max_iterations, return_intermediate_steps=True
        )

        # Format the input
        input_text = prompt if isinstance(prompt, str) else prompt[-1].get("content", str(prompt))

        # Execute the agent in a thread pool to avoid blocking the event loop
        result = await asyncio.to_thread(agent_executor.invoke, {"input": input_text})

        # Format the response
        return {
            "final_output": result["output"],
            "total_steps": len(result.get("intermediate_steps", [])),
            "steps": [
                {"step": i + 1, "tool": action.tool, "tool_input": action.tool_input, "observation": observation}
                for i, (action, observation) in enumerate(result.get("intermediate_steps", []))
            ],
            "provider": "openrouter" if use_openrouter else "openai",
            "model": effective_model,
        }

    except ImportError as e:
        raise ImportError("LangChain dependencies not installed. Run: poetry add langchain langchain-openai") from e
    except Exception as e:
        logger.error(f"Agent completion failed: {str(e)}")
        raise


def create_langchain_tool(func: callable, name: Optional[str] = None, description: Optional[str] = None):
    """Helper function to create a LangChain tool from a regular Python function.

    Args:
        func: The Python function to convert to a LangChain tool
        name: Optional name for the tool (defaults to function name)
        description: Optional description for the tool (defaults to function docstring)

    Returns:
        A LangChain tool
    """
    try:
        from langchain_core.tools import tool as langchain_tool

        # The tool decorator might not support name parameter in some versions
        # So we'll only use description if provided
        if description:
            return langchain_tool(description=description)(func)
        else:
            return langchain_tool(func)

    except ImportError:
        raise ImportError("LangChain dependencies not installed. Run: poetry add langchain langchain-openai")


def compose_prompt(main_content: str, system_content: Optional[str] = None) -> List[MessageDict]:
    """Helper to compose a prompt with optional system message.

    Args:
        main_content: The main user message content
        system_content: Optional system message content

    Returns:
        A list of message dictionaries
    """
    messages = []
    if system_content:
        messages.append({"role": "system", "content": system_content})
    messages.append({"role": "user", "content": main_content})
    return messages


def create_text_content(text: str) -> TextContent:
    """Create a text content object for multi-modal messages.

    Args:
        text: The text content

    Returns:
        A text content object
    """
    return {"type": "text", "text": text}


def create_image_content(image_base64: str, image_format: str = "jpeg") -> ImageUrlContent:
    """Create an image content object for multi-modal messages.

    Args:
        image_base64: Base64 encoded image data
        image_format: Image format (jpeg, png, etc.)

    Returns:
        An image content object
    """
    return {"type": "image_url", "image_url": {"url": f"data:image/{image_format};base64,{image_base64}"}}


def compose_multimodal_prompt(
    text: str, images: Optional[List[str]] = None, image_format: str = "jpeg", system_content: Optional[str] = None
) -> List[MessageDict]:
    """Helper to compose a multi-modal prompt with text and images.

    Args:
        text: The main text content
        images: List of base64 encoded images
        image_format: Format of the images (jpeg, png, etc.)
        system_content: Optional system message content

    Returns:
        A list of message dictionaries with multi-modal content
    """
    messages = []
    if system_content:
        messages.append({"role": "system", "content": system_content})

    # Create content list with text and images
    content = [create_text_content(text)]
    if images:
        for image_base64 in images:
            content.append(create_image_content(image_base64, image_format))

    messages.append({"role": "user", "content": content})
    return messages
