"""対話式ナラティブ入力。

端末入出力を ``input_fn`` / ``output_fn`` で差し替えられるようにし、
CLIからもテストからも同じ入力フローを利用できるようにする。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Mapping, Optional, Tuple, Union


InputFn = Callable[[str], str]
OutputFn = Callable[[str], object]
PathLike = Union[str, Path]


@dataclass(frozen=True)
class NarrativeQuestion:
    """ナラティブの1項目に対する質問と補足。"""

    key: str
    question: str
    hint: str
    label: str


# NarrativeInput、README、設計仕様の入力項目をここで一元管理する。
NARRATIVE_QUESTIONS: Tuple[NarrativeQuestion, ...] = (
    NarrativeQuestion(
        "author",
        "あなたはどんな人物ですか？",
        "思いつくままに、自分らしさや興味のあることを書いてください。",
        "自己紹介",
    ),
    NarrativeQuestion(
        "missing",
        "あなたには何が欠けていると感じますか？",
        "「私には○○が欠けている。それは○○を象徴する」の形も参考にしてください。",
        "自分に欠けていると感じるもの",
    ),
    NarrativeQuestion(
        "status",
        "あなたは今、自分の状況をどう評価していますか？",
        "成功している／かつては成功していた／まだ成功していない／成功とは何かわからない、など。",
        "現在の状態",
    ),
    NarrativeQuestion(
        "memories",
        "現在の状況に最も強い影響を与えた過去のできごとは何ですか？",
        "印象に残っている記憶や、今の自分につながる体験を教えてください。",
        "印象に残っている記憶",
    ),
    NarrativeQuestion(
        "mission",
        "欠けているものを手に入れるために、クリアすべき具体的なミッションは何ですか？",
        "自分が取り組む課題や、実際に起こす必要のある行動を考えてください。",
        "果たしたい使命",
    ),
    NarrativeQuestion(
        "success",
        "欠けているものが、いつか手に入るとイメージできますか？",
        "手に入った状態を想像できるか、見込みや実感を書いてください。",
        "成功のイメージ",
    ),
    NarrativeQuestion(
        "loss",
        "欠けているものを手に入れる過程で、手放さなければいけないものは何ですか？",
        "安心できる場所、時間、関係など、代償になりそうなものを考えてください。",
        "失うことが怖いもの",
    ),
    NarrativeQuestion(
        "taboo",
        "欠けているものを手に入れようとする過程で、決して破ってはいけないタブーは何ですか？",
        "自分に課している境界線や、守りたい価値観を教えてください。",
        "越えたくない境界",
    ),
    NarrativeQuestion(
        "inhibit",
        "欠けているものを手に入れようとするとき、いつも邪魔するものは何ですか？",
        "自分の内側・外側にある阻害要因や、繰り返し立ちはだかるものを書いてください。",
        "自分を抑えているもの",
    ),
    NarrativeQuestion(
        "daily",
        "あなたの日常生活を表すキーワードは何ですか？",
        "習慣、場所、人、感覚など、日常世界を象徴する言葉を挙げてください。",
        "日常",
    ),
    NarrativeQuestion(
        "change",
        "あなたの日常生活に変化をもたらす存在は何ですか？",
        "人、出来事、考え方など、日常を動かすきっかけを考えてください。",
        "変化のきっかけ",
    ),
    NarrativeQuestion(
        "acceptance",
        "大切なものを脅かす存在と、和解・許容できますか？",
        "敵対する相手や受け入れにくい現実に、どう向き合えるかを書いてください。",
        "受け入れられること／受け入れにくいこと",
    ),
    NarrativeQuestion(
        "desire",
        "誰にも話すことができない、あなたの秘めた願望は何ですか？",
        "本当は何を望んでいるのか、建前を外して自由に書いてください。",
        "本当の願望",
    ),
)

NARRATIVE_FIELDS: Tuple[str, ...] = tuple(item.key for item in NARRATIVE_QUESTIONS)


class InterviewInterrupted(Exception):
    """入力途中でCtrl+CまたはEOFを受け取った。"""

    def __init__(self, partial: str = "") -> None:
        super().__init__()
        self.partial = partial


class NarrativeInterview:
    """13項目のナラティブを対話的に収集してJSONへ保存する。"""

    def __init__(
        self,
        output_path: PathLike = "narrative.json",
        from_path: Optional[PathLike] = None,
        *,
        input_fn: Optional[InputFn] = None,
        output_fn: Optional[OutputFn] = None,
    ) -> None:
        self.output_path = Path(output_path)
        self.from_path = Path(from_path) if from_path is not None else None
        self.input_fn = input_fn or input
        self.output_fn = output_fn or print
        self._edit_mode = self.from_path is not None
        self._answers: Dict[str, str] = {}
        self._skipped: list[str] = []
        self._active_key: Optional[str] = None

    def run(self) -> int:
        """対話を実行する。成功・通常キャンセルは0、中断は1を返す。"""

        try:
            if self.from_path is not None:
                self._answers = self._load_existing(self.from_path)

            self._write_output(
                "あなた自身についての13の問いに答えると、そこから物語が生まれます。\n"
                "回答はこの端末上のローカルファイルに保存されるだけで、外部へ送信されません。"
            )
            self._write_output(
                "回答は複数行で入力できます。空行を2回入力するか、単独の「.」を入力すると次の問いへ進みます。"
            )

            if self.output_path.exists() and not self._confirm(
                f"出力先 {self.output_path} は既に存在します。上書きしますか？ (y/N) "
            ):
                self._write_output("保存をキャンセルしました。")
                return 0

            for number, question in enumerate(NARRATIVE_QUESTIONS, start=1):
                self._ask_question(number, question)

            if self._skipped:
                labels = "、".join(self._skipped)
                self._write_output(f"警告: 次の項目はスキップされました: {labels}")
                if not self._confirm("空欄の項目を残したまま保存しますか？ (y/N) "):
                    self._write_output("保存をキャンセルしました。")
                    return 0

            self._save_json(self.output_path, self._answers)
            self._write_output(f"ナラティブを保存しました: {self.output_path}")
            self._write_output(
                f"次に実行: python run_pipeline.py --narrative-json {self.output_path} --loops 1 --pool-size 3"
            )
            return 0
        except InterviewInterrupted as interrupted:
            if interrupted.partial:
                # 現在の問いで入力されていた行も、再開可能な回答として残す。
                if self._active_key is not None:
                    self._answers[self._active_key] = interrupted.partial
            partial_path = Path(f"{self.output_path}.partial.json")
            try:
                self._save_json(partial_path, self._answers)
                self._write_output(f"入力を中断しました。途中までの回答を保存しました: {partial_path}")
            except OSError as exc:
                self._write_output(f"入力を中断しました。途中回答の保存に失敗しました: {exc}")
            self._write_output(
                f"--from {partial_path} を指定すると再開できます。"
            )
            return 1
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            self._write_output(f"エラー: {exc}")
            return 2

    def _ask_question(self, number: int, question: NarrativeQuestion) -> None:
        self._active_key = question.key
        self._write_output(f"\n[{number}/{len(NARRATIVE_QUESTIONS)}] {question.question}")
        self._write_output(f"ヒント: {question.hint}")

        if self._edit_mode:
            current = self._answers.get(question.key, "")
            displayed = current if current else "（未入力）"
            self._write_output(f"現在値: {displayed}")
        else:
            current = ""

        answer = self._read_answer(current=current)
        self._answers[question.key] = answer
        if answer == "" and question.key not in self._skipped:
            self._skipped.append(question.key)

    def _read_answer(self, *, current: str) -> str:
        while True:
            lines: list[str] = []
            blank_count = 0
            try:
                while True:
                    line = self.input_fn("> ")
                    if line == ".":
                        break

                    if not line.strip():
                        # 編集モードでは空Enterを「現在値を維持」とする。
                        if not lines and self._edit_mode and current:
                            return current
                        blank_count += 1
                        if blank_count >= 2:
                            break
                        continue

                    blank_count = 0
                    lines.append(line)
            except (KeyboardInterrupt, EOFError) as exc:
                raise InterviewInterrupted("\n".join(lines)) from exc

            answer = "\n".join(lines)
            if answer:
                return answer

            if self._edit_mode and current:
                return current

            if self._confirm("スキップしますか？ (y/N) "):
                return ""
            self._write_output("回答を入力してください。")

    def _confirm(self, prompt: str) -> bool:
        try:
            response = self.input_fn(prompt).strip().lower()
        except (KeyboardInterrupt, EOFError) as exc:
            raise InterviewInterrupted() from exc
        return response in {"y", "yes"}

    @staticmethod
    def _load_existing(path: Path) -> Dict[str, str]:
        with path.open(encoding="utf-8") as handle:
            loaded = json.load(handle)
        if not isinstance(loaded, Mapping):
            raise ValueError("既存JSONのトップレベルはオブジェクトである必要があります")

        answers: Dict[str, str] = {}
        for key in NARRATIVE_FIELDS:
            value = loaded.get(key, "")
            if not isinstance(value, str):
                raise ValueError(f"{key} の値は文字列である必要があります")
            answers[key] = value
        return answers

    @staticmethod
    def _save_json(path: Path, answers: Mapping[str, str]) -> None:
        values = {key: answers.get(key, "") for key in NARRATIVE_FIELDS}
        with path.open("w", encoding="utf-8") as handle:
            json.dump(values, handle, ensure_ascii=False, indent=2)
            handle.write("\n")

    def _write_output(self, message: str) -> None:
        self.output_fn(message)


def run_interview(
    output_path: PathLike = "narrative.json",
    from_path: Optional[PathLike] = None,
    *,
    input_fn: Optional[InputFn] = None,
    output_fn: Optional[OutputFn] = None,
) -> int:
    """対話を実行する関数版API。"""

    return NarrativeInterview(
        output_path=output_path,
        from_path=from_path,
        input_fn=input_fn,
        output_fn=output_fn,
    ).run()


__all__ = [
    "InputFn",
    "NarrativeQuestion",
    "NarrativeInterview",
    "NARRATIVE_FIELDS",
    "NARRATIVE_QUESTIONS",
    "run_interview",
]
