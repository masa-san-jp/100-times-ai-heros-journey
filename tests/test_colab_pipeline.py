"""Colab版相当パイプラインのユニットテスト。"""

import pytest

from src.colab_features import (
    ElementPoolGenerator,
    PlotSkeletonGenerator,
    PlotTypeClassifier,
    VisualPromptGenerator,
    WorldGenerator,
    WorldSetting,
)
from src.colab_pipeline import ColabParityPipeline, PipelineConfig
from src.narrative_analyzer import NarrativeAnalysis, NarrativeInput
from src.character_generator import Character, CharacterSet
from src.plot_generator import PlotGenerator, Plot, PlotStage, TextGenerationResult
from src.plot_generator import JOURNEY_STAGES_12
from src.story_generator import ChapterGenerationError, StoryGenerator
from src.ollama_client import OllamaClient
from run_pipeline import choose_installed_model


class FakeClient:
    """LLMを呼ばずに各生成器の入出力契約を検証するクライアント。"""

    def __init__(self):
        self.chat_calls = []
        self.json_calls = []
        self.candidate = 0

    def chat(self, prompt, system="", temperature=0.7, model=None):
        self.chat_calls.append(prompt)
        if "主人公のキャラクタープロフィール" in prompt:
            self.candidate += 1
            return f"名前: 主人公{self.candidate}\n\n勇敢な主人公。"
        if "使者" in prompt and "主人公に対して" in prompt:
            return f"名前: 使者{self.candidate}\n\n知恵を授ける使者。"
        if "援助者" in prompt and "主人公をサポート" in prompt:
            return f"名前: 援助者{self.candidate}\n\n仲間を支える援助者。"
        if "敵対者" in prompt and "克服すべき" in prompt:
            return f"名前: 敵対者{self.candidate}\n\n主人公を試す敵対者。"
        return f"生成されたテキスト{self.candidate}"

    def chat_json(self, prompt, system="", temperature=0.3, model=None):
        self.json_calls.append(prompt)
        if '"wants"' in prompt:
            return {"wants": ["願望1", "願望2", "願望3"]}
        if '"abilities"' in prompt:
            return {"abilities": ["能力1", "能力2", "能力3"]}
        if '"roles"' in prompt:
            return {"roles": ["課題1", "課題2", "課題3"]}
        if '"plot_list"' in prompt:
            return {"plot_list": [{"name": "旅", "core_structure": "旅の構造"}]}
        if '"stages"' in prompt:
            return {
                "stages": [
                    {"stage": i, "name": f"段階{i}", "description": "展開"}
                    for i in range(1, 12)
                ]
            }
        if '"titles"' in prompt:
            return {"titles": [{"title": "試験作品", "reason": "理由"}]}
        if '"narrative"' in prompt:
            return {"narrative": [f"要素{i}" for i in range(1, 11)]}
        return {}


def _narrative():
    return NarrativeInput(*(["テスト入力"] * 13))


def _analysis():
    return NarrativeAnalysis(
        desire="願望",
        suppression="抑圧",
        conflict="葛藤",
        elements=("要素1", "要素2", "要素3"),
    )


def _characters():
    return CharacterSet(
        protagonist=Character("protagonist", "主人公", "主人公のプロフィール"),
        messenger=Character("messenger", "使者", "使者のプロフィール"),
        supporter=Character("supporter", "援助者", "援助者のプロフィール"),
        adversary=Character("adversary", "敵対者", "敵対者のプロフィール"),
    )


def test_feature_generators_return_colab_artifacts():
    client = FakeClient()
    narrative = _narrative()
    analysis = _analysis()

    pools = ElementPoolGenerator(client).generate(narrative, analysis, count=3)
    plot_types = PlotTypeClassifier(client).generate(narrative, analysis)
    world = WorldGenerator(client).generate(narrative, analysis)
    skeleton = PlotSkeletonGenerator(client).generate(
        _characters(), world, plot_types[0]
    )
    visuals = VisualPromptGenerator(client).generate(_characters())

    assert len(pools.wants) == 3
    assert plot_types[0].name == "旅"
    assert world.text
    assert skeleton.part_a
    assert visuals.adversary


def test_ollama_plot_skeleton_uses_one_bounded_json_call():
    class SkeletonClient(OllamaClient):
        def __init__(self):
            self.calls = []

        def chat_json(self, prompt, system="", temperature=0.3, model=None, num_predict=None):
            self.calls.append((prompt, num_predict))
            return {part: f"{part}パート" for part in "ABCDE"}

        def chat(self, *args, **kwargs):
            raise AssertionError("skeleton generation should be batched")

    client = SkeletonClient()
    skeleton = PlotSkeletonGenerator(client).generate(
        _characters(),
        WorldSetting("短い世界設定"),
        "旅",
    )

    assert skeleton.part_a == "Aパート"
    assert len(client.calls) == 1
    assert client.calls[0][1] == 2048


def test_ollama_visual_prompts_use_one_bounded_json_call():
    class VisualClient(OllamaClient):
        def __init__(self):
            self.calls = []

        def chat_json(self, prompt, system="", temperature=0.3, model=None, num_predict=None):
            self.calls.append((prompt, num_predict))
            return {role: f"{role} visual prompt" for role in (
                "protagonist", "messenger", "supporter", "adversary"
            )}

        def chat(self, *args, **kwargs):
            raise AssertionError("visual prompt generation should be batched")

    client = VisualClient()
    prompts = VisualPromptGenerator(client).generate(_characters())

    assert prompts.protagonist == "protagonist visual prompt"
    assert len(client.calls) == 1
    assert client.calls[0][1] == 4096


def test_pipeline_generates_multiple_variations_and_shared_artifacts(tmp_path):
    client = FakeClient()
    pipeline = ColabParityPipeline(client=client)
    batch = pipeline.run(
        _narrative(),
        PipelineConfig(
            pool_size=3,
            variation_count=2,
            write_chapters=False,
            generate_world=False,
            generate_skeleton=False,
            generate_visual_prompts=False,
            output_dir=str(tmp_path),
            random_seed=42,
            deduplicate=False,
        ),
    )

    assert len(batch.stories) == 2
    assert all(not story.chapters for story in batch.stories)
    assert batch.output_dir is not None
    assert (batch.output_dir / "element_pools.json").exists()
    assert (batch.output_dir / "plot_types.json").exists()
    assert (batch.output_dir / "batch_manifest.json").exists()
    assert (batch.output_dir / "run_001" / "metadata.json").exists()
    assert (batch.output_dir / "run_002" / "metadata.json").exists()


def test_pipeline_resumes_and_discards_duplicate(tmp_path):
    first = ColabParityPipeline(client=FakeClient()).run(
        _narrative(),
        PipelineConfig(
            pool_size=3,
            variation_count=1,
            write_chapters=False,
            generate_world=False,
            generate_skeleton=False,
            generate_visual_prompts=False,
            output_dir=str(tmp_path),
            batch_id="resume-test",
            random_seed=42,
        ),
    )

    resumed = ColabParityPipeline(client=FakeClient()).run(
        _narrative(),
        PipelineConfig(
            pool_size=3,
            variation_count=2,
            write_chapters=False,
            generate_world=False,
            generate_skeleton=False,
            generate_visual_prompts=False,
            resume_dir=str(first.output_dir),
            random_seed=42,
            max_attempts=3,
        ),
    )

    assert resumed.resumed is True
    assert resumed.completed_count == 2
    assert resumed.duplicate_count == 1
    assert resumed.attempts == 2
    assert (first.output_dir / "run_002" / "metadata.json").exists()


def test_choose_installed_model_prefers_default_in_non_interactive_mode():
    assert choose_installed_model(
        ["llama3:8b", "gpt-oss:20b"],
        interactive=False,
    ) == "gpt-oss:20b"


def test_choose_installed_model_falls_back_to_first_model():
    assert choose_installed_model(
        ["z-model:latest", "a-model:latest"],
        interactive=False,
    ) == "a-model:latest"


def test_choose_installed_model_accepts_interactive_number():
    answers = iter(["2"])
    assert choose_installed_model(
        ["first:latest", "second:latest"],
        interactive=True,
        input_fn=lambda _prompt: next(answers),
    ) == "second:latest"


def test_plot_title_parser_accepts_string_items():
    class TitleClient:
        def chat_json(self, prompt, system="", temperature=0.3, model=None):
            return {"titles": ["文字列タイトル"]}

    plot = Plot(
        stages=(PlotStage(1, "日常世界", "第一幕", "展開"),),
        outline="アウトライン",
    )
    titles = PlotGenerator(TitleClient()).generate_title(_characters(), plot)

    assert titles == ["文字列タイトル"]


def test_default_pipeline_matches_colab_twelve_stage_ten_chapter_shape():
    config = PipelineConfig()

    assert config.journey_stage_count == 12
    assert config.chapter_count == 10


def test_direct_story_generator_defaults_to_colab_shape():
    generator = StoryGenerator(client=FakeClient())
    story = generator.generate(_narrative())

    assert len(story.plot.stages) == 12
    assert len(story.chapters) == 10


def test_twelve_stages_are_preserved_when_written_as_ten_chapters():
    stages = tuple(
        PlotStage(
            stage=item["stage"],
            name=item["name"],
            act=item["act"],
            description=f"展開{item['stage']}",
        )
        for item in JOURNEY_STAGES_12
    )
    plot = Plot(stages=stages, outline="アウトライン")

    class ChapterRecorder:
        def __init__(self):
            self.stages = []

        def generate_chapter(self, stage, characters, previous_chapters, client=None):
            self.stages.append(stage)
            return f"第{stage.stage}章"

    recorder = ChapterRecorder()
    generator = StoryGenerator.__new__(StoryGenerator)
    generator.plot_generator = recorder
    generator.writing_client = None

    chapters = generator._write_chapters(plot, _characters(), chapter_count=10)

    assert len(chapters) == 10
    assert recorder.stages[6].name == "最も危険な場所への接近／最大の試練"
    assert recorder.stages[8].name == "帰路／復活"
    assert recorder.stages[9].name == "宝を持ち帰る"
    assert recorder.stages[9].description == "展開12"


def test_truncated_chapter_is_continued_until_stop():
    class ContinuationPlotGenerator:
        def __init__(self):
            self.calls = []

        def generate_chapter_result(self, **kwargs):
            self.calls.append(kwargs.get("continuation_text"))
            if kwargs.get("continuation_text") is None:
                return TextGenerationResult("ここまで", "length")
            return TextGenerationResult("ここで完結します。", "stop")

    generator = StoryGenerator.__new__(StoryGenerator)
    generator.plot_generator = ContinuationPlotGenerator()
    generator.writing_client = None
    plot = Plot(
        stages=(PlotStage(1, "日常世界", "第一幕", "展開"),),
        outline="アウトライン",
    )

    chapters = generator._write_chapters(
        plot,
        _characters(),
        chapter_count=1,
        max_chapter_continuations=1,
    )

    assert chapters == ["ここまで\n\nここで完結します。"]
    assert len(generator.plot_generator.calls) == 2


def test_truncated_chapter_fails_after_continuation_limit():
    class AlwaysTruncatedPlotGenerator:
        def generate_chapter_result(self, **kwargs):
            return TextGenerationResult("まだ途中", "length")

    generator = StoryGenerator.__new__(StoryGenerator)
    generator.plot_generator = AlwaysTruncatedPlotGenerator()
    generator.writing_client = None
    plot = Plot(
        stages=(PlotStage(1, "日常世界", "第一幕", "展開"),),
        outline="アウトライン",
    )

    with pytest.raises(ChapterGenerationError, match="第1章を完結できませんでした"):
        generator._write_chapters(
            plot,
            _characters(),
            chapter_count=1,
            max_chapter_continuations=1,
        )


def test_chapter_checkpoints_are_reused(tmp_path):
    class Recorder:
        def __init__(self):
            self.calls = 0

        def generate_chapter(self, stage, characters, previous_chapters, client=None):
            self.calls += 1
            return f"第{stage.stage}章は完結。"

    plot = Plot(
        stages=(
            PlotStage(1, "日常世界", "第一幕", "展開1"),
            PlotStage(2, "冒険への呼びかけ", "第一幕", "展開2"),
        ),
        outline="アウトライン",
    )
    checkpoint_dir = tmp_path / "run_001"

    first = StoryGenerator.__new__(StoryGenerator)
    first.plot_generator = Recorder()
    first.writing_client = None
    first_chapters = first._write_chapters(
        plot,
        _characters(),
        chapter_count=2,
        checkpoint_dir=checkpoint_dir,
    )

    second = StoryGenerator.__new__(StoryGenerator)
    second.plot_generator = Recorder()
    second.writing_client = None
    second_chapters = second._write_chapters(
        plot,
        _characters(),
        chapter_count=2,
        checkpoint_dir=checkpoint_dir,
    )

    assert first_chapters == second_chapters
    assert first.plot_generator.calls == 2
    assert second.plot_generator.calls == 0
    assert (checkpoint_dir / "chapter_01.md").exists()
    assert (checkpoint_dir / "chapter_progress.json").exists()


def test_draft_checkpoint_round_trips_story_materials(tmp_path):
    plot = Plot(
        stages=(PlotStage(1, "日常世界", "第一幕", "展開1"),),
        outline="アウトライン",
    )
    checkpoint_dir = tmp_path / "run_001"

    StoryGenerator.save_draft_checkpoint(
        checkpoint_dir=checkpoint_dir,
        characters=_characters(),
        plot=plot,
        world=None,
        plot_skeleton=None,
        plot_type="旅 (Quest)",
        selected_elements={"want": "つながり"},
    )
    draft = StoryGenerator.load_draft_checkpoint(checkpoint_dir)

    assert draft is not None
    assert draft["characters"].protagonist.name == "主人公"
    assert draft["plot"].stages[0].description == "展開1"
    assert draft["selected_elements"] == {"want": "つながり"}


NEW_STRUCTURES = ("kishotenketsu-4", "story-circle-8", "save-the-cat-15")


@pytest.mark.parametrize(
    "structure_name",
    NEW_STRUCTURES + ("journey-12", "journey-11"),
)
def test_plot_generator_returns_stage_count_of_each_structure(structure_name):
    from src.plot_generator import get_story_structure

    structure = get_story_structure(structure_name)
    client = FakeClient()
    plot = PlotGenerator(client).generate(
        _characters(),
        stage_definitions=structure.stages,
        structure_label=structure.label,
    )

    assert len(plot.stages) == structure.stage_count
    assert [stage.stage for stage in plot.stages] == [
        s["stage"] for s in structure.stages
    ]
    assert [stage.act for stage in plot.stages] == [s["act"] for s in structure.stages]
    assert f"{structure.label}{structure.stage_count}段階" in client.json_calls[0]
    assert structure.stages[-1]["name"] in client.chat_calls[-1]


def test_new_structures_have_documented_stage_names():
    from src.plot_generator import get_story_structure

    assert [s["name"] for s in get_story_structure("story-circle-8").stages] == [
        "You", "Need", "Go", "Search", "Find", "Take", "Return", "Change",
    ]
    assert [s["name"] for s in get_story_structure("save-the-cat-15").stages] == [
        "Opening Image", "Theme Stated", "Set-Up", "Catalyst", "Debate",
        "Break into Two", "B Story", "Fun and Games", "Midpoint",
        "Bad Guys Close In", "All Is Lost", "Dark Night of the Soul",
        "Break into Three", "Finale", "Final Image",
    ]
    assert [s["name"] for s in get_story_structure("kishotenketsu-4").stages] == [
        "起", "承", "転", "結",
    ]
    with pytest.raises(ValueError, match="unknown structure"):
        get_story_structure("propp-99")


def test_structure_config_validation():
    assert PipelineConfig().structure_name == "journey-12"
    assert PipelineConfig(journey_stage_count=11).structure_name == "journey-11"
    assert PipelineConfig(structure="story-circle-8").story_structure.stage_count == 8
    with pytest.raises(ValueError, match="structure must be one of"):
        PipelineConfig(structure="unknown").validate()
    with pytest.raises(ValueError, match="cannot be used together"):
        PipelineConfig(structure="kishotenketsu-4", journey_stage_count=11).validate()


def _structure_config(tmp_path, **kwargs):
    values = dict(
        pool_size=3,
        variation_count=1,
        write_chapters=False,
        generate_world=False,
        generate_skeleton=False,
        generate_visual_prompts=False,
        output_dir=str(tmp_path),
        random_seed=42,
    )
    values.update(kwargs)
    return PipelineConfig(**values)


def test_pipeline_saves_structure_and_resume_reuses_it(tmp_path):
    import json

    first = ColabParityPipeline(client=FakeClient()).run(
        _narrative(),
        _structure_config(tmp_path, structure="save-the-cat-15", batch_id="structure"),
    )
    manifest = json.loads(
        (first.output_dir / "batch_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["structure"] == "save-the-cat-15"
    assert manifest["journey_stage_count"] == 15
    assert len(first.stories[0].plot.stages) == 15
    metadata = json.loads(
        (first.output_dir / "run_001" / "metadata.json").read_text(encoding="utf-8")
    )
    assert metadata["structure"] == "save-the-cat-15"
    assert metadata["stage_count"] == 15

    resumed = ColabParityPipeline(client=FakeClient()).run(
        _narrative(),
        _structure_config(
            tmp_path,
            output_dir="output",
            variation_count=2,
            resume_dir=str(first.output_dir),
            deduplicate=False,
        ),
    )
    assert [len(story.plot.stages) for story in resumed.stories] == [15]

    with pytest.raises(ValueError, match="does not match"):
        ColabParityPipeline(client=FakeClient()).run(
            _narrative(),
            _structure_config(
                tmp_path,
                output_dir="output",
                variation_count=3,
                structure="kishotenketsu-4",
                resume_dir=str(first.output_dir),
            ),
        )


def test_cli_rejects_structure_with_journey_stages(monkeypatch, capsys):
    import run_pipeline

    monkeypatch.setattr(
        "sys.argv",
        ["run_pipeline.py", "--structure", "kishotenketsu-4", "--journey-stages", "11"],
    )
    with pytest.raises(SystemExit):
        run_pipeline.main()
    assert "同時に指定できません" in capsys.readouterr().err


def test_plot_stage_names_follow_structure_even_if_llm_renames_them():
    from src.plot_generator import get_story_structure

    class RenamingClient(FakeClient):
        def chat_json(self, prompt, system="", temperature=0.3, model=None):
            self.json_calls.append(prompt)
            return {
                "stages": [
                    {"stage": 10 + i, "name": f"言い換え{i}", "description": f"展開{i}"}
                    for i in range(1, 4)
                ]
            }

    structure = get_story_structure("story-circle-8")
    plot = PlotGenerator(RenamingClient()).generate(
        _characters(),
        stage_definitions=structure.stages,
        structure_label=structure.label,
    )

    assert [stage.name for stage in plot.stages] == [s["name"] for s in structure.stages]
    assert [stage.stage for stage in plot.stages] == list(range(1, 9))
    assert [stage.description for stage in plot.stages[:3]] == ["展開1", "展開2", "展開3"]
    assert plot.stages[3].description == "Searchの展開"


class SkeletonRecorder:
    """骨子生成のプロンプトを記録する（Ollama以外の経路: A〜Eを1回ずつ呼ぶ）。"""

    def __init__(self):
        self.prompts = []

    def chat(self, prompt, system="", temperature=0.7, model=None):
        self.prompts.append(prompt)
        return "骨子"


@pytest.mark.parametrize("structure_name", NEW_STRUCTURES)
def test_skeleton_prompts_follow_chosen_structure(structure_name):
    from src.plot_generator import get_story_structure

    structure = get_story_structure(structure_name)
    recorder = SkeletonRecorder()
    PlotSkeletonGenerator(recorder).generate(
        _characters(), WorldSetting(text="世界"), "旅", structure=structure
    )

    assert len(recorder.prompts) == 5
    by_number = {s["stage"]: s["name"] for s in structure.stages}
    covered = set()
    for part, prompt in zip("ABCDE", recorder.prompts):
        for number in structure.skeleton_parts[part]:
            assert f"{number}. {by_number[number]}" in prompt
            covered.add(number)
        for journey_requirement in PlotSkeletonGenerator.PART_PROMPTS.values():
            assert journey_requirement not in prompt
    # どの段も、いずれかの部に割り当てられている
    assert covered == set(by_number)


def test_skeleton_prompts_for_ollama_include_structure_stages():
    from src.plot_generator import get_story_structure

    class OllamaSkeletonClient(OllamaClient):
        def __init__(self):
            self.calls = []

        def chat_json(self, prompt, system="", temperature=0.3, model=None, num_predict=None):
            self.calls.append(prompt)
            return {part: f"{part}パート" for part in "ABCDE"}

    structure = get_story_structure("kishotenketsu-4")
    client = OllamaSkeletonClient()
    skeleton = PlotSkeletonGenerator(client).generate(
        _characters(), WorldSetting(text="世界"), "旅", structure=structure
    )

    assert skeleton.part_e == "Eパート"
    assert "C: 山場。起承転結の次の段に当たる出来事: 3. 転" in client.calls[0]
    assert "4. 結" in client.calls[0]


@pytest.mark.parametrize("structure_name", ("journey-12", "journey-11"))
def test_journey_skeleton_prompts_are_unchanged(structure_name):
    from src.plot_generator import get_story_structure

    without = SkeletonRecorder()
    PlotSkeletonGenerator(without).generate(_characters(), WorldSetting(text="世界"), "旅")
    with_structure = SkeletonRecorder()
    PlotSkeletonGenerator(with_structure).generate(
        _characters(),
        WorldSetting(text="世界"),
        "旅",
        structure=get_story_structure(structure_name),
    )

    assert with_structure.prompts == without.prompts
    assert PlotSkeletonGenerator.PART_PROMPTS["A"] in without.prompts[0]


def test_pipeline_passes_structure_to_skeleton(tmp_path):
    client = FakeClient()
    ColabParityPipeline(client=client).run(
        _narrative(),
        _structure_config(
            tmp_path, structure="story-circle-8", generate_skeleton=True
        ),
    )

    skeleton_prompts = [p for p in client.chat_calls if "物語プロットの" in p]
    assert len(skeleton_prompts) == 5
    assert "1. You" in skeleton_prompts[0]


# 感情曲線の指定（#61、出典は Reagan ほか 2016 の6つの基本形）

ARC_DIRECTIONS = {
    "rags-to-riches": ("上昇",),
    "tragedy": ("下降",),
    "man-in-a-hole": ("下降", "上昇"),
    "icarus": ("上昇", "下降"),
    "cinderella": ("上昇", "下降", "上昇"),
    "oedipus": ("下降", "上昇", "下降"),
}


def test_emotional_arcs_match_the_six_shapes_of_the_source():
    from src.plot_generator import EMOTIONAL_ARCS

    assert {name: arc.directions for name, arc in EMOTIONAL_ARCS.items()} == ARC_DIRECTIONS


@pytest.mark.parametrize("arc_name", tuple(ARC_DIRECTIONS))
@pytest.mark.parametrize("stage_count", (4, 8, 11, 12, 15))
def test_emotion_directions_split_stages_evenly_in_order(arc_name, stage_count):
    from src.plot_generator import emotion_directions, get_emotional_arc

    arc = get_emotional_arc(arc_name)
    directions = emotion_directions(arc, stage_count)
    assert len(directions) == stage_count
    # 区間の向きが、形の並びどおりに前から現れる
    runs = [directions[0]]
    for direction in directions[1:]:
        if direction != runs[-1]:
            runs.append(direction)
    assert tuple(runs) == ARC_DIRECTIONS[arc_name]
    # 各区間の段数の差は1以内（等分）
    sizes = []
    for direction in directions:
        if sizes and sizes[-1][0] == direction:
            sizes[-1][1] += 1
        else:
            sizes.append([direction, 1])
    counts = [count for _, count in sizes]
    assert max(counts) - min(counts) <= 1


def test_emotion_directions_for_12_stage_man_in_a_hole():
    from src.plot_generator import emotion_directions, get_emotional_arc

    assert emotion_directions(get_emotional_arc("man-in-a-hole"), 12) == (
        ("下降",) * 6 + ("上昇",) * 6
    )


def test_unknown_emotional_arc_is_rejected():
    from src.plot_generator import get_emotional_arc

    with pytest.raises(ValueError, match="unknown emotional arc"):
        get_emotional_arc("vonnegut")
    with pytest.raises(ValueError, match="emotional_arc"):
        PipelineConfig(emotional_arc="vonnegut").validate()


def test_plot_prompts_include_stage_emotions_and_keep_plot_format():
    from src.plot_generator import apply_emotional_arc, get_emotional_arc

    definitions = apply_emotional_arc(JOURNEY_STAGES_12, get_emotional_arc("man-in-a-hole"))
    client = FakeClient()
    plot = PlotGenerator(client).generate(_characters(), stage_definitions=definitions)

    structure_prompt = client.json_calls[-1]
    outline_prompt = client.chat_calls[-1]
    for prompt in (structure_prompt, outline_prompt):
        assert "1. 日常世界 (第一幕) ［感情: 下降］" in prompt
        assert "12. 宝を持ち帰る (第三幕) ［感情: 上昇］" in prompt
        assert "各段の［感情］に従うこと" in prompt
    # プロット本文の「N. 名前 (第X幕)」の形式は変わらない（#38）
    assert "\n1. 日常世界 (第一幕)\n" in plot.to_text()
    assert "感情" not in plot.to_text()


def test_plot_prompts_without_emotional_arc_are_unchanged():
    from src.plot_generator import apply_emotional_arc

    with_none = FakeClient()
    PlotGenerator(with_none).generate(
        _characters(), stage_definitions=apply_emotional_arc(JOURNEY_STAGES_12, None)
    )
    default = FakeClient()
    PlotGenerator(default).generate(_characters())
    assert with_none.json_calls == default.json_calls
    assert with_none.chat_calls == default.chat_calls
    assert "感情" not in default.json_calls[-1]
    assert "感情" not in default.chat_calls[-1]


def test_pipeline_saves_emotional_arc_and_resume_reuses_it(tmp_path):
    import json

    client = FakeClient()
    first = ColabParityPipeline(client=client).run(
        _narrative(),
        _structure_config(
            tmp_path, structure="kishotenketsu-4", emotional_arc="icarus", batch_id="arc"
        ),
    )
    manifest = json.loads(
        (first.output_dir / "batch_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["emotional_arc"] == "icarus"
    structure_prompts = [p for p in client.json_calls if '"stages"' in p]
    assert "1. 起 (第一幕): " in structure_prompts[0]
    assert "［感情: 上昇］" in structure_prompts[0]
    assert "4. 結 (第三幕): " in structure_prompts[0]
    assert structure_prompts[0].rstrip().count("［感情: 下降］") == 2

    resumed_client = FakeClient()
    ColabParityPipeline(client=resumed_client).run(
        _narrative(),
        _structure_config(
            tmp_path,
            output_dir="output",
            variation_count=2,
            resume_dir=str(first.output_dir),
            deduplicate=False,
        ),
    )
    resumed_prompts = [p for p in resumed_client.json_calls if '"stages"' in p]
    assert resumed_prompts and "［感情: 上昇］" in resumed_prompts[0]

    with pytest.raises(ValueError, match="does not match"):
        ColabParityPipeline(client=FakeClient()).run(
            _narrative(),
            _structure_config(
                tmp_path,
                output_dir="output",
                variation_count=3,
                emotional_arc="tragedy",
                resume_dir=str(first.output_dir),
            ),
        )


def _run_metadata(batch):
    import json

    return [
        json.loads((path / "metadata.json").read_text(encoding="utf-8"))
        for path in sorted(batch.output_dir.glob("run_*"))
    ]


def test_pipeline_chooses_emotional_arc_per_work_without_option(tmp_path):
    import json

    client = FakeClient()
    batch = ColabParityPipeline(client=client).run(
        _narrative(),
        _structure_config(tmp_path, variation_count=6, batch_id="auto", deduplicate=False),
    )
    manifest = json.loads(
        (batch.output_dir / "batch_manifest.json").read_text(encoding="utf-8")
    )
    # 固定指定なし（null）＝作品ごとに自動で選ぶ
    assert manifest["emotional_arc"] is None
    arcs = [meta["selected_elements"]["emotional_arc"] for meta in _run_metadata(batch)]
    assert len(arcs) == 6
    assert set(arcs) <= set(ARC_DIRECTIONS)
    # 各作品のプロット生成プロンプトに、その作品の形の上下が入る
    structure_prompts = [p for p in client.json_calls if '"stages"' in p]
    assert len(structure_prompts) == 6
    for prompt, arc in zip(structure_prompts, arcs):
        first = ARC_DIRECTIONS[arc][0]
        assert f"1. 日常世界 (第一幕) ［感情: {first}］" in prompt


def test_auto_emotional_arc_is_reproducible_and_keeps_element_choices(tmp_path):
    def run(batch_id, **kwargs):
        return _run_metadata(
            ColabParityPipeline(client=FakeClient()).run(
                _narrative(),
                _structure_config(
                    tmp_path, variation_count=4, batch_id=batch_id, deduplicate=False,
                    **kwargs,
                ),
            )
        )

    first = run("seed-a")
    second = run("seed-b")
    fixed = run("seed-fixed", emotional_arc="tragedy")
    assert [m["selected_elements"] for m in first] == [m["selected_elements"] for m in second]
    assert [m["plot_type"] for m in first] == [m["plot_type"] for m in fixed]
    # 形の選択は要素の乱数とは別。固定しても、要素とプロット形式の選ばれ方は変わらない
    def without_arc(meta):
        return {k: v for k, v in meta["selected_elements"].items() if k != "emotional_arc"}

    assert [without_arc(m) for m in first] == [without_arc(m) for m in fixed]
    assert {m["selected_elements"]["emotional_arc"] for m in fixed} == {"tragedy"}


def test_batch_analyzer_counts_emotional_arcs():
    from pathlib import Path
    from src.batch_analyzer import BatchAnalyzer, CompletedRun

    runs = [
        CompletedRun(i, f"run_00{i}", Path("."),
                     {"plot_type": "旅", "selected_elements": {"emotional_arc": arc}},
                     Path("story.md"), "")
        for i, arc in enumerate(("icarus", "tragedy", "icarus"), start=1)
    ]
    frequencies = BatchAnalyzer._frequency_payload(runs)
    assert frequencies["emotional_arc"][0] == {
        "value": "icarus", "count": 2, "runs": ["run_001", "run_003"],
    }


def test_cli_rejects_unknown_emotional_arc(monkeypatch, capsys):
    import run_pipeline

    monkeypatch.setattr("sys.argv", ["run_pipeline.py", "--emotional-arc", "vonnegut"])
    with pytest.raises(SystemExit):
        run_pipeline.main()
    assert "--emotional-arc" in capsys.readouterr().err
