"""
プロット生成モジュール

Colab版のヒーローズ・ジャーニー12段階に基づいたプロット生成。
旧11段階版は ``stage_definitions=JOURNEY_STAGES`` で明示的に選択できる。
ほかの物語構造は ``STORY_STRUCTURES`` から ``get_story_structure`` で選ぶ。
"""

import logging
from typing import Any, List, Mapping, Optional, Sequence, Tuple
from dataclasses import dataclass
from .ollama_client import OllamaClient
from .character_generator import CharacterSet

logger = logging.getLogger(__name__)


# 旧来のヒーローズ・ジャーニー11段階の定義。
# 互換性のため残し、標準では12段階版を使う。
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

# Colab版の統合プロットで使われていた12段階版。
JOURNEY_STAGES_12 = [
    {"stage": 1, "name": "日常世界", "act": "第一幕"},
    {"stage": 2, "name": "冒険への呼びかけ", "act": "第一幕"},
    {"stage": 3, "name": "拒否", "act": "第一幕"},
    {"stage": 4, "name": "師との出会い", "act": "第一幕"},
    {"stage": 5, "name": "第一関門の突破", "act": "第二幕"},
    {"stage": 6, "name": "試練、仲間、敵", "act": "第二幕"},
    {"stage": 7, "name": "最も危険な場所への接近", "act": "第二幕"},
    {"stage": 8, "name": "最大の試練", "act": "第二幕"},
    {"stage": 9, "name": "報酬", "act": "第三幕"},
    {"stage": 10, "name": "帰路", "act": "第三幕"},
    {"stage": 11, "name": "復活", "act": "第三幕"},
    {"stage": 12, "name": "宝を持ち帰る", "act": "第三幕"},
]


# 以下の構造の段名は二次資料（Wikipedia と解説記事、確認日2026-11-25）による。
# 一次資料の確認は arayashiki-kb のイシュー #39 で進めている。
# "description" はプロンプトに入れる各段の役割。

# ダン・ハーモンのストーリーサークル（8段）。
# 幕の割り当ては暫定（出典で確認できていない）。
STORY_CIRCLE_8 = [
    {"stage": 1, "name": "You", "act": "第一幕",
     "description": "主人公が居心地のよい日常にいる"},
    {"stage": 2, "name": "Need", "act": "第一幕",
     "description": "主人公が何かを欲する、または欠けたものに気づく"},
    {"stage": 3, "name": "Go", "act": "第二幕",
     "description": "主人公が見知らぬ状況へ踏み出す"},
    {"stage": 4, "name": "Search", "act": "第二幕",
     "description": "新しい状況に適応しようともがき、試される"},
    {"stage": 5, "name": "Find", "act": "第二幕",
     "description": "求めていたものを見つける"},
    {"stage": 6, "name": "Take", "act": "第二幕",
     "description": "手に入れた代わりに重い代償を払う"},
    {"stage": 7, "name": "Return", "act": "第三幕",
     "description": "元の日常へ戻る"},
    {"stage": 8, "name": "Change", "act": "第三幕",
     "description": "変化した主人公として日常に向き合う"},
]

# ブレイク・スナイダーのセーブ・ザ・キャット（15段）。
# 13〜15が第三幕であることだけ確認済み。1〜6と7〜12の幕は暫定。
SAVE_THE_CAT_15 = [
    {"stage": 1, "name": "Opening Image", "act": "第一幕",
     "description": "変化する前の主人公と世界を一場面で見せる"},
    {"stage": 2, "name": "Theme Stated", "act": "第一幕",
     "description": "誰かが物語のテーマをそれとなく口にする"},
    {"stage": 3, "name": "Set-Up", "act": "第一幕",
     "description": "主人公の日常、欠点、周囲の人物を示す"},
    {"stage": 4, "name": "Catalyst", "act": "第一幕",
     "description": "日常を壊す出来事が起きる"},
    {"stage": 5, "name": "Debate", "act": "第一幕",
     "description": "主人公が進むべきか迷い、ためらう"},
    {"stage": 6, "name": "Break into Two", "act": "第一幕",
     "description": "主人公が自ら決断し、新しい世界へ入る"},
    {"stage": 7, "name": "B Story", "act": "第二幕",
     "description": "テーマを映す別の人間関係が始まる"},
    {"stage": 8, "name": "Fun and Games", "act": "第二幕",
     "description": "新しい世界での冒険や試みを描く"},
    {"stage": 9, "name": "Midpoint", "act": "第二幕",
     "description": "偽りの勝利か偽りの敗北で、賭け金が上がる"},
    {"stage": 10, "name": "Bad Guys Close In", "act": "第二幕",
     "description": "外の敵と内の弱さが主人公を追い詰める"},
    {"stage": 11, "name": "All Is Lost", "act": "第二幕",
     "description": "主人公がすべてを失ったように見える"},
    {"stage": 12, "name": "Dark Night of the Soul", "act": "第二幕",
     "description": "絶望の中で主人公が自分と向き合う"},
    {"stage": 13, "name": "Break into Three", "act": "第三幕",
     "description": "テーマに気づき、解決の糸口をつかむ"},
    {"stage": 14, "name": "Finale", "act": "第三幕",
     "description": "学んだことを使って問題を解決する"},
    {"stage": 15, "name": "Final Image", "act": "第三幕",
     "description": "変化した主人公と世界を、最初の場面と対にして見せる"},
]

# 起承転結（4段）。幕の割り当ては暫定（出典で確認できていない）。
KISHOTENKETSU_4 = [
    {"stage": 1, "name": "起", "act": "第一幕",
     "description": "導入。人物と状況を示す"},
    {"stage": 2, "name": "承", "act": "第二幕",
     "description": "展開。起で示したことを深める"},
    {"stage": 3, "name": "転", "act": "第二幕",
     "description": "転換・ひねり。予想しない出来事で見え方が変わる"},
    {"stage": 4, "name": "結", "act": "第三幕",
     "description": "結果。転を受けて全体をまとめる"},
]


@dataclass(frozen=True)
class StoryStructure:
    """選択できる物語構造。"""

    name: str
    label: str
    stages: Tuple[Mapping[str, Any], ...]

    @property
    def stage_count(self) -> int:
        return len(self.stages)


DEFAULT_STRUCTURE = "journey-12"

STORY_STRUCTURES = {
    "journey-12": StoryStructure(
        "journey-12", "ヒーローズ・ジャーニー", tuple(JOURNEY_STAGES_12)
    ),
    "journey-11": StoryStructure(
        "journey-11", "ヒーローズ・ジャーニー", tuple(JOURNEY_STAGES)
    ),
    "story-circle-8": StoryStructure(
        "story-circle-8", "ストーリーサークル", tuple(STORY_CIRCLE_8)
    ),
    "save-the-cat-15": StoryStructure(
        "save-the-cat-15", "セーブ・ザ・キャット", tuple(SAVE_THE_CAT_15)
    ),
    "kishotenketsu-4": StoryStructure(
        "kishotenketsu-4", "起承転結", tuple(KISHOTENKETSU_4)
    ),
}


def get_story_structure(name: str) -> StoryStructure:
    """名前から物語構造を返す。未知の名前は ValueError。"""
    try:
        return STORY_STRUCTURES[name]
    except KeyError:
        choices = ", ".join(STORY_STRUCTURES)
        raise ValueError(f"unknown structure: {name} (choices: {choices})") from None


def _stages_prompt_text(definitions: Sequence[Mapping[str, Any]]) -> str:
    lines = []
    for s in definitions:
        line = f"{s['stage']}. {s['name']} ({s['act']})"
        if s.get("description"):
            line += f": {s['description']}"
        lines.append(line)
    return "\n".join(lines)


@dataclass(frozen=True)
class PlotStage:
    """プロット段階（イミュータブル）"""
    stage: int
    name: str
    act: str
    description: str


@dataclass(frozen=True)
class TextGenerationResult:
    """テキスト生成本文と、取得できた終了理由。"""

    text: str
    done_reason: Optional[str] = None


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

    def generate(
        self,
        characters: CharacterSet,
        plot_type: str = "旅 (Quest)",
        world: Optional[Any] = None,
        skeleton: Optional[Any] = None,
        stage_definitions: Optional[Sequence[Mapping[str, Any]]] = None,
        structure_label: Optional[str] = None,
    ) -> Plot:
        """
        プロットを生成

        Args:
            characters: キャラクターセット
            plot_type: 物語の構造タイプ
            world: 物語世界（文字列またはto_text()を持つオブジェクト）
            skeleton: プロット骨子（文字列またはto_text()を持つオブジェクト）
            stage_definitions: 使用する物語構造の段階定義（既定は12段階）
            structure_label: プロンプトに書く構造名（既定は「ヒーローズ・ジャーニー」）

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
        stages = self._generate_structure(
            characters,
            plot_type=plot_type,
            world=world,
            skeleton=skeleton,
            stage_definitions=stage_definitions,
            structure_label=structure_label,
        )

        # 統合アウトラインを生成
        logger.info("プロットアウトラインを生成中")
        outline = self._generate_outline(
            characters,
            plot_type=plot_type,
            world=world,
            skeleton=skeleton,
            stage_definitions=stage_definitions,
            structure_label=structure_label,
        )

        return Plot(stages=tuple(stages), outline=outline)

    def _generate_structure(
        self,
        characters: CharacterSet,
        plot_type: str = "旅 (Quest)",
        world: Optional[Any] = None,
        skeleton: Optional[Any] = None,
        stage_definitions: Optional[Sequence[Mapping[str, Any]]] = None,
        structure_label: Optional[str] = None,
    ) -> List[PlotStage]:
        """プロット構造を生成"""
        characters_desc = characters.to_text()
        world_desc = self._context_text(world)
        skeleton_desc = self._context_text(skeleton)
        definitions = list(stage_definitions or JOURNEY_STAGES_12)
        stage_count = len(definitions)
        label = structure_label or "ヒーローズ・ジャーニー"
        stages_desc = _stages_prompt_text(definitions)
        first, second = definitions[0]["name"], definitions[min(1, stage_count - 1)]["name"]

        prompt = f"""以下のキャラクターと物語資料、{label}{stage_count}段階に基づいて、
各段階の簡潔な展開（各50文字程度）を考えてJSON形式で出力してください。

【キャラクター】
{characters_desc}

【物語形式】
{plot_type}

【物語世界】
{world_desc or '指定なし'}

【プロット骨子】
{skeleton_desc or '指定なし'}

【{label}{stage_count}段階】
{stages_desc}

出力形式:
{{
  "stages": [
    {{"stage": 1, "name": "{first}", "description": "..."}},
    {{"stage": 2, "name": "{second}", "description": "..."}},
    ...
  ]
}}"""

        try:
            result = self.client.chat_json(
                prompt=prompt,
                temperature=0.7,
                num_predict=1536,
            )
        except TypeError as exc:
            if "num_predict" not in str(exc):
                raise
            result = self.client.chat_json(prompt=prompt, temperature=0.7)

        stages_data = result.get("stages", [])

        if len(stages_data) == 0:
            raise ValueError("No stages returned")

        # 段の番号・名前・幕は選んだ構造の定義で固定し、LLMからは展開の説明だけを使う。
        # LLMが段名を言い換えても、プロットは定義どおりの段で並ぶ。
        stages = []
        for i, stage_def in enumerate(definitions):
            stage_data = stages_data[i] if i < len(stages_data) else {}
            if not isinstance(stage_data, Mapping):
                stage_data = {}
            stage_desc = str(stage_data.get("description") or "").strip()
            stages.append(PlotStage(
                stage=stage_def["stage"],
                name=stage_def["name"],
                act=stage_def["act"],
                description=stage_desc or f"{stage_def['name']}の展開",
            ))

        return stages

    def _generate_outline(
        self,
        characters: CharacterSet,
        plot_type: str = "旅 (Quest)",
        world: Optional[Any] = None,
        skeleton: Optional[Any] = None,
        stage_definitions: Optional[Sequence[Mapping[str, Any]]] = None,
        structure_label: Optional[str] = None,
    ) -> str:
        """統合アウトラインを生成"""
        characters_desc = characters.to_text()
        world_desc = self._context_text(world)
        skeleton_desc = self._context_text(skeleton)
        definitions = list(stage_definitions or JOURNEY_STAGES_12)
        stage_count = len(definitions)
        label = structure_label or "ヒーローズ・ジャーニー"
        stages_desc = _stages_prompt_text(definitions)
        flow = "→".join(
            [definitions[0]["name"], definitions[min(1, stage_count - 1)]["name"], "...", definitions[-1]["name"]]
        )

        prompt = f"""以下のキャラクターと物語資料を使って、{label}{stage_count}段階の構造に沿った
物語のプロットアウトラインを800文字程度で作成してください。

【キャラクター】
{characters_desc}

【物語形式】
{plot_type}

【物語世界】
{world_desc or '指定なし'}

【プロット骨子】
{skeleton_desc or '指定なし'}

【{label}の段階】
{stages_desc}

【要件】
- 上記の全段階（{flow}）に沿うこと
- 主人公の成長と変化を明確に描くこと
- 第一幕・第二幕・第三幕の構成を意識すること"""

        try:
            return self.client.chat(
                prompt=prompt,
                system="あなたは優れた脚本家です。",
                temperature=0.7,
                num_predict=1536,
            )
        except TypeError as exc:
            if "num_predict" not in str(exc):
                raise
            return self.client.chat(
                prompt=prompt,
                system="あなたは優れた脚本家です。",
                temperature=0.7,
            )

    @staticmethod
    def _context_text(value: Optional[Any]) -> str:
        """文字列または ``to_text`` オブジェクトをプロンプト用文字列にする。"""
        if value is None:
            return ""
        if hasattr(value, "to_text"):
            return str(value.to_text())
        return str(value)

    def generate_chapter(
        self,
        stage: PlotStage,
        characters: CharacterSet,
        previous_chapters: List[str],
        client: Optional[Any] = None,
        continuation_text: Optional[str] = None,
    ) -> str:
        """特定の段階の章を執筆（後方互換の本文だけを返す）。"""
        return self.generate_chapter_result(
            stage=stage,
            characters=characters,
            previous_chapters=previous_chapters,
            client=client,
            continuation_text=continuation_text,
        ).text

    def generate_chapter_result(
        self,
        stage: PlotStage,
        characters: CharacterSet,
        previous_chapters: List[str],
        client: Optional[Any] = None,
        continuation_text: Optional[str] = None,
    ) -> TextGenerationResult:
        """
        特定の段階の章を執筆し、終了理由も可能なら返す。

        Args:
            stage: プロット段階
            characters: キャラクターセット
            previous_chapters: これまでの章の内容（要約）
            continuation_text: 途中で切れた本文。指定時は続きを生成する。

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

        prompt = self._build_chapter_prompt(
            stage=stage,
            characters=characters,
            previous_chapters=previous_chapters,
            continuation_text=continuation_text,
        )

        use_client = client or self.client
        if hasattr(use_client, "chat_with_metadata"):
            response = use_client.chat_with_metadata(
                prompt=prompt,
                system="あなたは優れた小説家です。感情豊かで文学的な物語を書いてください。",
                temperature=1.0,
            )
            return TextGenerationResult(
                text=str(response.content),
                done_reason=response.done_reason,
            )

        return TextGenerationResult(
            text=use_client.chat(
                prompt=prompt,
                system="あなたは優れた小説家です。感情豊かで文学的な物語を書いてください。",
                temperature=1.0,
            )
        )

    @staticmethod
    def _build_chapter_prompt(
        stage: PlotStage,
        characters: CharacterSet,
        previous_chapters: List[str],
        continuation_text: Optional[str] = None,
    ) -> str:
        """章本文または途中からの続き用プロンプトを組み立てる。"""
        characters_desc = characters.to_text()
        previous_summary = ""
        if previous_chapters:
            previous_summary = "\n\n【これまでの物語】\n" + "\n".join(previous_chapters)

        if continuation_text:
            # コンテキストを無制限に増やさず、直近の本文だけを渡す。
            existing = continuation_text[-6000:]
            return f"""以下の章本文は生成途中で終わっています。既出の文章を繰り返さず、末尾の直後から自然に続きを書いて章を完結させてください。

【章】
第{stage.stage}章「{stage.name}」

【ここまでの本文】
{existing}

【続きの要件】
- 続きの本文だけを出力し、章見出しは付けないこと
- 物語上の出来事と感情の決着まで描くこと
- 最後は完結した文で終え、未完のまま止めないこと"""

        return f"""以下の情報に基づいて、第{stage.stage}章「{stage.name}」を執筆してください。

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
- 最後は完結した文で終えること

出力形式:
# 第{stage.stage}章: [文学的なタイトル]

[本文]"""

    def generate_title(
        self,
        characters: CharacterSet,
        plot: Plot,
        client: Optional[Any] = None,
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

        use_client = client or self.client
        result = use_client.chat_json(
            prompt=prompt,
            temperature=0.8
        )

        titles_data = result.get("titles", [])

        if isinstance(titles_data, str):
            titles_data = [titles_data]
        if not isinstance(titles_data, list):
            raise ValueError("titles must be a list")
        if len(titles_data) == 0:
            raise ValueError("No titles returned")

        titles = []
        for item in titles_data[:3]:
            if isinstance(item, Mapping):
                title = item.get("title", "")
            else:
                title = str(item)
            title = title.strip()
            if title:
                titles.append(title)

        if not titles:
            raise ValueError("No usable titles returned")
        return titles
