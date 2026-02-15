"""
プロット生成モジュール

ヒーローズ・ジャーニー11段階に基づいたプロット生成
"""

import logging
from typing import List, Tuple
from dataclasses import dataclass
from .ollama_client import OllamaClient
from .character_generator import CharacterSet

logger = logging.getLogger(__name__)


# ヒーローズ・ジャーニー11段階の定義
JOURNEY_STAGES = [
    {"stage": 1, "name": "日常世界", "act": "第一幕"},
    {"stage": 2, "name": "冒険への呼びかけ", "act": "第一幕"},
    {"stage": 3, "name": "拒否", "act": "第一幕"},
    {"stage": 4, "name": "師との出会い", "act": "第一幕"},
    {"stage": 5, "name": "第一関門の突破", "act": "第二幕"},
    {"stage": 6, "name": "試練、仲間、敵", "act": "第二幕"},
    {"stage": 7, "name": "最大の試練", "act": "第二幕"},
    {"stage": 8, "name": "報酬", "act": "第二幕"},
    {"stage": 9, "name": "帰路", "act": "第三幕"},
    {"stage": 10, "name": "復活", "act": "第三幕"},
    {"stage": 11, "name": "宝を持ち帰る", "act": "第三幕"}
]


@dataclass(frozen=True)
class PlotStage:
    """プロット段階（イミュータブル）"""
    stage: int
    name: str
    act: str
    description: str


@dataclass(frozen=True)
class Plot:
    """プロット（イミュータブル）"""
    stages: Tuple[PlotStage, ...]
    outline: str

    def to_text(self) -> str:
        """テキスト形式に変換"""
        lines = ["【プロットアウトライン】", self.outline, "", "【各段階の詳細】"]

        for stage in self.stages:
            lines.append(f"\n{stage.stage}. {stage.name} ({stage.act})")
            lines.append(f"  {stage.description}")

        return "\n".join(lines)


class PlotGenerator:
    """プロット生成クラス"""

    def __init__(self, client: OllamaClient):
        """
        Args:
            client: Ollamaクライアント
        """
        self.client = client

    def generate(self, characters: CharacterSet) -> Plot:
        """
        プロットを生成

        Args:
            characters: キャラクターセット

        Returns:
            プロット

        Raises:
            ValueError: 入力が不正な場合
            OllamaClientError: API呼び出しに失敗した場合
        """
        if not isinstance(characters, CharacterSet):
            raise ValueError("characters must be CharacterSet instance")

        # プロット構造を生成（JSON）
        logger.info("プロット構造を生成中")
        stages = self._generate_structure(characters)

        # 統合アウトラインを生成
        logger.info("プロットアウトラインを生成中")
        outline = self._generate_outline(characters)

        return Plot(stages=tuple(stages), outline=outline)

    def _generate_structure(self, characters: CharacterSet) -> List[PlotStage]:
        """プロット構造を生成"""
        characters_desc = characters.to_text()

        stages_desc = "\n".join([
            f"{s['stage']}. {s['name']} ({s['act']})"
            for s in JOURNEY_STAGES
        ])

        prompt = f"""以下のキャラクターとヒーローズ・ジャーニー11段階に基づいて、
各段階の簡潔な展開（各50文字程度）を考えてJSON形式で出力してください。

【キャラクター】
{characters_desc}

【ヒーローズ・ジャーニー11段階】
{stages_desc}

出力形式:
{{
  "stages": [
    {{"stage": 1, "name": "日常世界", "description": "..."}},
    {{"stage": 2, "name": "冒険への呼びかけ", "description": "..."}},
    ...
  ]
}}"""

        result = self.client.chat_json(
            prompt=prompt,
            temperature=0.7
        )

        stages_data = result.get("stages", [])

        if len(stages_data) == 0:
            raise ValueError("No stages returned")

        stages_data = stages_data[:11]

        # 不足分をJOURNEY_STAGESの定義から補完
        for i in range(len(stages_data), 11):
            stage_def = JOURNEY_STAGES[i]
            stages_data.append({
                "stage": stage_def["stage"],
                "name": stage_def["name"],
                "description": f"{stage_def['name']}の展開"
            })

        # PlotStageオブジェクトのリストに変換
        stages = []
        for stage_data in stages_data:
            stage_num = stage_data.get("stage")
            stage_name = stage_data.get("name")
            stage_desc = stage_data.get("description", "")

            # 幕の情報を追加
            act = next(
                (s["act"] for s in JOURNEY_STAGES if s["stage"] == stage_num),
                "不明"
            )

            stages.append(PlotStage(
                stage=stage_num,
                name=stage_name,
                act=act,
                description=stage_desc
            ))

        return stages

    def _generate_outline(self, characters: CharacterSet) -> str:
        """統合アウトラインを生成"""
        characters_desc = characters.to_text()

        prompt = f"""以下のキャラクターを使って、ヒーローズ・ジャーニー11段階の構造に沿った
物語のプロットアウトラインを800文字程度で作成してください。

【キャラクター】
{characters_desc}

【要件】
- ヒーローズ・ジャーニー11段階（日常世界→冒険への呼びかけ→...→宝を持ち帰る）に沿うこと
- 主人公の成長と変化を明確に描くこと
- 第一幕・第二幕・第三幕の構成を意識すること"""

        return self.client.chat(
            prompt=prompt,
            system="あなたは優れた脚本家です。",
            temperature=0.7
        )

    def generate_chapter(
        self,
        stage: PlotStage,
        characters: CharacterSet,
        previous_chapters: List[str]
    ) -> str:
        """
        特定の段階の章を執筆

        Args:
            stage: プロット段階
            characters: キャラクターセット
            previous_chapters: これまでの章の内容（要約）

        Returns:
            章の本文

        Raises:
            ValueError: 入力が不正な場合
            OllamaClientError: API呼び出しに失敗した場合
        """
        if not isinstance(stage, PlotStage):
            raise ValueError("stage must be PlotStage instance")

        if not isinstance(characters, CharacterSet):
            raise ValueError("characters must be CharacterSet instance")

        characters_desc = characters.to_text()

        # これまでの物語の要約
        previous_summary = ""
        if previous_chapters:
            previous_summary = "\n\n【これまでの物語】\n" + "\n".join(previous_chapters)

        prompt = f"""以下の情報に基づいて、第{stage.stage}章「{stage.name}」を執筆してください。

【登場人物】
{characters_desc}
{previous_summary}

【第{stage.stage}章のプロット】
{stage.description}

【執筆要件】
- 文字数: 800〜1200文字程度
- 具体的な出来事、登場人物の感情や行動を詳細に描写すること
- 読者が情景を思い浮かべられるような文学的な表現を使うこと
- 章のタイトルは文学的な表現に改変すること

出力形式:
# 第{stage.stage}章: [文学的なタイトル]

[本文]"""

        return self.client.chat(
            prompt=prompt,
            system="あなたは優れた小説家です。感情豊かで文学的な物語を書いてください。",
            temperature=1.0
        )

    def generate_title(
        self,
        characters: CharacterSet,
        plot: Plot
    ) -> List[str]:
        """
        作品タイトルを生成

        Args:
            characters: キャラクターセット
            plot: プロット

        Returns:
            タイトル候補のリスト（3個）

        Raises:
            ValueError: 入力が不正な場合
            OllamaClientError: API呼び出しに失敗した場合
        """
        if not isinstance(characters, CharacterSet):
            raise ValueError("characters must be CharacterSet instance")

        if not isinstance(plot, Plot):
            raise ValueError("plot must be Plot instance")

        characters_desc = characters.to_text()
        plot_summary = "\n".join([
            f"{s.stage}. {s.name}: {s.description}"
            for s in plot.stages
        ])

        prompt = f"""以下の物語のための印象的な作品タイトルを3つ提案してください。

【登場人物】
{characters_desc}

【物語の流れ】
{plot_summary}

【要件】
- 物語のテーマを表現したタイトル
- 読者の興味を引く魅力的なタイトル
- 日本語で5〜15文字程度

出力形式:
{{
  "titles": [
    {{"title": "タイトル1", "reason": "選定理由"}},
    {{"title": "タイトル2", "reason": "選定理由"}},
    {{"title": "タイトル3", "reason": "選定理由"}}
  ]
}}"""

        result = self.client.chat_json(
            prompt=prompt,
            temperature=0.8
        )

        titles_data = result.get("titles", [])

        if len(titles_data) == 0:
            raise ValueError("No titles returned")

        return [t.get("title", "") for t in titles_data[:3]]
