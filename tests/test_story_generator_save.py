"""save_run() のテスト"""

import re
import pytest
from pathlib import Path

from src.narrative_analyzer import NarrativeAnalysis
from src.character_generator import Character, CharacterSet
from src.plot_generator import PlotStage, Plot
from src.story_generator import Story, StoryGenerator


def _make_story() -> Story:
    """テスト用 Story を生成"""
    analysis = NarrativeAnalysis(
        desire="願望",
        suppression="抑圧",
        conflict="葛藤",
        elements=("要素1", "要素2"),
    )
    protagonist = Character(role="protagonist", name="主人公", profile="主人公プロフィール")
    messenger = Character(role="messenger", name="使者", profile="使者プロフィール")
    supporter = Character(role="supporter", name="援助者", profile="援助者プロフィール")
    adversary = Character(role="adversary", name="敵対者", profile="敵対者プロフィール")
    characters = CharacterSet(
        protagonist=protagonist,
        messenger=messenger,
        supporter=supporter,
        adversary=adversary,
    )
    stages = (
        PlotStage(stage=1, name="日常世界", act="第一幕", description="平穏な日常"),
    )
    plot = Plot(stages=stages, outline="アウトライン")
    return Story(
        title="テスト物語",
        chapters=("第一章本文",),
        characters=characters,
        plot=plot,
        narrative_analysis=analysis,
    )


class TestSaveRun:
    def test_creates_timestamped_run_dir(self, tmp_path):
        story = _make_story()
        generator = StoryGenerator.__new__(StoryGenerator)
        run_dir = generator.save_run(story, base_dir=str(tmp_path))

        assert run_dir.exists()
        assert run_dir.is_dir()
        # ディレクトリ名が run_YYYYMMDD_HHMMSS 形式であること
        assert re.match(r"run_\d{8}_\d{6}$", run_dir.name)

    def test_story_file_is_saved_in_run_dir(self, tmp_path):
        story = _make_story()
        generator = StoryGenerator.__new__(StoryGenerator)
        run_dir = generator.save_run(story, base_dir=str(tmp_path))

        # 物語ファイルが run_dir 内に存在すること
        files = list(run_dir.iterdir())
        assert any("テスト物語" in f.name or "story" in f.name.lower() for f in files)

    def test_analysis_file_is_saved_in_run_dir(self, tmp_path):
        story = _make_story()
        generator = StoryGenerator.__new__(StoryGenerator)
        run_dir = generator.save_run(story, base_dir=str(tmp_path))

        analysis_file = run_dir / "narrative_analysis.md"
        assert analysis_file.exists()

    def test_separate_run_dirs_for_each_call(self, tmp_path):
        import time

        story = _make_story()
        generator = StoryGenerator.__new__(StoryGenerator)

        run_dir1 = generator.save_run(story, base_dir=str(tmp_path))
        time.sleep(1)  # タイムスタンプが異なるよう1秒待機
        run_dir2 = generator.save_run(story, base_dir=str(tmp_path))

        # 異なるディレクトリに保存されること
        assert run_dir1 != run_dir2
        assert run_dir1.exists()
        assert run_dir2.exists()

    def test_invalid_story_raises_value_error(self, tmp_path):
        generator = StoryGenerator.__new__(StoryGenerator)
        with pytest.raises(ValueError, match="story must be Story instance"):
            generator.save_run("not a story", base_dir=str(tmp_path))

    def test_default_base_dir_is_output(self, tmp_path, monkeypatch):
        """base_dir のデフォルトが "output" であること（呼び出し時に引数指定しない場合）"""
        story = _make_story()
        generator = StoryGenerator.__new__(StoryGenerator)
        # tmp_path を作業ディレクトリとして変更することで output/ が tmp_path 配下に作られる
        monkeypatch.chdir(tmp_path)
        run_dir = generator.save_run(story)
        assert run_dir.resolve().parent == (tmp_path / "output").resolve()
