"""ポルティの劇的状況の軸と、プロット形式との除外表（#60）。"""

import json

import pytest

from src.colab_features import DEFAULT_PLOT_TYPES
from src.colab_pipeline import ColabParityPipeline, PipelineConfig
from src.dramatic_situations import (
    DRAMATIC_SITUATIONS_PATH,
    load_situation_table,
    situation_table,
)
from tests.test_colab_pipeline import FakeClient, _narrative, _run_metadata, _structure_config


class PlotListClient(FakeClient):
    """分類器が返すプロット形式の名前を差し替えられるクライアント。"""

    def __init__(self, names):
        super().__init__()
        self.names = names

    def chat_json(self, prompt, system="", temperature=0.3, model=None):
        if '"plot_list"' in prompt:
            self.json_calls.append(prompt)
            return {"plot_list": [{"name": name} for name in self.names]}
        return super().chat_json(prompt, system=system, temperature=temperature, model=model)


def _run(tmp_path, client, **kwargs):
    values = dict(variation_count=1, batch_id="situation", deduplicate=False)
    values.update(kwargs)
    return ColabParityPipeline(client=client).run(
        _narrative(), _structure_config(tmp_path, **values)
    )


def _plot_type_names(batch):
    # metadata.json の plot_type は、形式の記述（先頭行が名前）と状況の行の文
    return {
        meta["plot_type"].splitlines()[0].removeprefix("- **name**: ")
        for meta in _run_metadata(batch)
    }


def _situation_numbers(batch):
    return [
        int(meta["selected_elements"]["dramatic_situation"].split(".")[0])
        for meta in _run_metadata(batch)
    ]


def test_table_has_the_36_situations_of_the_source_in_order():
    table = situation_table()
    assert [item.number for item in table.situations] == list(range(1, 37))
    # 見出しは arayashiki-culture cul-0086（仏語原典を読んだ項目）と同じ
    assert table.get(1).name_fr == "Implorer"
    assert table.get(3).name_ja == "罪を追う復讐"
    assert table.get(36).name_fr == "Perdre les siens"
    assert table.get(36).name_ja == "愛する者を失う"


def test_every_plot_type_has_an_exclusion_entry():
    table = situation_table()
    assert set(table.exclusions) == set(DEFAULT_PLOT_TYPES)
    assert table.conflicts("復讐", 3)
    assert table.conflicts("復讐", 4)
    assert not table.conflicts("復讐", 1)
    assert [item.number for item in table.allowed("復讐")] == [
        n for n in range(1, 37) if n not in (3, 4)
    ]
    with pytest.raises(ValueError, match="DEFAULT_PLOT_TYPES"):
        table.allowed("旅")


@pytest.mark.parametrize(
    "change, message",
    [
        (lambda d: d["exclusions"].pop("復讐"), "exactly the plot types"),
        (lambda d: d["exclusions"].update({"旅": []}), "exactly the plot types"),
        (lambda d: d["exclusions"].update({"復讐": [37]}), "situation numbers"),
        (lambda d: d["exclusions"].update({"復讐": list(range(1, 37))}), "leave no situation"),
        (lambda d: d["situations"].pop(), "numbered 1 to 36"),
    ],
)
def test_broken_table_is_rejected(tmp_path, change, message):
    source = json.loads(DRAMATIC_SITUATIONS_PATH.read_text(encoding="utf-8"))
    change(source)
    path = tmp_path / "table.json"
    path.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        load_situation_table(path)


def test_pipeline_chooses_situation_per_work_and_puts_it_in_prompts(tmp_path):
    client = FakeClient()
    batch = _run(tmp_path, client, variation_count=4)
    manifest = json.loads(
        (batch.output_dir / "batch_manifest.json").read_text(encoding="utf-8")
    )
    # 固定指定なし（null）＝作品ごとに自動で選ぶ
    assert manifest["dramatic_situation"] is None
    labels = [meta["selected_elements"]["dramatic_situation"] for meta in _run_metadata(batch)]
    assert len(labels) == 4
    table = situation_table()
    structure_prompts = [p for p in client.json_calls if '"stages"' in p]
    assert len(structure_prompts) == 4
    for prompt, label in zip(structure_prompts, labels):
        situation = table.get(int(label.split(".")[0]))
        assert situation.label == label
        assert f"- **劇的状況**: {situation.name_ja}（ポルティ" in prompt
    # 人物と骨子のプロンプトにも同じ文で入る
    assert any("**劇的状況**" in p for p in client.chat_calls)


def test_excluded_situations_are_never_chosen(tmp_path):
    batch = _run(tmp_path, PlotListClient(["復讐"]), variation_count=40)
    numbers = _situation_numbers(batch)
    assert len(numbers) == 40
    assert not {3, 4} & set(numbers)
    assert len(set(numbers)) > 1


def test_situation_choice_is_reproducible_and_keeps_other_choices(tmp_path):
    def run(batch_id, **kwargs):
        return _run_metadata(
            _run(tmp_path, FakeClient(), variation_count=4, batch_id=batch_id, **kwargs)
        )

    first = run("seed-a")
    second = run("seed-b")
    fixed = run("seed-fixed", dramatic_situation=1)
    assert [m["selected_elements"] for m in first] == [m["selected_elements"] for m in second]

    def without_situation(meta):
        return {k: v for k, v in meta["selected_elements"].items() if k != "dramatic_situation"}

    # 状況は別の乱数で選ぶ。固定しても、要素・感情曲線・形式の選ばれ方は変わらない
    assert [without_situation(m) for m in first] == [without_situation(m) for m in fixed]
    assert {m["selected_elements"]["dramatic_situation"] for m in fixed} == {"1. 懇願"}


def test_plot_type_names_outside_the_list_are_dropped(tmp_path):
    batch = _run(tmp_path, PlotListClient(["旅", "復讐"]), variation_count=6)
    assert _plot_type_names(batch) == {"復讐"}


def test_no_usable_plot_type_stops_before_generation(tmp_path):
    client = PlotListClient(["旅", "Revenge"])
    with pytest.raises(ValueError, match="no usable plot type"):
        _run(tmp_path, client)
    assert not any("主人公のキャラクタープロフィール" in p for p in client.chat_calls)


def test_fixed_situation_skips_plot_types_that_exclude_it(tmp_path):
    batch = _run(
        tmp_path, PlotListClient(["復讐", "コメディ"]), variation_count=6, dramatic_situation=3
    )
    assert _plot_type_names(batch) == {"コメディ"}
    assert set(_situation_numbers(batch)) == {3}

    with pytest.raises(ValueError, match="no usable plot type"):
        _run(tmp_path, PlotListClient(["復讐"]), batch_id="only-revenge", dramatic_situation=3)


def test_config_validation(tmp_path):
    with pytest.raises(ValueError, match="fixed_plot_type must be one of"):
        PipelineConfig(fixed_plot_type="旅").validate()
    with pytest.raises(ValueError, match="unknown dramatic situation"):
        PipelineConfig(dramatic_situation=37).validate()
    with pytest.raises(ValueError, match="excluded for plot type"):
        PipelineConfig(fixed_plot_type="復讐", dramatic_situation=4).validate()
    PipelineConfig(fixed_plot_type="復讐", dramatic_situation=1).validate()


def test_manifest_and_resume_keep_the_fixed_situation(tmp_path):
    first = _run(tmp_path, FakeClient(), dramatic_situation=12, batch_id="fixed")
    manifest = json.loads(
        (first.output_dir / "batch_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["dramatic_situation"] == 12

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
    assert set(_situation_numbers(resumed)) == {12}

    with pytest.raises(ValueError, match="does not match"):
        ColabParityPipeline(client=FakeClient()).run(
            _narrative(),
            _structure_config(
                tmp_path,
                output_dir="output",
                variation_count=3,
                dramatic_situation=1,
                resume_dir=str(first.output_dir),
            ),
        )


def test_batch_analyzer_counts_situations():
    from pathlib import Path
    from src.batch_analyzer import BatchAnalyzer, CompletedRun

    runs = [
        CompletedRun(i, f"run_00{i}", Path("."),
                     {"plot_type": "復讐", "selected_elements": {"dramatic_situation": label}},
                     Path("story.md"), "")
        for i, label in enumerate(("1. 懇願", "12. 獲得", "1. 懇願"), start=1)
    ]
    frequencies = BatchAnalyzer._frequency_payload(runs)
    assert frequencies["dramatic_situation"][0] == {
        "value": "1. 懇願", "count": 2, "runs": ["run_001", "run_003"],
    }


@pytest.mark.parametrize(
    "argv, option",
    [(["--situation", "37"], "--situation"), (["--plot-type", "旅"], "--plot-type")],
)
def test_cli_rejects_unknown_situation_and_plot_type(monkeypatch, capsys, argv, option):
    import run_pipeline

    monkeypatch.setattr("sys.argv", ["run_pipeline.py", *argv])
    with pytest.raises(SystemExit):
        run_pipeline.main()
    assert option in capsys.readouterr().err
