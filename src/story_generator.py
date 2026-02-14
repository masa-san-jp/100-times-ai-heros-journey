"""
物語生成オーケストレーター

全体のフローを制御するメインクラス
"""

from typing import List, Optional
from dataclasses import dataclass
from pathlib import Path

from .ollama_client import OllamaClient, OllamaConfig
from .narrative_analyzer import NarrativeAnalyzer, NarrativeInput, NarrativeAnalysis
from .character_generator import CharacterGenerator, CharacterSet
from .plot_generator import PlotGenerator, Plot, PlotStage


@dataclass(frozen=True)
class Story:
    """完成した物語（イミュータブル）"""
    title: str
    chapters: List[str]  # 各章の本文
    characters: CharacterSet
    plot: Plot
    narrative_analysis: NarrativeAnalysis


class StoryGenerator:
    """物語生成オーケストレーター"""

    def __init__(
        self,
        ollama_config: Optional[OllamaConfig] = None
    ):
        """
        Args:
            ollama_config: Ollama設定（省略時はデフォルト）
        """
        self.client = OllamaClient(ollama_config)
        self.narrative_analyzer = NarrativeAnalyzer(self.client)
        self.character_generator = CharacterGenerator(self.client)
        self.plot_generator = PlotGenerator(self.client)

    def generate(
        self,
        narrative: NarrativeInput,
        plot_type: str = "旅 (Quest)"
    ) -> Story:
        """
        物語を生成

        Args:
            narrative: ナラティブ入力データ
            plot_type: 物語の構造タイプ

        Returns:
            完成した物語

        Raises:
            ValueError: 入力が不正な場合
            OllamaClientError: API呼び出しに失敗した場合
        """
        if not isinstance(narrative, NarrativeInput):
            raise ValueError("narrative must be NarrativeInput instance")

        if not plot_type:
            raise ValueError("plot_type must be provided")

        # ステップ1: ナラティブ分析
        narrative_analysis = self.narrative_analyzer.analyze(narrative)

        # ステップ2: キャラクター生成
        characters = self.character_generator.generate(
            narrative_elements=narrative_analysis.elements,
            plot_type=plot_type
        )

        # ステップ3: プロット生成
        plot = self.plot_generator.generate(characters)

        # ステップ4: 各章を執筆
        chapters = self._write_chapters(plot, characters)

        # ステップ5: タイトル生成
        title_candidates = self.plot_generator.generate_title(characters, plot)
        title = title_candidates[0] if title_candidates else "無題"

        return Story(
            title=title,
            chapters=chapters,
            characters=characters,
            plot=plot,
            narrative_analysis=narrative_analysis
        )

    def _write_chapters(
        self,
        plot: Plot,
        characters: CharacterSet
    ) -> List[str]:
        """
        全章を執筆

        Args:
            plot: プロット
            characters: キャラクターセット

        Returns:
            各章の本文リスト
        """
        chapters = []
        previous_summaries = []

        for stage in plot.stages:
            # 章を執筆
            chapter = self.plot_generator.generate_chapter(
                stage=stage,
                characters=characters,
                previous_chapters=previous_summaries
            )

            chapters.append(chapter)

            # 次章のための要約を追加
            summary = f"第{stage.stage}章: {stage.description}"
            previous_summaries.append(summary)

        return chapters

    def save_story(self, story: Story, output_dir: str = "output/stories") -> Path:
        """
        物語をファイルに保存

        Args:
            story: 物語
            output_dir: 出力ディレクトリ

        Returns:
            保存したファイルのパス

        Raises:
            IOError: ファイル保存に失敗した場合
        """
        if not isinstance(story, Story):
            raise ValueError("story must be Story instance")

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # ファイル名を生成（タイトルから）
        safe_title = "".join(c for c in story.title if c.isalnum() or c in (" ", "_", "-"))
        safe_title = safe_title[:50]  # 最大50文字
        filename = f"{safe_title}.md"
        file_path = output_path / filename

        # Markdown形式で保存
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                # タイトル
                f.write(f"# {story.title}\n\n")

                # 登場人物
                f.write("## 登場人物\n\n")
                f.write(f"### {story.characters.protagonist.name}（主人公）\n")
                f.write(f"{story.characters.protagonist.profile}\n\n")
                f.write(f"### {story.characters.messenger.name}（使者）\n")
                f.write(f"{story.characters.messenger.profile}\n\n")
                f.write(f"### {story.characters.supporter.name}（援助者）\n")
                f.write(f"{story.characters.supporter.profile}\n\n")
                f.write(f"### {story.characters.adversary.name}（敵対者）\n")
                f.write(f"{story.characters.adversary.profile}\n\n")

                # 各章
                f.write("---\n\n")
                for chapter in story.chapters:
                    f.write(f"{chapter}\n\n")

                # メタ情報
                f.write("---\n\n")
                f.write("## メタ情報\n\n")
                f.write(f"- 総章数: {len(story.chapters)}章\n")
                f.write(f"- 総文字数: {sum(len(c) for c in story.chapters)}文字\n")

            return file_path

        except Exception as e:
            raise IOError(f"Failed to save story: {e}")

    def save_analysis(
        self,
        narrative_analysis: NarrativeAnalysis,
        output_dir: str = "output/analysis"
    ) -> Path:
        """
        ナラティブ分析結果を保存

        Args:
            narrative_analysis: 分析結果
            output_dir: 出力ディレクトリ

        Returns:
            保存したファイルのパス

        Raises:
            IOError: ファイル保存に失敗した場合
        """
        if not isinstance(narrative_analysis, NarrativeAnalysis):
            raise ValueError("narrative_analysis must be NarrativeAnalysis instance")

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        file_path = output_path / "narrative_analysis.md"

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("# ナラティブ分析結果\n\n")

                f.write("## 願望分析\n\n")
                f.write(f"{narrative_analysis.desire}\n\n")

                f.write("## 抑圧分析\n\n")
                f.write(f"{narrative_analysis.suppression}\n\n")

                f.write("## 葛藤分析\n\n")
                f.write(f"{narrative_analysis.conflict}\n\n")

                f.write("## ナラティブ要素\n\n")
                for i, element in enumerate(narrative_analysis.elements, 1):
                    f.write(f"{i}. {element}\n")

            return file_path

        except Exception as e:
            raise IOError(f"Failed to save analysis: {e}")
