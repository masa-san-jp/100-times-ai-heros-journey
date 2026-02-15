"""OllamaClientのテスト"""

import pytest

from src.ollama_client import OllamaClient, OllamaConfig


@pytest.fixture
def client():
    return OllamaClient(OllamaConfig())


class TestValidation:
    def test_empty_prompt_raises(self, client):
        with pytest.raises(ValueError, match="non-empty string"):
            client.chat(prompt="")

    def test_none_prompt_raises(self, client):
        with pytest.raises(ValueError, match="non-empty string"):
            client.chat(prompt=None)

    def test_temperature_too_low(self, client):
        with pytest.raises(ValueError, match="temperature"):
            client.chat(prompt="hello", temperature=-0.1)

    def test_temperature_too_high(self, client):
        with pytest.raises(ValueError, match="temperature"):
            client.chat(prompt="hello", temperature=2.1)

    def test_valid_temperature_boundary(self, client):
        """境界値はバリデーションを通過する（接続エラーは許容）"""
        # temperature=0.0 と 2.0 はバリデーションを通過するべき
        # 実際のAPI呼び出しは失敗するが、ValueError は出ない
        with pytest.raises(Exception) as exc_info:
            client.chat(prompt="hello", temperature=0.0)
        assert not isinstance(exc_info.value, ValueError)

        with pytest.raises(Exception) as exc_info:
            client.chat(prompt="hello", temperature=2.0)
        assert not isinstance(exc_info.value, ValueError)

    def test_chat_json_empty_prompt_raises(self, client):
        with pytest.raises(ValueError, match="non-empty string"):
            client.chat_json(prompt="")


class TestBuildMessages:
    def test_with_system(self, client):
        messages = client._build_messages("system msg", "user msg")
        assert len(messages) == 2
        assert messages[0] == {"role": "system", "content": "system msg"}
        assert messages[1] == {"role": "user", "content": "user msg"}

    def test_without_system(self, client):
        messages = client._build_messages("", "user msg")
        assert len(messages) == 1
        assert messages[0] == {"role": "user", "content": "user msg"}


class TestBuildPayload:
    def test_temperature_in_options(self, client):
        payload = client._build_payload(
            messages=[{"role": "user", "content": "test"}],
            temperature=0.5,
            model="test-model"
        )
        assert "temperature" not in payload
        assert payload["options"]["temperature"] == 0.5

    def test_format_json(self, client):
        payload = client._build_payload(
            messages=[],
            temperature=0.3,
            model="test",
            format_json=True
        )
        assert payload["format"] == "json"

    def test_no_format_by_default(self, client):
        payload = client._build_payload(
            messages=[],
            temperature=0.3,
            model="test"
        )
        assert "format" not in payload

    def test_stream_is_false(self, client):
        payload = client._build_payload(
            messages=[],
            temperature=0.7,
            model="test"
        )
        assert payload["stream"] is False
