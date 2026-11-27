"""プロップの31機能から作品ごとに選んで並べる構造（#59）。"""

import json
import random

import pytest

from src import propp
from src.colab_pipeline import ColabParityPipeline
from src.plot_generator import (
    PROPP_FUNCTIONS_KEY,
    Plot,
    PlotStage,
    get_story_structure,
    propp_structure,
    structure_for_work,
)
from tests.test_colab_pipeline import FakeClient, _narrative, _run_metadata, _structure_config


def _choose(seed):
    return propp.choose_functions(random.Random(seed))


def test_table_has_the_31_functions_of_the_1928_edition_in_order():
    numbers = [item.number for item in propp.FUNCTIONS if item.key != "8a"]
    assert numbers == list(range(1, 32))
    assert propp.ALL_KEYS == tuple(str(n) for n in range(1, 32))
    # 見出しは初版 OCR（第III章）から写したもの
    assert propp.BY_KEY["1"].heading_ru == "Один из членов семьи отлучается из дома."
    assert propp.BY_KEY["1"].name_ru == "отлучка"
    assert propp.BY_KEY["8"].name_ru == "вредительство"
    assert propp.BY_KEY["8a"].name_ru == "недостача"
    assert propp.BY_KEY["19"].heading_ru == "Начальная беда или недостача ликвидируется."
    assert propp.BY_KEY["31"].heading_ru == "Герой вступает в брак и воцаряется."
    assert propp.BY_KEY["8a"].number == 8
    template = get_story_structure("propp-31")
    assert template.stage_count == 31
    assert template.per_work


@pytest.mark.parametrize("seed", range(200))
def test_every_choice_follows_the_rules(seed):
    keys = _choose(seed)
    # 保存した形から読み直せる（原典の順・重複なし・必須の機能あり）
    assert propp.parse_functions(propp.format_functions(keys)) == keys
    numbers = {propp.BY_KEY[key].number for key in keys}
    assert {8, 11, 19} <= numbers
    assert sum(key in ("8", "8a") for key in keys) == 1
    # 組は全部入るか全部入らない
    for unit in propp._UNITS:
        included = [key in keys for key in unit]
        assert all(included) or not any(included), unit
    # 骨子A〜Eのどの部にも段がある
    assert {propp.BY_KEY[key].part for key in keys} == set(propp.PARTS)


def test_choice_is_reproducible_and_varies_between_works():
    assert _choose(7) == _choose(7)
    choices = {_choose(seed) for seed in range(50)}
    assert len(choices) > 40
    assert {len(keys) for keys in choices} != {len(_choose(0))}
    forms = {key for keys in choices for key in keys if key in ("8", "8a")}
    assert forms == {"8", "8a"}


def test_stage_definitions_number_stages_and_mark_roles():
    keys = ("1", "8a", "11", "12", "13", "14", "19", "20", "31")
    structure = propp_structure(keys)
    assert [s["stage"] for s in structure.stages] == list(range(1, 10))
    assert [s["name"] for s in structure.stages] == [
        "不在", "欠如", "出発", "贈与者の試し", "主人公の反応", "魔法の手段の獲得",
        "解消", "帰還", "結婚",
    ]
    assert [s["act"] for s in structure.stages] == (
        ["第一幕"] * 3 + ["第二幕"] * 4 + ["第三幕"] * 2
    )
    # 最初と最後は引き、第19機能（物語の頂点）は close_up
    assert [s["role"] for s in structure.stages] == [
        "wide", None, None, None, None, None, "peak", None, "wide",
    ]
    assert structure.skeleton_parts == {
        "A": (1, 2, 3), "B": (4, 5, 6), "C": (7,), "D": (8,), "E": (9,),
    }


@pytest.mark.parametrize(
    "text, message",
    [
        ("1,8,11,19,32", "unknown propp function"),
        ("1,11,8,19,20", "original order"),
        ("8,8a,11,19", "original order"),
        ("1,8,19,20", "miss required"),
        ("", "non-empty"),
    ],
)
def test_parse_rejects_broken_sequences(text, message):
    with pytest.raises(ValueError, match=message):
        propp.parse_functions(text)


def test_structure_for_work_needs_the_saved_sequence():
    template = get_story_structure("propp-31")
    work = structure_for_work(template, {PROPP_FUNCTIONS_KEY: "8,11,12,13,14,19,20,30"})
    assert work.stage_count == 8
    with pytest.raises(ValueError, match="propp_functions"):
        structure_for_work(template, {})
    other = get_story_structure("journey-12")
    assert structure_for_work(other, {}) is other


def _run(tmp_path, client, **kwargs):
    values = dict(structure="propp-31", variation_count=3, batch_id="propp", deduplicate=False)
    values.update(kwargs)
    return ColabParityPipeline(client=client).run(
        _narrative(), _structure_config(tmp_path, **values)
    )


def test_pipeline_chooses_functions_per_work_and_records_roles(tmp_path):
    client = FakeClient()
    batch = _run(tmp_path, client)
    manifest = json.loads((batch.output_dir / "batch_manifest.json").read_text(encoding="utf-8"))
    assert manifest["structure"] == "propp-31"
    # 段数は作品ごとに違うので、バッチには書かない
    assert manifest["journey_stage_count"] is None

    metas = _run_metadata(batch)
    assert len(metas) == 3
    structure_prompts = [p for p in client.json_calls if '"stages"' in p]
    assert len(structure_prompts) == 3
    for meta, prompt in zip(metas, structure_prompts):
        keys = propp.parse_functions(meta["selected_elements"][PROPP_FUNCTIONS_KEY])
        work = propp_structure(keys)
        assert meta["structure"] == "propp-31"
        assert meta["stage_count"] == len(keys)
        assert meta["stage_roles"] == [s["role"] for s in work.stages]
        assert f"プロップの31機能{len(keys)}段階" in prompt
        for stage in work.stages:
            assert f"{stage['stage']}. {stage['name']} ({stage['act']})" in prompt


def test_pipeline_choice_is_reproducible_and_leaves_other_choices_alone(tmp_path):
    first = _run_metadata(_run(tmp_path, FakeClient(), batch_id="a"))
    second = _run_metadata(_run(tmp_path, FakeClient(), batch_id="b"))
    journey = _run_metadata(_run(tmp_path, FakeClient(), batch_id="c", structure=None))
    assert [m["selected_elements"] for m in first] == [m["selected_elements"] for m in second]

    def without_propp(meta):
        return {k: v for k, v in meta["selected_elements"].items() if k != PROPP_FUNCTIONS_KEY}

    # 機能は別の乱数で選ぶので、要素・感情曲線の選ばれ方は構造によらず同じ
    assert [without_propp(m) for m in first] == [m["selected_elements"] for m in journey]
    assert all("stage_roles" not in m for m in journey)


def test_skeleton_parts_follow_the_chosen_functions(tmp_path):
    client = FakeClient()
    batch = _run(tmp_path, client, variation_count=1, generate_skeleton=True)
    keys = propp.parse_functions(
        _run_metadata(batch)[0]["selected_elements"][PROPP_FUNCTIONS_KEY]
    )
    work = propp_structure(keys)
    skeleton_prompts = [p for p in client.chat_calls if "プロップの31機能の次の段" in p]
    assert len(skeleton_prompts) == 5
    for part, prompt in zip("ABCDE", skeleton_prompts):
        for number in work.skeleton_parts[part]:
            assert f"{number}. {work.stages[number - 1]['name']}" in prompt


def test_storyboard_uses_recorded_roles(tmp_path):
    from src.storyboard import _stage_plan, build_shot_list
    from tests.test_storyboard_shots import FakeClient as ShotClient, _write_run

    work = propp_structure(("1", "2", "3", "8", "11", "15", "16", "18", "19", "21", "22", "30"))
    plot = Plot(
        stages=tuple(
            PlotStage(s["stage"], s["name"], s["act"], f"{s['name']}の展開。")
            for s in work.stages
        ),
        outline="アウトライン",
    )
    run = _write_run(tmp_path, chapters=False)
    (run / "story.md").write_text(
        f"# テスト作品\n\n## プロット\n\n{plot.to_text()}\n", encoding="utf-8"
    )
    metadata = json.loads((run / "metadata.json").read_text(encoding="utf-8"))
    roles = [s["role"] for s in work.stages]
    metadata.update(structure="propp-31", stage_count=work.stage_count, stage_roles=roles)
    (run / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")

    result = build_shot_list(run, ShotClient(), unit="stage")
    sizes = [shot["shot_size"] for shot in result.shots]
    assert sizes == _stage_plan(work.stage_count, roles)
    assert sizes[0] in ("extreme_long", "long")
    assert sizes[-1] in ("extreme_long", "long")
    assert sizes[roles.index("peak")] == "close_up"


def test_storyboard_ignores_roles_that_do_not_match_the_plot(tmp_path, capsys):
    from src.storyboard import _read_run_input
    from tests.test_storyboard_shots import _write_run

    run = _write_run(tmp_path, chapters=False)
    metadata = json.loads((run / "metadata.json").read_text(encoding="utf-8"))
    metadata["stage_roles"] = ["wide", "peak", "wide"]  # プロットは2段
    (run / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
    assert _read_run_input(run).stage_roles is None
    assert "stage_roles" in capsys.readouterr().err


def test_comparison_reports_stage_count_per_work(tmp_path):
    from src.batch_comparison import _batch_payload

    batch = _run(tmp_path, FakeClient(), variation_count=1)
    assert _batch_payload(batch.output_dir, tmp_path)["stage_count"] == "作品ごと"


def test_resume_keeps_the_structure_and_draws_new_works(tmp_path):
    first = _run(tmp_path, FakeClient(), variation_count=1, batch_id="resume")
    resumed = ColabParityPipeline(client=FakeClient()).run(
        _narrative(),
        _structure_config(
            tmp_path,
            variation_count=2,
            resume_dir=str(first.output_dir),
            deduplicate=False,
        ),
    )
    metas = _run_metadata(resumed)
    assert len(metas) == 2
    assert {m["structure"] for m in metas} == {"propp-31"}
    for meta in metas:
        propp.parse_functions(meta["selected_elements"][PROPP_FUNCTIONS_KEY])
