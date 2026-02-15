"""データクラスのテスト"""

import dataclasses
import pytest

from src.ollama_client import OllamaConfig
from src.narrative_analyzer import NarrativeInput, NarrativeAnalysis
from src.character_generator import Character, CharacterSet
from src.plot_generator import PlotStage, Plot, JOURNEY_STAGES


# === NarrativeInput ===

def _make_narrative_input(**kwargs):
    defaults = {
        "author": "テスト作家",
        "missing": "欠けているもの",
        "status": "現在の状態",
        "memories": "記憶",
        "mission": "使命",
        "success": "成功",
        "loss": "失うもの",
        "taboo": "タブー",
        "inhibit": "抑制",
        "daily": "日常",
        "change": "変化",
        "acceptance": "受容",
        "desire": "願望",
    }
    defaults.update(kwargs)
    return NarrativeInput(**defaults)


class TestNarrativeInput:
    def test_creation(self):
        ni = _make_narrative_input()
        assert ni.author == "テスト作家"
        assert ni.desire == "願望"

    def test_to_text_contains_all_fields(self):
        ni = _make_narrative_input()
        text = ni.to_text()
        assert "テスト作家" in text
        assert "願望" in text
        assert "使命" in text

    def test_frozen(self):
        ni = _make_narrative_input()
        with pytest.raises(dataclasses.FrozenInstanceError):
            ni.author = "別の作家"


# === NarrativeAnalysis ===

class TestNarrativeAnalysis:
    def test_creation(self):
        na = NarrativeAnalysis(
            desire="願望分析",
            suppression="抑圧分析",
            conflict="葛藤分析",
            elements=("要素1", "要素2", "要素3")
        )
        assert na.desire == "願望分析"
        assert len(na.elements) == 3

    def test_elements_is_tuple(self):
        na = NarrativeAnalysis(
            desire="d", suppression="s", conflict="c",
            elements=("a", "b")
        )
        assert isinstance(na.elements, tuple)

    def test_frozen(self):
        na = NarrativeAnalysis(
            desire="d", suppression="s", conflict="c",
            elements=("a",)
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            na.desire = "changed"


# === Character / CharacterSet ===

def _make_character(role="protagonist", name="太郎", profile="主人公のプロフィール"):
    return Character(role=role, name=name, profile=profile)


class TestCharacter:
    def test_creation(self):
        c = _make_character()
        assert c.role == "protagonist"
        assert c.name == "太郎"

    def test_frozen(self):
        c = _make_character()
        with pytest.raises(dataclasses.FrozenInstanceError):
            c.name = "次郎"


class TestCharacterSet:
    def test_to_text(self):
        cs = CharacterSet(
            protagonist=_make_character("protagonist", "主人公", "profile1"),
            messenger=_make_character("messenger", "使者", "profile2"),
            supporter=_make_character("supporter", "援助者", "profile3"),
            adversary=_make_character("adversary", "敵対者", "profile4"),
        )
        text = cs.to_text()
        assert "【主人公】主人公" in text
        assert "【使者】使者" in text
        assert "【援助者】援助者" in text
        assert "【敵対者】敵対者" in text


# === PlotStage / Plot ===

class TestPlotStage:
    def test_creation(self):
        ps = PlotStage(stage=1, name="日常世界", act="第一幕", description="平穏な日常")
        assert ps.stage == 1
        assert ps.name == "日常世界"

    def test_frozen(self):
        ps = PlotStage(stage=1, name="日常世界", act="第一幕", description="desc")
        with pytest.raises(dataclasses.FrozenInstanceError):
            ps.description = "changed"


class TestPlot:
    def test_to_text(self):
        stages = tuple(
            PlotStage(stage=s["stage"], name=s["name"], act=s["act"], description="展開")
            for s in JOURNEY_STAGES
        )
        plot = Plot(stages=stages, outline="アウトライン")
        text = plot.to_text()
        assert "アウトライン" in text
        assert "日常世界" in text
        assert "宝を持ち帰る" in text

    def test_stages_is_tuple(self):
        stages = (PlotStage(stage=1, name="n", act="a", description="d"),)
        plot = Plot(stages=stages, outline="o")
        assert isinstance(plot.stages, tuple)


# === OllamaConfig ===

class TestOllamaConfig:
    def test_defaults(self):
        config = OllamaConfig()
        assert config.base_url == "http://localhost:11434"
        assert config.model == "gpt-oss:20b"
        assert config.timeout == 300

    def test_custom(self):
        config = OllamaConfig(base_url="http://example:1234", model="test", timeout=60)
        assert config.base_url == "http://example:1234"

    def test_frozen(self):
        config = OllamaConfig()
        with pytest.raises(dataclasses.FrozenInstanceError):
            config.model = "other"
