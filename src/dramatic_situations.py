"""ポルティ『36の劇的状況』（1895）と、プロット形式との除外表（#60）。

作品ごとに、プロット形式とは別の軸として状況を1つ選ぶ。形式と同じ意味の状況
（形式「復讐」と状況「罪を追う復讐」など）は、設定ファイルの除外表で決定論的に
除き、推論（LLM）では判断しない。
"""

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, FrozenSet, Tuple

from .colab_features import DEFAULT_PLOT_TYPES

DRAMATIC_SITUATIONS_PATH = (
    Path(__file__).resolve().parent.parent / "config" / "story" / "dramatic_situations.json"
)
SITUATION_COUNT = 36


@dataclass(frozen=True)
class DramaticSituation:
    """ポルティの状況1つ。番号は原典の並び（1〜36）。"""

    number: int
    name_fr: str
    name_ja: str

    @property
    def label(self) -> str:
        """metadata.json と集計で使う表記。"""
        return f"{self.number}. {self.name_ja}"

    def to_text(self) -> str:
        """プロンプトに入れる表記。"""
        return (
            f"- **劇的状況**: {self.name_ja}"
            f"（ポルティ『36の劇的状況』第{self.number}状況 {self.name_fr}）"
        )


@dataclass(frozen=True)
class SituationTable:
    situations: Tuple[DramaticSituation, ...]
    exclusions: Dict[str, FrozenSet[int]]

    def get(self, number: int) -> DramaticSituation:
        if isinstance(number, bool) or not isinstance(number, int):
            raise ValueError(f"unknown dramatic situation: {number!r}")
        if not 1 <= number <= len(self.situations):
            raise ValueError(f"unknown dramatic situation: {number}")
        return self.situations[number - 1]

    def conflicts(self, plot_type: str, number: int) -> bool:
        """形式と状況が同じ意味（除外表に載っている）なら True。"""
        return number in self._excluded(plot_type)

    def allowed(self, plot_type: str) -> Tuple[DramaticSituation, ...]:
        """その形式で選んでよい状況を、番号順に返す。"""
        excluded = self._excluded(plot_type)
        return tuple(item for item in self.situations if item.number not in excluded)

    def _excluded(self, plot_type: str) -> FrozenSet[int]:
        if plot_type not in self.exclusions:
            raise ValueError(f"plot type is not in DEFAULT_PLOT_TYPES: {plot_type}")
        return self.exclusions[plot_type]


def load_situation_table(path: Path = DRAMATIC_SITUATIONS_PATH) -> SituationTable:
    """設定ファイルを読み、36状況と全21形式の除外表が揃っているか確かめる。"""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    raw_situations = data.get("situations")
    if not isinstance(raw_situations, list):
        raise ValueError("dramatic_situations.json: situations must be a list")
    situations = tuple(
        DramaticSituation(
            number=int(item["number"]),
            name_fr=str(item["name_fr"]),
            name_ja=str(item["name_ja"]),
        )
        for item in raw_situations
    )
    if [item.number for item in situations] != list(range(1, SITUATION_COUNT + 1)):
        raise ValueError("dramatic_situations.json: situations must be numbered 1 to 36 in order")

    raw_exclusions = data.get("exclusions")
    if not isinstance(raw_exclusions, dict):
        raise ValueError("dramatic_situations.json: exclusions must be an object")
    missing = [name for name in DEFAULT_PLOT_TYPES if name not in raw_exclusions]
    unknown = [name for name in raw_exclusions if name not in DEFAULT_PLOT_TYPES]
    if missing or unknown:
        raise ValueError(
            "dramatic_situations.json: exclusions must list exactly the plot types in "
            f"DEFAULT_PLOT_TYPES (missing: {missing}, unknown: {unknown})"
        )
    exclusions: Dict[str, FrozenSet[int]] = {}
    for name, numbers in raw_exclusions.items():
        if not isinstance(numbers, list) or any(
            isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= SITUATION_COUNT
            for n in numbers
        ):
            raise ValueError(
                f"dramatic_situations.json: exclusions for {name} must be situation numbers"
            )
        if len(numbers) >= SITUATION_COUNT:
            raise ValueError(
                f"dramatic_situations.json: exclusions for {name} leave no situation"
            )
        exclusions[name] = frozenset(numbers)
    return SituationTable(situations=situations, exclusions=exclusions)


@lru_cache(maxsize=1)
def situation_table() -> SituationTable:
    """リポジトリの設定ファイルから読んだ表（読み込みは1回）。"""
    return load_situation_table()
