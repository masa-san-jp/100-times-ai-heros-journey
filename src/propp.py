"""プロップ『昔話の形態学』（1928）の31の機能と、作品ごとの機能の選び方（#59）。

出典: В. Пропп『Морфология сказки』Ленинград: Academia, 1928（«Вопросы поэтики»
第12集）第III章「Функции действующих лиц」。Internet Archive の初版 OCR テキスト
（https://archive.org/details/1928_20230714_202307）で、31の見出しと定義語を読んだ。
``heading_ru`` と ``name_ru`` は見出しと定義語（OCR の誤字は直した）。日本語の名前と
説明は見出しからの訳。

作品ごとに、機能を原典の順番のまま一部だけ選んで並べる。選び方は決まった規則と
シード付きの乱数で、推論（LLM）は使わない。規則の根拠は ``_UNITS`` などの注記に書く。
"""

import random
from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

PROPP_STRUCTURE = "propp-31"
PROPP_LABEL = "プロップの31機能"

ACT_1 = "第一幕"
ACT_2 = "第二幕"
ACT_3 = "第三幕"

# 段の性質（src/storyboard.py の STAGE_ROLES と同じ値）。
ROLE_WIDE = "wide"
ROLE_PEAK = "peak"


@dataclass(frozen=True)
class ProppFunction:
    """機能1つ。``key`` は番号の文字列（第8機能の別の形「欠如」だけ ``"8a"``）。"""

    key: str
    number: int
    heading_ru: str
    name_ru: str
    name_ja: str
    description_ja: str
    # プロット骨子A〜Eのどの部に当たるか。
    part: str

    @property
    def act(self) -> str:
        return {"A": ACT_1, "B": ACT_2, "C": ACT_2}.get(self.part, ACT_3)


def _f(key, heading_ru, name_ru, name_ja, description_ja, part):
    return ProppFunction(key, int(key.rstrip("a")), heading_ru, name_ru, name_ja, description_ja, part)


# 骨子の部の割り当て:
# A（物語の始まり）= 1〜11。原典は1〜7を「準備部」、8〜11（加害・仲介・対抗の開始・出発）を
#   「発端」と呼ぶ。
# B（展開）= 12〜15。贈与者との出会いから、探すものの場所への移動まで。
# C（山場）= 16〜19。原典は19（解消）で「物語は頂点に達する」と書く。
# D（決着）= 20〜28。帰還から暴露まで。
# E（結末）= 29〜31。変身・罰・結婚。
# 幕は A を第一幕、B と C を第二幕、D と E を第三幕にする（原典に幕の区分は無い）。
FUNCTIONS: Tuple[ProppFunction, ...] = (
    _f("1", "Один из членов семьи отлучается из дома.", "отлучка",
       "不在", "家族の一人が家を離れる", "A"),
    _f("2", "К герою обращаются с запретом.", "запрет",
       "禁止", "主人公に禁止が言い渡される", "A"),
    _f("3", "Запрет нарушается.", "нарушение",
       "違反", "禁止が破られる", "A"),
    _f("4", "Вредитель пытается произвести разведку.", "выведывание",
       "探り", "加害者が様子を探ろうとする", "A"),
    _f("5", "Вредителю даются сведения о его жертве.", "выдача",
       "漏洩", "加害者に、狙う相手のことが知られてしまう", "A"),
    _f("6", "Вредитель пытается обмануть свою жертву, чтобы овладеть ею или ее имуществом.",
       "подвох", "謀略", "加害者が、相手やその持ち物を手に入れようと相手をだまそうとする", "A"),
    _f("7", "Жертва поддается обману и тем невольно помогает врагу.", "пособничество",
       "加担", "相手がだまされ、知らずに敵を助けてしまう", "A"),
    _f("8", "Вредитель наносит одному из членов семьи вред или ущерб.", "вредительство",
       "加害", "加害者が家族の一人に害や損失を与える", "A"),
    _f("8a", "Одному из членов семьи чего-либо не хватает, ему хочется иметь что-либо.",
       "недостача", "欠如", "家族の一人に何かが欠けていて、それを手に入れたいと望む", "A"),
    _f("9", "Беда или недостача сообщается, к герою обращаются с просьбой или приказанием, "
       "отсылают или отпускают его.", "посредничество, соединительный момент",
       "仲介", "災いや欠如が知らされ、主人公が頼まれるか命じられて送り出される", "A"),
    _f("10", "Искатель соглашается или решается на противодействие.",
       "начинающееся противодействие", "対抗の開始",
       "探しに行く主人公が、立ち向かうことを引き受けるか決心する", "A"),
    _f("11", "Герой покидает дом.", "отправка",
       "出発", "主人公が家を出る", "A"),
    _f("12", "Герой испытывается, выспрашивается, подвергается нападению и пр., чем "
       "подготовляется получение им волшебного средства или помощника.",
       "первая функция дарителя", "贈与者の試し",
       "主人公が試され、問いただされ、襲われるなどして、魔法の手段か助け手を得る準備が整う", "B"),
    _f("13", "Герой реагирует на действия будущего дарителя.", "реакция героя",
       "主人公の反応", "主人公が、のちの贈与者のふるまいに応える", "B"),
    _f("14", "В распоряжение героя попадает волшебное средство.",
       "снабжение, получение волшебного средства", "魔法の手段の獲得",
       "魔法の手段が主人公の手に入る", "B"),
    _f("15", "Герой переносится, доставляется или приводится к месту нахождения предмета "
       "поисков.", "пространственное перемещение между двумя царствами, путеводительство",
       "二つの国の間の移動", "主人公が、探すものがある場所へ運ばれるか連れて行かれる", "B"),
    _f("16", "Герой и вредитель вступают в непосредственную борьбу.", "борьба",
       "闘い", "主人公と加害者が直接闘う", "C"),
    _f("17", "Героя метят.", "клеймение, отметка",
       "標づけ", "主人公に印が付けられる", "C"),
    _f("18", "Вредитель побеждается.", "победа",
       "勝利", "加害者が打ち負かされる", "C"),
    # 第19機能だけ、初版の見出しに定義語（Опр.）が無く、記号（Л）だけがある。
    _f("19", "Начальная беда или недостача ликвидируется.", "",
       "解消", "最初の災いか欠如が解消される", "C"),
    _f("20", "Герой возвращается.", "возвращение",
       "帰還", "主人公が帰る", "D"),
    _f("21", "Герой подвергается преследованию.", "преследование, погоня",
       "追跡", "主人公が追われる", "D"),
    _f("22", "Герой спасается от преследования.", "спасение",
       "逃げ切り", "主人公が追っ手から逃れる", "D"),
    _f("23", "Герой неузнанным прибывает домой или в другую страну.", "неузнанное прибытие",
       "気づかれない到着", "主人公が、誰にも気づかれずに家か別の国に着く", "D"),
    _f("24", "Ложный герой предъявляет необоснованные притязания.",
       "необоснованные притязания", "偽の主人公の主張",
       "偽の主人公が、根拠のない手柄を言い立てる", "D"),
    _f("25", "Герою предлагается трудная задача.", "трудная задача",
       "難題", "主人公に難しい課題が出される", "D"),
    _f("26", "Задача решается.", "решение",
       "解決", "課題が解かれる", "D"),
    _f("27", "Героя узнают.", "узнавание",
       "認知", "主人公が誰なのかが分かる", "D"),
    _f("28", "Ложный герой или вредитель изобличается.", "обличение",
       "暴露", "偽の主人公か加害者の正体があばかれる", "D"),
    _f("29", "Герою дается новый облик.", "трансфигурация",
       "変身", "主人公が新しい姿を得る", "E"),
    _f("30", "Вредитель наказывается.", "наказание",
       "罰", "加害者が罰を受ける", "E"),
    _f("31", "Герой вступает в брак и воцаряется.", "свадьба",
       "結婚", "主人公が結婚し、王位に就く", "E"),
)

BY_KEY: Dict[str, ProppFunction] = {item.key: item for item in FUNCTIONS}
PARTS = ("A", "B", "C", "D", "E")

# どの作品にも入れる機能。
# 8: 原典「А か а（加害か欠如）はこの種の物語のどれにも欠かせない」。8a はその別の形。
# 11: 原典「物語の構造は、主人公がどうしても家を出ることを求める」。
# 19: 原典「この機能は加害と対をなす」「これで物語は頂点に達する」。
REQUIRED = ("8", "11", "19")
FORMS_OF_8 = ("8", "8a")

# 入れるか入れないかを、まとめて決める機能の組。組の中は全部入るか全部入らないか。
# 2-3, 4-5, 16-18, 21-22: 原典が対（парный элемент）として挙げる組。
# 6-7: 謀略とそれに乗る加担は、だます側とだまされる側の対。
# 12-13-14: 原典「Д・Г・Z もひとまとまりをなす」（試し・反応・獲得）。
# 17-27: 原典「認知は標づけに対応する機能」。印を付けたら、その印で見分ける。
# 24-28: 偽の主人公が名乗り出たら、あばかれるまでを入れる。
# 25-26: 原典の「難題―解決」（З―Р）。
_UNITS: Tuple[Tuple[str, ...], ...] = (
    ("1",), ("2", "3"), ("4", "5"), ("6", "7"),
    ("9",), ("10",),
    ("12", "13", "14"), ("15",),
    ("16", "18"), ("17", "27"),
    ("20",), ("21", "22"), ("23",), ("24", "28"), ("25", "26"),
    ("29",), ("30",), ("31",),
)
# 組ごとに入れる確率。原典は欠ける機能があっても順序は変わらないと書くだけで、
# 頻度は示さない。偏りを持ち込まないため、入れる・入れないを半々にする。
INCLUDE_PROBABILITY = 0.5


def choose_functions(rng: random.Random) -> Tuple[str, ...]:
    """作品1つ分の機能を選び、原典の順に並べたキーの並びを返す。

    1. 第8機能の形（加害か欠如）を選ぶ。
    2. ``REQUIRED`` を入れ、``_UNITS`` の組を1つずつ半々の確率で入れる。
    3. 骨子A〜Eのうち機能が1つも無い部があれば、その部に当たる組から1つ選んで入れる
       （骨子の各部は、少なくとも1つの段を必要とするため）。
    """
    form_of_8 = rng.choice(FORMS_OF_8)
    chosen = set(REQUIRED)
    for unit in _UNITS:
        if rng.random() < INCLUDE_PROBABILITY:
            chosen.update(unit)
    for part in PARTS:
        if any(BY_KEY[key].part == part for key in chosen):
            continue
        candidates = [unit for unit in _UNITS if any(BY_KEY[key].part == part for key in unit)]
        chosen.update(rng.choice(candidates))
    keys = sorted(chosen, key=lambda key: BY_KEY[key].number)
    return tuple(form_of_8 if key == "8" else key for key in keys)


def parse_functions(text: str) -> Tuple[str, ...]:
    """保存した並び（``"1,8a,11,19"`` の形）を読み、検証して返す。"""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("propp functions must be a non-empty string")
    keys = tuple(part.strip() for part in text.split(","))
    unknown = [key for key in keys if key not in BY_KEY]
    if unknown:
        raise ValueError(f"unknown propp function: {', '.join(unknown)}")
    numbers = [BY_KEY[key].number for key in keys]
    if numbers != sorted(set(numbers)):
        raise ValueError("propp functions must be in the original order without repeats")
    missing = [key for key in REQUIRED if int(key) not in numbers]
    if missing:
        raise ValueError(f"propp functions miss required: {', '.join(missing)}")
    return keys


def format_functions(keys: Sequence[str]) -> str:
    return ",".join(keys)


def stage_definitions(keys: Sequence[str]) -> Tuple[Tuple[Mapping[str, object], ...], Dict[str, Tuple[int, ...]]]:
    """選んだ機能から、段の定義と骨子A〜Eの段番号を作る。

    段の性質（``role``）は #51 の決定5と同じ規則: 最初と最後の段を引き（wide）、
    感情が最も動く段を close_up（peak）にする。peak は、原典が「物語の頂点」と書く
    第19機能（解消）。
    """
    definitions: List[Mapping[str, object]] = []
    parts: Dict[str, List[int]] = {part: [] for part in PARTS}
    last = len(keys)
    for index, key in enumerate(keys, start=1):
        function = BY_KEY[key]
        role: Optional[str] = None
        if function.number == 19:
            role = ROLE_PEAK
        elif index in (1, last):
            role = ROLE_WIDE
        definitions.append({
            "stage": index,
            "name": function.name_ja,
            "act": function.act,
            "description": function.description_ja,
            "role": role,
            "propp_function": function.key,
        })
        parts[function.part].append(index)
    return tuple(definitions), {part: tuple(numbers) for part, numbers in parts.items()}


ALL_KEYS: Tuple[str, ...] = tuple(item.key for item in FUNCTIONS if item.key != "8a")
