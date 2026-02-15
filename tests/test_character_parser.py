"""キャラクター名パースのテスト"""

from src.character_generator import CharacterGenerator
from src.ollama_client import OllamaClient, OllamaConfig


def _parser():
    """パーサーメソッドにアクセスするためにインスタンスを作成"""
    client = OllamaClient(OllamaConfig())
    return CharacterGenerator(client)


class TestParseCharacterResponse:
    def test_standard_format(self):
        gen = _parser()
        response = "名前: 太郎\n\n勇敢な青年。冒険を求めている。"
        name, profile = gen._parse_character_response(response)
        assert name == "太郎"
        assert "勇敢な青年" in profile

    def test_fullwidth_colon(self):
        gen = _parser()
        response = "名前：花子\n\n知恵の使者。"
        name, profile = gen._parse_character_response(response)
        assert name == "花子"
        assert "知恵の使者" in profile

    def test_markdown_bold(self):
        gen = _parser()
        response = "**名前:** 次郎\n\n援助者のプロフィール。"
        name, profile = gen._parse_character_response(response)
        assert name == "次郎"

    def test_markdown_bold_fullwidth(self):
        gen = _parser()
        response = "**名前：** 三郎\n\nプロフィール。"
        name, profile = gen._parse_character_response(response)
        assert name == "三郎"

    def test_english_name_label(self):
        gen = _parser()
        response = "Name: Taro\n\nA brave hero."
        name, profile = gen._parse_character_response(response)
        assert name == "Taro"

    def test_fallback_first_line(self):
        gen = _parser()
        response = "太郎\n\n勇敢な青年。"
        name, profile = gen._parse_character_response(response)
        assert name == "太郎"
        assert "勇敢な青年" in profile

    def test_empty_profile_uses_full_response(self):
        gen = _parser()
        response = "名前: 太郎"
        name, profile = gen._parse_character_response(response)
        assert name == "太郎"
        # プロフィールが空の場合、レスポンス全体が使用される
        assert "名前" in profile
