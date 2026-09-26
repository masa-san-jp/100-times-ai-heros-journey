"""CLIで共有するLLMプロバイダーとモデルの解決処理。"""

from __future__ import annotations

import sys
from typing import Any, Callable, List, Optional, Tuple

from .ollama_client import OllamaClient, OllamaClientError, OllamaConfig
from .provider_clients import (
    AnthropicClient,
    DeepSeekClient,
    OpenAICompatibleClient,
)


DEFAULT_PROVIDER_MODELS = {
    "openai": "o3-mini",
    "anthropic": "claude-3-5-sonnet-20241022",
    "deepseek": "deepseek-reasoner",
}


def choose_installed_model(
    installed_models: List[str],
    preferred_model: str = "gpt-oss:20b",
    interactive: bool = False,
    input_fn: Callable[[str], str] = input,
) -> str:
    """インストール済みモデルから、実行に使うモデルを選ぶ。"""
    models = sorted({model for model in installed_models if model})
    if not models:
        raise ValueError("installed_models must contain at least one model")

    default_index = models.index(preferred_model) + 1 if preferred_model in models else 1
    if not interactive or len(models) == 1:
        return models[default_index - 1]

    print("インストール済みのOllamaモデル:")
    for index, model in enumerate(models, start=1):
        marker = " (推奨)" if index == default_index else ""
        print(f"  {index}. {model}{marker}")

    while True:
        answer = input_fn(f"使用するモデル番号 [{default_index}]: ").strip()
        if not answer:
            return models[default_index - 1]
        try:
            index = int(answer)
        except ValueError:
            print("番号を入力してください。")
            continue
        if 1 <= index <= len(models):
            return models[index - 1]
        print(f"1〜{len(models)}の番号を入力してください。")


def resolve_ollama_model(
    requested_model: Optional[str],
    timeout: int,
    default_model: str = "gpt-oss:20b",
) -> str:
    """Ollamaのモデルを解決し、必要ならダウンロードする。"""
    client = OllamaClient(OllamaConfig(model=default_model, timeout=timeout))
    installed_models = client.list_models()

    if requested_model:
        if requested_model not in installed_models:
            print(f"{requested_model} は未インストールです。ダウンロードします。")
            client.pull_model(requested_model)
        return requested_model

    if installed_models:
        selected = choose_installed_model(
            installed_models,
            preferred_model=default_model,
            interactive=sys.stdin.isatty(),
        )
        print(f"使用モデル: {selected}")
        return selected

    print(f"Ollamaにモデルがありません。{default_model}をダウンロードします。")
    client.pull_model(default_model)
    return default_model


def create_provider_client(
    provider: str,
    requested_model: Optional[str] = None,
    timeout: int = 600,
    num_ctx: Optional[int] = None,
) -> Tuple[Any, str]:
    """既存CLIと同じ既定値でLLMクライアントを生成する。

    Returns:
        ``(client, selected_model)`` の組。
    """
    if provider == "ollama":
        selected_model = resolve_ollama_model(requested_model, timeout)
        num_predict = 8192 if selected_model.startswith("gpt-oss") else 2048
        context_length = (
            num_ctx
            if num_ctx is not None
            else (16384 if selected_model.startswith("gpt-oss") else 8192)
        )
        return (
            OllamaClient(
                OllamaConfig(
                    model=selected_model,
                    timeout=timeout,
                    num_ctx=context_length,
                    num_predict=num_predict,
                )
            ),
            selected_model,
        )

    if provider == "openai":
        model = requested_model or DEFAULT_PROVIDER_MODELS[provider]
        return (
            OpenAICompatibleClient(
                model=model,
                timeout=timeout,
                reasoning_effort="medium",
            ),
            model,
        )
    if provider == "anthropic":
        model = requested_model or DEFAULT_PROVIDER_MODELS[provider]
        return AnthropicClient(model=model, timeout=timeout), model
    if provider == "deepseek":
        model = requested_model or DEFAULT_PROVIDER_MODELS[provider]
        return DeepSeekClient(model=model, timeout=timeout), model
    raise ValueError(f"Unsupported provider: {provider}")


__all__ = [
    "DEFAULT_PROVIDER_MODELS",
    "choose_installed_model",
    "create_provider_client",
    "resolve_ollama_model",
    "OllamaClientError",
]
