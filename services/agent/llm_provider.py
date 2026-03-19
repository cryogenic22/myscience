"""Configurable LLM provider for the agent layer.

Supports OpenAI and Anthropic via langchain's init_chat_model.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from config import AppConfig

logger = logging.getLogger(__name__)


def get_agent_llm(config: AppConfig) -> BaseChatModel:
    """Create an LLM instance from agent config.

    Uses langchain init_chat_model for provider-agnostic initialization.
    Reads from config.agent.llm_provider and config.agent.llm_model.
    """
    provider = config.agent.llm_provider
    model = config.agent.llm_model
    temperature = config.agent.llm_temperature

    model_id = f"{provider}:{model}" if provider else model
    logger.info("Initializing agent LLM: %s (temperature=%.2f)", model_id, temperature)

    return init_chat_model(model_id, temperature=temperature)
