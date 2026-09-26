"""バッチ横断分析のテスト。"""

import json

import src.llm_factory as llm_factory
from src.batch_analyzer import BatchAnalyzer, analyze_batch


def _write_batch(tmp_path):
    batch = tmp_path / "batch"
    batch.mkdir()
    (batch / "batch_manifest.json").write_text(
        json.dumps(
            {
                "provider": "ollama",
                "model": "test-model",
                "variation_count": 3,
                "chapter_count": 10,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (batch / "narrative.json").write_text(
        json.dumps({"loss": "安心できる場所", "desire": "尊敬されたい"}),
        encoding="utf-8",
    )
    for number, title, plot_type, selected, protagonist in (
        (1, "第一作", "旅", {"want": "居場所", "ability": "共感", "role": "孤独", "narrative": "対話"}, "一郎"),
        (2, "第二作", "旅", {"want": "居場所", "ability": "夢", "role": "孤独", "narrative": "対話"}, "二郎"),
    ):
        run = batch / f"run_{number:03d}"
        run.mkdir()
        (run / "metadata.json").write_text(
            json.dumps(
                {
                    "title": title,
                    "plot_type": (
                        "- **name**: 旅\n- **core_structure**: 物語の構造"
                        if number == 1
                        else {"name": plot_type}
                    ),
                    "character_names": {"protagonist": protagonist},
                    "selected_elements": selected,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (run / f"story_{number}.md").write_text(
            f"# {title}\n\n本文です。", encoding="utf-8"
        )
    incomplete = batch / "run_003"
    incomplete.mkdir()
    (incomplete / "metadata.json").write_text("{}", encoding="utf-8")
    return batch


def test_deterministic_report_counts_frequencies_and_skips_incomplete(tmp_path):
    batch = _write_batch(tmp_path)
    report = analyze_batch(batch, no_llm=True)

    assert report["overview"]["target_count"] == 2
    assert report["overview"]["skipped_count"] == 1
    assert report["overview"]["skipped_runs"] == ["run_003"]
    assert report["works"][0]["body_markdown"] == "run_001/story_1.md"
    assert report["frequencies"]["plot_type"][0] == {
        "value": "旅",
        "count": 2,
        "runs": ["run_001", "run_002"],
    }
    assert report["frequencies"]["want"][0]["runs"] == ["run_001", "run_002"]
    assert (batch / "batch_report.md").exists()
    assert (batch / "batch_report.json").exists()


def test_no_llm_does_not_call_client(tmp_path):
    class FailingClient:
        def chat_json(self, **_kwargs):
            raise AssertionError("LLM must not be called")

    report = BatchAnalyzer(
        _write_batch(tmp_path), client=FailingClient()
    ).analyze(no_llm=True)

    assert report["cross_analysis"]["enabled"] is False


class SummaryClient:
    def __init__(self):
        self.calls = []

    def chat_json(self, prompt, system="", temperature=0.3):
        self.calls.append(prompt)
        if '"patterns"' in prompt:
            return {
                "patterns": [
                    {
                        "pattern": "対話への回帰",
                        "evidence_runs": ["run_001", "run_999", 2, "001"],
                        "question": "『本当の願望』との関係をどう考えられますか？",
                    }
                ]
            }
        return {
            "protagonist_desire": "つながり",
            "adversary_type": "孤立",
            "central_loss": "古い居場所",
            "ending": "変容",
            "key_motifs": ["風", "対話"],
        }


def test_cross_summary_cache_and_refresh(tmp_path):
    batch = _write_batch(tmp_path)
    first_client = SummaryClient()
    analyze_batch(batch, client=first_client)
    assert len(first_client.calls) == 3  # 2作品の要約 + 統合
    cache = batch / "run_001" / "cross_summary.json"
    assert cache.exists()

    cached_client = SummaryClient()
    analyze_batch(batch, client=cached_client)
    assert len(cached_client.calls) == 1  # 統合だけ再実行

    refresh_client = SummaryClient()
    analyze_batch(batch, client=refresh_client, refresh=True)
    assert len(refresh_client.calls) == 3


def test_nonexistent_evidence_runs_are_removed(tmp_path):
    report = analyze_batch(batch := _write_batch(tmp_path), client=SummaryClient())

    evidence = report["cross_analysis"]["patterns"][0]["evidence_runs"]
    assert evidence == ["run_001", "run_002"]
    assert "run_999" not in (batch / "batch_report.md").read_text(encoding="utf-8")


def test_llm_parse_failure_retries_and_writes_fallback(tmp_path):
    class InvalidClient:
        def __init__(self):
            self.calls = 0
            self.integration_calls = 0

        def chat_json(self, prompt, **_kwargs):
            self.calls += 1
            if '"patterns"' in prompt:
                self.integration_calls += 1
            raise ValueError("invalid JSON")

    client = InvalidClient()
    report = analyze_batch(_write_batch(tmp_path), client=client)

    assert client.calls == 4  # 要約2作品×2回。全件失敗なので統合なし
    assert client.integration_calls == 0
    assert report["cross_analysis"]["status"] == "生成失敗"
    assert report["cross_analysis"]["summaries"][0]["ending"] == "生成失敗"
    assert "生成失敗" in (tmp_path / "batch" / "batch_report.md").read_text(
        encoding="utf-8"
    )


def test_failed_summary_is_not_cached_and_is_retried_next_time(tmp_path):
    batch = _write_batch(tmp_path)

    class AlwaysInvalidClient:
        def __init__(self):
            self.calls = 0

        def chat_json(self, **_kwargs):
            self.calls += 1
            raise ValueError("temporary failure")

    first_client = AlwaysInvalidClient()
    analyze_batch(batch, client=first_client)
    assert first_client.calls == 4
    assert not (batch / "run_001" / "cross_summary.json").exists()
    assert not (batch / "run_002" / "cross_summary.json").exists()

    second_client = SummaryClient()
    analyze_batch(batch, client=second_client)
    assert len(second_client.calls) == 3
    assert (batch / "run_001" / "cross_summary.json").exists()


def test_failed_runs_are_excluded_from_integration_prompt(tmp_path):
    batch = _write_batch(tmp_path)

    class PartialClient(SummaryClient):
        def __init__(self):
            super().__init__()
            self.integration_prompt = None

        def chat_json(self, prompt, system="", temperature=0.3):
            if '"patterns"' in prompt:
                self.integration_prompt = prompt
                return super().chat_json(prompt, system, temperature)
            if "（run_001）" in prompt:
                self.calls.append(prompt)
                raise ValueError("run_001 summary failed")
            return super().chat_json(prompt, system, temperature)

    client = PartialClient()
    report = analyze_batch(batch, client=client)

    assert report["cross_analysis"]["summaries"][0]["ending"] == "生成失敗"
    assert report["cross_analysis"]["summaries"][1]["ending"] == "変容"
    assert client.integration_prompt is not None
    assert "run_001" not in client.integration_prompt
    assert "run_002" in client.integration_prompt


def test_plot_type_name_is_extracted_from_metadata_markdown(tmp_path):
    report = analyze_batch(_write_batch(tmp_path), no_llm=True)

    assert report["works"][0]["plot_type"] == "旅"
    assert report["frequencies"]["plot_type"][0]["value"] == "旅"


def test_long_ollama_body_is_truncated_with_warning(tmp_path, capsys):
    batch = _write_batch(tmp_path)
    head = "冒頭に残る文字列"
    tail = "末尾に残る文字列"
    (batch / "run_001" / "story_1.md").write_text(
        head + ("本文" * 1000) + tail,
        encoding="utf-8",
    )
    client = SummaryClient()
    analyze_batch(batch, client=client, provider="ollama", num_ctx=1000)

    summary_prompt = next(prompt for prompt in client.calls if '"patterns"' not in prompt)
    assert head in summary_prompt
    assert tail in summary_prompt
    assert "冒頭と末尾を残して中略しています" in summary_prompt
    assert "中略しました" in capsys.readouterr().err


def test_non_ollama_body_is_not_truncated(tmp_path, capsys):
    batch = _write_batch(tmp_path)
    body = "冒頭" + ("本文" * 1000) + "末尾"
    (batch / "run_001" / "story_1.md").write_text(body, encoding="utf-8")
    client = SummaryClient()
    analyze_batch(batch, client=client, provider="openai", num_ctx=1000)

    summary_prompt = next(prompt for prompt in client.calls if '"patterns"' not in prompt)
    assert body in summary_prompt
    assert "中略しました" not in capsys.readouterr().err


def test_provider_factory_num_ctx_override_does_not_change_default(
    monkeypatch,
):
    monkeypatch.setattr(
        llm_factory,
        "resolve_ollama_model",
        lambda _requested, _timeout: "gemma4:e4b",
    )

    overridden, _ = llm_factory.create_provider_client(
        "ollama", "gemma4:e4b", 10, num_ctx=32768
    )
    default, _ = llm_factory.create_provider_client("ollama", "gemma4:e4b", 10)

    assert overridden.config.num_ctx == 32768
    assert default.config.num_ctx == 8192
