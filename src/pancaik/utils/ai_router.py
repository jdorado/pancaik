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


class MessageDict(TypedDict):
    """Type definition for a chat message."""

    role: str
    content: str


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

    def __init__(self, default_provider: Provider = Provider.OPENAI, use_openrouter: bool = False, max_concurrent_requests: int = 100):
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
            preview = messages[-1]["content"][:50].strip().replace("\n", " ")
            logger.info(f"{effective_provider.name} {effective_model}: {preview}")

            # Prepare kwargs for API call, only including parameters that have values
            api_kwargs = kwargs.copy()
            if max_tokens is not None:
                api_kwargs["max_tokens"] = max_tokens
            if temperature is not None:
                api_kwargs["temperature"] = temperature

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
        **kwargs: Additional arguments to pass to the provider

    Returns:
        The model's completion text or structured response
    """
    # Use the appropriate router based on use_openrouter flag
    router = openrouter if use_openrouter else default_router

    # Create kwargs for the router's get_completion method
    router_kwargs = kwargs.copy()
    if temperature is not None:
        router_kwargs["temperature"] = temperature
    if max_tokens is not None:
        router_kwargs["max_tokens"] = max_tokens

    return await router.get_completion(
        prompt=prompt, model_id=model_id, use_openrouter=use_openrouter, response_model=response_model, **router_kwargs
    )


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
