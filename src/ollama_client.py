"""
Ollama APIクライアント

Ollama APIとの通信を担当するクライアントクラス
"""

import requests
import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass


@dataclass(frozen=True)
class OllamaConfig:
    """Ollama設定（イミュータブル）"""
    base_url: str = "http://localhost:11434"
    model: str = "gpt-oss:20b"
    timeout: int = 300


class OllamaClientError(Exception):
    """Ollamaクライアントエラー"""
    pass


class OllamaClient:
    """Ollama APIクライアント"""

    def __init__(self, config: Optional[OllamaConfig] = None):
        """
        Args:
            config: Ollama設定（省略時はデフォルト設定）
        """
        self.config = config or OllamaConfig()

    def chat(
        self,
        prompt: str,
        system: str = "",
        temperature: float = 0.7,
        model: Optional[str] = None
    ) -> str:
        """
        テキスト生成

        Args:
            prompt: ユーザープロンプト
            system: システムプロンプト
            temperature: 生成の創造性（0.0〜2.0）
            model: 使用モデル（省略時は設定値を使用）

        Returns:
            生成されたテキスト

        Raises:
            OllamaClientError: API呼び出しに失敗した場合
        """
        if not prompt or not isinstance(prompt, str):
            raise ValueError("prompt must be a non-empty string")

        if not isinstance(temperature, (int, float)) or temperature < 0 or temperature > 2:
            raise ValueError("temperature must be between 0.0 and 2.0")

        messages = self._build_messages(system, prompt)
        payload = self._build_payload(
            messages=messages,
            temperature=temperature,
            model=model or self.config.model
        )

        try:
            response = requests.post(
                f"{self.config.base_url}/api/chat",
                json=payload,
                timeout=self.config.timeout
            )
            response.raise_for_status()

            result = response.json()
            content = result.get("message", {}).get("content", "")

            if not content:
                raise OllamaClientError("Empty response from Ollama API")

            return content

        except requests.exceptions.Timeout:
            raise OllamaClientError(
                f"Request timeout after {self.config.timeout} seconds"
            )
        except requests.exceptions.ConnectionError:
            raise OllamaClientError(
                f"Failed to connect to Ollama server at {self.config.base_url}"
            )
        except requests.exceptions.HTTPError as e:
            raise OllamaClientError(f"HTTP error: {e}")
        except json.JSONDecodeError:
            raise OllamaClientError("Invalid JSON response from server")
        except Exception as e:
            raise OllamaClientError(f"Unexpected error: {e}")

    def chat_json(
        self,
        prompt: str,
        system: str = "",
        temperature: float = 0.3,
        model: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        JSON形式でデータ生成

        Args:
            prompt: ユーザープロンプト
            system: システムプロンプト
            temperature: 生成の創造性（デフォルト0.3で精度重視）
            model: 使用モデル

        Returns:
            JSON形式のデータ（辞書型）

        Raises:
            OllamaClientError: API呼び出しまたはJSONパースに失敗した場合
        """
        if not prompt or not isinstance(prompt, str):
            raise ValueError("prompt must be a non-empty string")

        # JSON生成用のシステムプロンプト
        json_system = "常にJSON形式で応答してください。出力はJSONのみで、説明文は含めないでください。"
        if system:
            json_system = f"{json_system}\n\n{system}"

        messages = self._build_messages(json_system, prompt)
        payload = self._build_payload(
            messages=messages,
            temperature=temperature,
            model=model or self.config.model,
            format_json=True
        )

        try:
            response = requests.post(
                f"{self.config.base_url}/api/chat",
                json=payload,
                timeout=self.config.timeout
            )
            response.raise_for_status()

            result = response.json()
            content = result.get("message", {}).get("content", "")

            if not content:
                raise OllamaClientError("Empty response from Ollama API")

            # JSONパース
            try:
                parsed_json = json.loads(content)
                return parsed_json
            except json.JSONDecodeError as e:
                raise OllamaClientError(f"Failed to parse JSON response: {e}\nContent: {content[:200]}")

        except requests.exceptions.Timeout:
            raise OllamaClientError(
                f"Request timeout after {self.config.timeout} seconds"
            )
        except requests.exceptions.ConnectionError:
            raise OllamaClientError(
                f"Failed to connect to Ollama server at {self.config.base_url}"
            )
        except requests.exceptions.HTTPError as e:
            raise OllamaClientError(f"HTTP error: {e}")
        except Exception as e:
            if isinstance(e, OllamaClientError):
                raise
            raise OllamaClientError(f"Unexpected error: {e}")

    def _build_messages(self, system: str, prompt: str) -> List[Dict[str, str]]:
        """メッセージリストを構築（イミュータブル）"""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return messages

    def _build_payload(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        model: str,
        format_json: bool = False
    ) -> Dict[str, Any]:
        """APIペイロードを構築（イミュータブル）"""
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": False
        }

        if format_json:
            payload["format"] = "json"

        return payload

    def health_check(self) -> bool:
        """
        Ollamaサーバーの接続確認

        Returns:
            接続可能な場合True、それ以外はFalse
        """
        try:
            response = requests.get(
                f"{self.config.base_url}/api/tags",
                timeout=5
            )
            return response.status_code == 200
        except Exception:
            return False

    def list_models(self) -> List[str]:
        """
        利用可能なモデル一覧を取得

        Returns:
            モデル名のリスト

        Raises:
            OllamaClientError: API呼び出しに失敗した場合
        """
        try:
            response = requests.get(
                f"{self.config.base_url}/api/tags",
                timeout=10
            )
            response.raise_for_status()

            data = response.json()
            models = data.get("models", [])

            return [model.get("name", "") for model in models if model.get("name")]

        except Exception as e:
            raise OllamaClientError(f"Failed to list models: {e}")
