"""対話式ナラティブ入力のテスト。"""

import json
from pathlib import Path

from run_pipeline import load_narrative
from src.narrative_analyzer import NarrativeInput
from src.narrative_interview import NARRATIVE_FIELDS, NARRATIVE_QUESTIONS, run_interview


def _scripted_input(values, prompts):
    iterator = iter(values)

    def input_fn(prompt):
        prompts.append(prompt)
        value = next(iterator)
        if isinstance(value, BaseException):
            raise value
        return value

    return input_fn


def _single_line_answers(values=None):
    values = values or {key: f"回答-{key}" for key in NARRATIVE_FIELDS}
    return [item for key in NARRATIVE_FIELDS for item in (values[key], ".")]


def test_all_narrative_questions_have_labels():
    assert len(NARRATIVE_QUESTIONS) == 13
    assert all(question.label for question in NARRATIVE_QUESTIONS)


def test_all_answers_are_saved_and_loadable(tmp_path: Path):
    output_path = tmp_path / "narrative.json"
    prompts = []

    result = run_interview(
        output_path,
        input_fn=_scripted_input(_single_line_answers(), prompts),
        output_fn=lambda _message: None,
    )

    assert result == 0
    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert list(data) == list(NARRATIVE_FIELDS)
    assert NarrativeInput(**data).desire == "回答-desire"
    assert load_narrative(str(output_path)).author == "回答-author"


def test_two_blank_lines_end_a_multiline_answer(tmp_path: Path):
    output_path = tmp_path / "narrative.json"
    values = {key: f"回答-{key}" for key in NARRATIVE_FIELDS}
    scripted = ["一行目", "二行目", "", ""]
    scripted.extend(_single_line_answers(values)[2:])

    result = run_interview(
        output_path,
        input_fn=_scripted_input(scripted, []),
        output_fn=lambda _message: None,
    )

    assert result == 0
    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert data["author"] == "一行目\n二行目"


def test_empty_answer_can_be_skipped_and_confirmed(tmp_path: Path):
    output_path = tmp_path / "narrative.json"
    scripted = ["", "", "y"] + _single_line_answers()[2:] + ["y"]
    messages = []

    result = run_interview(
        output_path,
        input_fn=_scripted_input(scripted, []),
        output_fn=messages.append,
    )

    assert result == 0
    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert data["author"] == ""
    assert any("警告" in message for message in messages)


def test_edit_mode_empty_enter_keeps_current_value(tmp_path: Path):
    source_path = tmp_path / "existing.json"
    output_path = tmp_path / "edited.json"
    original = {key: f"現在値-{key}" for key in NARRATIVE_FIELDS}
    source_path.write_text(json.dumps(original, ensure_ascii=False), encoding="utf-8")

    result = run_interview(
        output_path,
        from_path=source_path,
        input_fn=_scripted_input([""] * len(NARRATIVE_FIELDS), []),
        output_fn=lambda _message: None,
    )

    assert result == 0
    assert json.loads(output_path.read_text(encoding="utf-8")) == original


def test_interrupt_saves_partial_json(tmp_path: Path):
    output_path = tmp_path / "narrative.json"
    partial_path = Path(f"{output_path}.partial.json")
    messages = []

    result = run_interview(
        output_path,
        input_fn=_scripted_input(["途中まで", EOFError()], []),
        output_fn=messages.append,
    )

    assert result == 1
    partial = json.loads(partial_path.read_text(encoding="utf-8"))
    assert partial["author"] == "途中まで"
    assert any("--from" in message for message in messages)


def test_overwrite_rejection_does_not_save(tmp_path: Path):
    output_path = tmp_path / "narrative.json"
    original = '{"keep": true}\n'
    output_path.write_text(original, encoding="utf-8")

    result = run_interview(
        output_path,
        input_fn=_scripted_input(["n"], []),
        output_fn=lambda _message: None,
    )

    assert result == 0
    assert output_path.read_text(encoding="utf-8") == original
