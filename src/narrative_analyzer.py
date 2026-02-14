"""
ナラティブ分析モジュール

作家の自己ナラティブを分析し、物語要素を抽出
"""

from typing import Dict, List
from dataclasses import dataclass
from .ollama_client import OllamaClient


@dataclass(frozen=True)
class NarrativeInput:
    """ナラティブ入力データ（イミュータブル）"""
    author: str
    missing: str
    status: str
    memories: str
    mission: str
    success: str
    loss: str
    taboo: str
    inhibit: str
    daily: str
    change: str
    acceptance: str
    desire: str

    def to_text(self) -> str:
        """テキスト形式に変換"""
        return "\n".join([
            f"自己紹介: {self.author}",
            f"欠けているもの: {self.missing}",
            f"現在の状態: {self.status}",
            f"記憶: {self.memories}",
            f"使命: {self.mission}",
            f"成功のイメージ: {self.success}",
            f"失うもの: {self.loss}",
            f"タブー: {self.taboo}",
            f"抑制するもの: {self.inhibit}",
            f"日常: {self.daily}",
            f"変化のきっかけ: {self.change}",
            f"受容: {self.acceptance}",
            f"願望: {self.desire}"
        ])


@dataclass(frozen=True)
class NarrativeAnalysis:
    """ナラティブ分析結果（イミュータブル）"""
    desire: str  # 願望分析
    suppression: str  # 抑圧分析
    conflict: str  # 葛藤分析
    elements: List[str]  # ナラティブ要素（10個）


class NarrativeAnalyzer:
    """ナラティブ分析クラス"""

    def __init__(self, client: OllamaClient):
        """
        Args:
            client: Ollamaクライアント
        """
        self.client = client

    def analyze(self, narrative: NarrativeInput) -> NarrativeAnalysis:
        """
        ナラティブを分析

        Args:
            narrative: ナラティブ入力データ

        Returns:
            分析結果

        Raises:
            ValueError: 入力が不正な場合
            OllamaClientError: API呼び出しに失敗した場合
        """
        if not isinstance(narrative, NarrativeInput):
            raise ValueError("narrative must be NarrativeInput instance")

        narrative_text = narrative.to_text()

        # 願望分析
        desire = self._analyze_desire(narrative_text)

        # 抑圧分析
        suppression = self._analyze_suppression(narrative_text)

        # 葛藤分析
        conflict = self._analyze_conflict(narrative_text)

        # ナラティブ要素抽出
        elements = self._extract_elements(desire, suppression, conflict)

        return NarrativeAnalysis(
            desire=desire,
            suppression=suppression,
            conflict=conflict,
            elements=elements
        )

    def _analyze_desire(self, narrative_text: str) -> str:
        """願望分析"""
        prompt = f"""以下の資料を網羅的に分析して、この作家が切望していること、
手に入れたいと渇望していることについて、400文字程度でレポートしてください。

{narrative_text}"""

        return self.client.chat(
            prompt=prompt,
            system="あなたは深層心理学の専門家です。",
            temperature=0.5
        )

    def _analyze_suppression(self, narrative_text: str) -> str:
        """抑圧分析"""
        prompt = f"""以下の資料を網羅的に分析して、この作家が抑圧している根源的な
感情について、400文字程度でレポートしてください。

{narrative_text}"""

        return self.client.chat(
            prompt=prompt,
            system="あなたは深層心理学の専門家です。",
            temperature=0.5
        )

    def _analyze_conflict(self, narrative_text: str) -> str:
        """葛藤分析"""
        prompt = f"""以下の資料を網羅的に分析して、この作家が抱えている自己矛盾と
葛藤について、400文字程度でレポートしてください。

{narrative_text}"""

        return self.client.chat(
            prompt=prompt,
            system="あなたは深層心理学の専門家です。",
            temperature=0.5
        )

    def _extract_elements(
        self,
        desire: str,
        suppression: str,
        conflict: str
    ) -> List[str]:
        """ナラティブ要素抽出"""
        prompt = f"""以下の分析結果から、作家の備えている特有のナラティブを形成する
要素を抽象化して、10個に分類してリストnarrativeに格納してください。

分析結果:
- 願望: {desire[:200]}...
- 抑圧: {suppression[:200]}...
- 葛藤: {conflict[:200]}...

出力形式: {{"narrative": ["要素1", "要素2", ..., "要素10"]}}"""

        result = self.client.chat_json(
            prompt=prompt,
            temperature=0.3
        )

        elements = result.get("narrative", [])

        if not isinstance(elements, list) or len(elements) != 10:
            raise ValueError(f"Expected 10 narrative elements, got {len(elements)}")

        return elements
