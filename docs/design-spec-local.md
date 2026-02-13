# 100 Times AI Hero's Journey — ローカル版設計仕様書

**バージョン:** 2.0 (Local Edition)
**作成日:** 2026-02-14
**ベースバージョン:** 1.0 (Cloud Edition)
**著者:** masa-jp-art

---

## 目次

1. [プロジェクト概要](#1-プロジェクト概要)
2. [システムアーキテクチャ](#2-システムアーキテクチャ)
3. [技術スタック](#3-技術スタック)
4. [環境セットアップ](#4-環境セットアップ)
5. [データフロー（処理パイプライン）](#5-データフロー処理パイプライン)
6. [入力仕様](#6-入力仕様)
7. [コア関数定義](#7-コア関数定義)
8. [AIモデル構成（Ollama）](#8-aiモデル構成ollama)
9. [ナラティブ分析フェーズ](#9-ナラティブ分析フェーズ)
10. [キャラクター生成システム](#10-キャラクター生成システム)
11. [プロット要素生成](#11-プロット要素生成)
12. [ヒーローズ・ジャーニー物語構造定義](#12-ヒーローズジャーニー物語構造定義)
13. [世界観構築システム](#13-世界観構築システム)
14. [プロット骨子生成（A〜Eパート）](#14-プロット骨子生成aeパート)
15. [統合プロット生成](#15-統合プロット生成)
16. [物語執筆システム](#16-物語執筆システム)
17. [ビジュアルプロンプト生成](#17-ビジュアルプロンプト生成)
18. [データ永続化（ローカルストレージ）](#18-データ永続化ローカルストレージ)
19. [出力仕様](#19-出力仕様)
20. [実装構成一覧](#20-実装構成一覧)
21. [クラウド版との差異](#21-クラウド版との差異)
22. [パフォーマンス考慮事項](#22-パフォーマンス考慮事項)
23. [今後の拡張性](#23-今後の拡張性)

---

## 1. プロジェクト概要

### 1.1 目的

本プロジェクトは、クラウドベースのAIサービス（OpenAI、Anthropic Claude）に依存せず、**完全にローカル環境で動作する**物語自動生成システムである。

Joseph Campbell の「ヒーローズ・ジャーニー（英雄の旅）」理論に基づき、作家の個人的なナラティブ（自己物語）を**Ollama + gpt-oss:20b**で分析・変換し、12段階の物語構造に沿った完全なフィクション作品を自動生成する。

### 1.2 基本コンセプト

- **入力:** 作家自身の内面（願望・欠落・葛藤・記憶など）を構造化した自己ナラティブ
- **処理:** Ollama (gpt-oss:20b) による分析→要素生成→キャラクター創造→プロット構築→物語執筆
- **出力:** 10章構成の完全な小説原稿、キャラクタープロフィール、世界観設定、ビジュアルプロンプト

### 1.3 ローカル版の設計思想

1. **プライバシー第一**: すべてのデータと処理がローカルマシン内で完結
2. **外部依存ゼロ**: インターネット接続不要（初回モデルダウンロード後）
3. **コスト削減**: APIコストゼロ、従量課金なし
4. **オフライン動作**: ネットワーク障害時でも動作継続
5. **カスタマイズ性**: モデルパラメータの自由な調整、プロンプトエンジニアリングの完全制御

---

## 2. システムアーキテクチャ

### 2.1 実行環境

```
ローカルマシン
  └── Python 3.10+ 環境
       ├── Ollama サーバー (localhost:11434)
       │    └── gpt-oss:20b モデル
       ├── Jupyter Notebook / Lab（UI）
       ├── または Python スクリプト（CLI）
       └── ローカルファイルシステム（データ永続化）
            ├── output/
            │    ├── stories/        ← 生成された物語
            │    ├── characters/     ← キャラクタープロフィール
            │    ├── plots/          ← プロット情報
            │    └── analysis/       ← ナラティブ分析結果
            └── data/
                 └── story_data.db   ← SQLite データベース（オプション）
```

### 2.2 処理フロー全体像

```
┌─────────────────────────────────────────────────────────────────┐
│                    作家のナラティブ入力                           │
│  (author, missing, status, memories, mission, success,         │
│   loss, taboo, inhibit, daily, change, acceptance, desire)     │
└────────────────────────────┬────────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│              Phase 1: ナラティブ分析                             │
│  ① 願望分析 (analysis_desire)                                   │
│  ② 抑圧分析 (analysis_suppression)                              │
│  ③ 葛藤分析 (analysis_conflict)                                 │
│                                                                 │
│  [Ollama API: gpt-oss:20b]                                     │
└────────────────────────────┬────────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│              Phase 2: 要素生成                                   │
│  ④ ナラティブ要素の抽出 (narrative: 10要素)                      │
│  ⑤ キャラクター願望リスト (wants: 100個)                         │
│  ⑥ キャラクター能力リスト (abilities: 100個)                     │
│  ⑦ キャラクター課題リスト (roles: 100個)                         │
│  ⑧ プロット形式分類 (plot_list)                                  │
│                                                                 │
│  [Ollama API: gpt-oss:20b + JSON mode]                        │
└────────────────────────────┬────────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│              Phase 3: キャラクター＆プロット生成（×100ループ）    │
│  ⑨  主人公生成 (prompt_protagonist)                              │
│  ⑩  使者生成 (prompt_messenger)                                  │
│  ⑪  援助者生成 (prompt_supporter)                                │
│  ⑫  敵対者生成 (prompt_adversary)                                │
│  ⑬  10章プロット生成 (plot)                                      │
│                                                                 │
│  [Ollama API: gpt-oss:20b]                                     │
└────────────────────────────┬────────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│              Phase 4: 物語執筆                                   │
│  ⑭  各章の執筆 (gpt-oss:20b)                                    │
│  ⑮  作品タイトル生成                                             │
│                                                                 │
│  [Ollama API: gpt-oss:20b + 高temperature設定]                │
└────────────────────────────┬────────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│              Phase 5: 付随要素生成                                │
│  ⑯  ビジュアルプロンプト生成（4キャラクター分）                  │
│  ⑰  物語世界の生成                                               │
│  ⑱  プロット骨子生成（A〜Eパート）                               │
│  ⑲  統合プロット生成                                             │
│                                                                 │
│  [Ollama API: gpt-oss:20b]                                     │
└────────────────────────────┬────────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│              Phase 6: データ保存                                 │
│  - Markdown形式の完全な小説原稿 → output/stories/              │
│  - キャラクタープロフィール → output/characters/                │
│  - プロット情報 → output/plots/                                 │
│  - 分析結果 → output/analysis/                                  │
│  - メタデータ → data/story_data.db（SQLite）                    │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. 技術スタック

| コンポーネント | 技術 | バージョン / 備考 |
|---|---|---|
| **実行環境** | ローカルマシン | macOS / Linux / Windows |
| **言語** | Python | 3.10 以上 |
| **LLM サーバー** | **Ollama** | 最新版 |
| **LLM モデル** | **gpt-oss:20b** | Ollama経由でローカル実行 |
| **API クライアント** | `requests` または `ollama-python` | HTTP API / Python SDK |
| **データ形式** | JSON | `json` 標準ライブラリ |
| **データベース（オプション）** | SQLite | `sqlite3` 標準ライブラリ |
| **ノートブック** | Jupyter Notebook / Lab | ローカル実行 |
| **表示** | `IPython.display` | `Markdown` レンダリング |
| **ランダム化** | `random` | 標準ライブラリ |
| **ファイルI/O** | `pathlib`, `json` | 標準ライブラリ |

### 3.1 依存関係インストール

```bash
# Ollama のインストール（macOS / Linux）
curl -fsSL https://ollama.com/install.sh | sh

# または Homebrew（macOS）
brew install ollama

# gpt-oss:20b モデルのダウンロード
ollama pull gpt-oss:20b

# Python 依存関係
pip install requests
pip install jupyter notebook
pip install ipython

# オプション: Ollama Python SDK
pip install ollama
```

---

## 4. 環境セットアップ

### 4.1 Ollama サーバーの起動

```bash
# Ollamaサーバーをバックグラウンドで起動
ollama serve

# または、システムサービスとして自動起動設定
# macOS (Homebrew)
brew services start ollama

# Linux (systemd)
sudo systemctl enable ollama
sudo systemctl start ollama
```

デフォルトでは `http://localhost:11434` でAPIサーバーが起動する。

### 4.2 モデルの確認

```bash
# インストール済みモデルの確認
ollama list

# gpt-oss:20b の動作確認
ollama run gpt-oss:20b "こんにちは"
```

### 4.3 ディレクトリ構造の作成

```bash
mkdir -p output/{stories,characters,plots,analysis}
mkdir -p data
```

---

## 5. データフロー（処理パイプライン）

```
入力（作家の自己ナラティブ 13項目）
    │
    ├──→ ollama_chat() ──→ analysis_desire（願望分析レポート 400字）
    ├──→ ollama_chat() ──→ analysis_suppression（抑圧分析レポート 400字）
    ├──→ ollama_chat() ──→ analysis_conflict（葛藤分析レポート 400字）
    │
    ├──→ ollama_json() ──→ narrative（ナラティブ要素 10個 / JSON配列）
    │
    ├──→ ollama_json() ──→ wants（キャラクター願望 100個 / JSON配列）
    ├──→ ollama_json() ──→ abilities（キャラクター能力 100個 / JSON配列）
    ├──→ ollama_json() ──→ roles（キャラクター課題 100個 / JSON配列）
    │
    ├──→ ollama_json() ──→ plot_list（プロット形式分類 / JSON配列）
    │
    └──→ ループ（最大100回）
         ├── rand_choice() で要素をランダム選択
         ├──→ ollama_chat() ──→ prompt_protagonist（主人公プロフィール 400字）
         ├──→ ollama_chat() ──→ prompt_messenger（使者プロフィール 200字）
         ├──→ ollama_chat() ──→ prompt_supporter（援助者プロフィール 200字）
         ├──→ ollama_chat() ──→ prompt_adversary（敵対者プロフィール 200字）
         └──→ ollama_chat() ──→ plot（10章構成プロット）
              │
              ├──→ ollama_chat() ──→ story（各章 最大4000字 × 10章）
              └──→ ollama_chat() ──→ title（作品タイトル）
```

---

## 6. 入力仕様

**変更なし**。クラウド版の入力仕様（13項目の作家ナラティブ）をそのまま使用する。

詳細は[クラウド版 設計仕様書 §5](./design-specification.md#5-入力仕様)を参照。

---

## 7. コア関数定義

### 7.1 `ollama_chat(prompt, system="", model="gpt-oss:20b", temperature=0.7)` — テキスト生成

Ollama APIを使用してテキストを生成する。

```python
def ollama_chat(prompt, system="", model="gpt-oss:20b", temperature=0.7):
    """
    Ollama API を使用してテキストを生成

    Args:
        prompt (str): ユーザープロンプト
        system (str): システムプロンプト（オプション）
        model (str): 使用モデル（デフォルト: gpt-oss:20b）
        temperature (float): 生成の創造性（0.0〜2.0）

    Returns:
        str: 生成されたテキスト
    """
    import requests

    url = "http://localhost:11434/api/chat"

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "stream": False
    }

    try:
        response = requests.post(url, json=payload, timeout=300)
        response.raise_for_status()
        return response.json()["message"]["content"]
    except Exception as e:
        return f"エラーが発生しました: {e}"
```

### 7.2 `ollama_json(prompt, model="gpt-oss:20b")` — JSON構造化データ生成

Ollama APIを使用してJSON形式の構造化データを生成する。

```python
def ollama_json(prompt, model="gpt-oss:20b"):
    """
    Ollama API を使用してJSON形式のデータを生成

    Args:
        prompt (str): ユーザープロンプト
        model (str): 使用モデル

    Returns:
        dict: JSON形式のデータ（辞書型）
    """
    import requests
    import json

    url = "http://localhost:11434/api/chat"

    system_prompt = "常にJSON形式で応答してください。出力はJSONのみで、説明文は含めないでください。"
    user_prompt = f"{prompt}\n\nJSON形式で答えてください。"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.3,  # JSON生成は低めのtemperatureで
        "stream": False,
        "format": "json"  # Ollama の JSON mode
    }

    try:
        response = requests.post(url, json=payload, timeout=300)
        response.raise_for_status()
        content = response.json()["message"]["content"]
        return json.loads(content)
    except Exception as e:
        print(f"エラーが発生しました: {e}")
        return {}
```

### 7.3 ユーティリティ関数

クラウド版と同じユーティリティ関数を使用：

| 関数 | 入力 | 出力 | 説明 |
|---|---|---|---|
| `show(data)` | `dict` / `list` | 表示 | データをMarkdown形式に変換して表示 |
| `rich_print(m)` | `str` | 表示 | Markdownテキストをレンダリング表示 |
| `data_to_markdown(data, indent=0)` | `dict` / `list` | `str` | データ構造を再帰的にMarkdownリスト形式の文字列に変換 |
| `rand(n)` | `int` | `int` | 0〜nのランダム整数を返す |
| `rand_choice(li)` | `list` | `any` | リストからランダムに1要素を選択して返す |

### 7.4 ファイル保存関数

```python
import json
from pathlib import Path
from datetime import datetime

def save_story(title, content, metadata=None):
    """物語をMarkdown形式で保存"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{title}.md"
    filepath = Path("output/stories") / filename

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    if metadata:
        json_path = filepath.with_suffix(".json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

    return filepath

def save_json(data, category, filename):
    """JSON形式でデータを保存"""
    filepath = Path(f"output/{category}") / f"{filename}.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return filepath
```

---

## 8. AIモデル構成（Ollama）

### 8.1 モデル情報

| モデル | プロバイダ | パラメータ数 | 用途 |
|---|---|---|---|
| **gpt-oss:20b** | Ollama | 20B | すべてのタスク（分析、構造化、執筆） |

### 8.2 モデル設定

```python
# デフォルト設定
DEFAULT_MODEL = "gpt-oss:20b"
OLLAMA_BASE_URL = "http://localhost:11434"

# タスク別 temperature 設定
TEMPERATURE_CONFIG = {
    "analysis": 0.5,        # 分析タスク（安定性重視）
    "structure": 0.3,       # JSON構造化（精度重視）
    "character": 0.7,       # キャラクター生成（バランス）
    "plot": 0.7,           # プロット生成（バランス）
    "writing": 1.0,        # 文学的執筆（創造性重視）
}
```

### 8.3 モデル選択ガイドライン

ローカル版では単一モデル（gpt-oss:20b）ですべてのタスクを処理する。
タスクに応じて **temperature パラメータ** を調整することで、出力の性質を制御する：

- **分析・構造化 (temperature=0.3-0.5)**: 安定性と精度を重視
- **キャラクター・プロット生成 (temperature=0.7)**: バランス型
- **文学的執筆 (temperature=1.0)**: 創造性を最大化

### 8.4 Ollama API エンドポイント

| エンドポイント | 用途 |
|---|---|
| `POST /api/chat` | チャット形式でテキスト生成 |
| `POST /api/generate` | プロンプト完成形式で生成 |
| `GET /api/tags` | インストール済みモデル一覧 |

---

## 9. ナラティブ分析フェーズ

**変更点**: API呼び出し関数が `ai()` から `ollama_chat()` に変更。

### 9.1 願望分析 (`analysis_desire`)

```python
prompt = f"""以下の資料を網羅的に分析して、この作家が切望していること、
手に入れたいと渇望していることについて、400文字程度でレポートしてください。

{narrative_input}"""

analysis_desire = ollama_chat(
    prompt=prompt,
    system="あなたは深層心理学の専門家です。",
    temperature=TEMPERATURE_CONFIG["analysis"]
)
```

### 9.2 抑圧分析 (`analysis_suppression`)

```python
prompt = f"""以下の資料を網羅的に分析して、この作家が抑圧している根源的な
感情について、400文字程度でレポートしてください。

{narrative_input}"""

analysis_suppression = ollama_chat(
    prompt=prompt,
    system="あなたは深層心理学の専門家です。",
    temperature=TEMPERATURE_CONFIG["analysis"]
)
```

### 9.3 葛藤分析 (`analysis_conflict`)

```python
prompt = f"""以下の資料を網羅的に分析して、この作家が抱えている自己矛盾と
葛藤について、400文字程度でレポートしてください。

{narrative_input}"""

analysis_conflict = ollama_chat(
    prompt=prompt,
    system="あなたは深層心理学の専門家です。",
    temperature=TEMPERATURE_CONFIG["analysis"]
)
```

### 9.4 ナラティブ要素抽出 (`narrative`)

```python
prompt = f"""以下の資料を分析して、作家の備えている特有のナラティブを形成する
要素を抽象化して、10個に分類してリストnarrativeに格納してください。

分析資料:
- 願望分析: {analysis_desire}
- 抑圧分析: {analysis_suppression}
- 葛藤分析: {analysis_conflict}

出力形式: {{"narrative": ["要素1", "要素2", ..., "要素10"]}}"""

narrative_data = ollama_json(
    prompt=prompt,
    model=DEFAULT_MODEL
)
narrative = narrative_data.get("narrative", [])
```

---

## 10. キャラクター生成システム

**変更点**: API呼び出し関数が `ai_list()` から `ollama_json()` に変更。

### 10.1 キャラクター要素プール生成

```python
# 願望リスト生成
prompt = f"""以下のナラティブから、キャラクターが心の中に持っている願望を100個生成してください。

{narrative_input}

出力形式: {{"wants": ["願望1", "願望2", ..., "願望100"]}}"""

wants_data = ollama_json(prompt, model=DEFAULT_MODEL)
wants = wants_data.get("wants", [])

# 能力リスト生成
prompt = f"""以下のナラティブから、キャラクターが秘めている特有の能力を100個生成してください。

{narrative_input}

出力形式: {{"abilities": ["能力1", "能力2", ..., "能力100"]}}"""

abilities_data = ollama_json(prompt, model=DEFAULT_MODEL)
abilities = abilities_data.get("abilities", [])

# 課題リスト生成
prompt = f"""以下のナラティブから、キャラクターが抱えている課題を100個生成してください。

{narrative_input}

出力形式: {{"roles": ["課題1", "課題2", ..., "課題100"]}}"""

roles_data = ollama_json(prompt, model=DEFAULT_MODEL)
roles = roles_data.get("roles", [])
```

### 10.2 キャラクター生成（主人公）

```python
selected_plot = rand_choice(plot_list)
selected_narrative = rand_choice(narrative)
selected_want = rand_choice(wants)
selected_ability = rand_choice(abilities)
selected_role = rand_choice(roles)

prompt = f"""以下の要素を基に、主人公のキャラクタープロフィールを400文字程度で作成してください。
名前も付けてください。

- 物語の構造: {selected_plot}
- 抑圧されている自己像: {selected_narrative}
- 内面の願望: {selected_want}
- 秘めた能力: {selected_ability}
- 個人的な課題: {selected_role}"""

prompt_protagonist = ollama_chat(
    prompt=prompt,
    system="あなたは優れた小説家です。",
    temperature=TEMPERATURE_CONFIG["character"]
)
```

### 10.3 キャラクター生成ループ

クラウド版と同じ100回ループ構造を使用。各ループで：
1. プロット形式をランダム選択
2. 各要素プールから1要素ずつランダム選択
3. 主人公生成（400字）
4. 使者・援助者・敵対者生成（各200字）
5. 10章構成プロット生成

---

## 11. プロット要素生成

**変更なし**。クラウド版と同じプロットタイプ一覧（21カテゴリ）を使用。

詳細は[クラウド版 設計仕様書 §10](./design-specification.md#10-プロット要素生成)を参照。

---

## 12. ヒーローズ・ジャーニー物語構造定義

**変更なし**。クラウド版と同じ11段階（または12段階）の物語構造を使用。

詳細は[クラウド版 設計仕様書 §11](./design-specification.md#11-ヒーローズジャーニー物語構造定義)を参照。

---

## 13. 世界観構築システム

**変更点**: API呼び出し関数が `ai()` から `ollama_chat()` に変更。

```python
prompt = f"""以下の作家のナラティブを基に、物語の世界観を構築してください。

作家情報: {author_info}

以下の要素を含めてください：
- 社会構造（発展の指向性、構造維持の仕組み、大きな課題、発展阻害要因）
- 組織体（組織が指向する理想像、構成要素、施設・設備、抱える課題）
- 生活風習（公共貢献と考えられる行動、重要視される文化・思想、軋轢・緊張）
- 人々（社会における役割、重要な行動指針、個人的な問題）"""

story_world = ollama_chat(
    prompt=prompt,
    system="あなたは世界観構築の専門家です。",
    temperature=TEMPERATURE_CONFIG["plot"]
)
```

---

## 14. プロット骨子生成（A〜Eパート）

**変更点**: API呼び出し関数を `ollama_chat()` に変更。

### 14.1 Aパート — 序章・日常から召喚へ

```python
prompt = f"""以下の要素を基に、物語のAパート（序章・日常から召喚へ）を生成してください。

キャラクター:
- 主人公: {protagonist}
- 使者: {messenger}

含めるべき要素:
- 日常の世界
- 非日常の世界
- 主人公が欠落させているもの
- 主人公の前に現れる予兆
- 主人公の元に訪れる使者
- 召喚を拒絶させる要素
- 主人公が使者からもらうもの"""

plot_part_a = ollama_chat(prompt, temperature=TEMPERATURE_CONFIG["plot"])
```

同様にB〜Eパートも生成。

---

## 15. 統合プロット生成

**変更点**: API呼び出し関数を `ollama_chat()` に変更。

```python
prompt = f"""以下の要素をすべて統合して、12段階のヒーローズ・ジャーニー構造に沿った
完全なプロットを生成してください。

【キャラクター】
- 主人公: {protagonist}
- 援助者: {supporter}
- 使者: {messenger}
- 敵対者: {adversary}

【物語世界】
{story_world}

【プロット骨子】
Aパート: {plot_part_a}
Bパート: {plot_part_b}
Cパート: {plot_part_c}
Dパート: {plot_part_d}
Eパート: {plot_part_e}

【物語の構成】
第一幕: 1.日常の世界 → 2.冒険への誘い → 3.冒険への拒絶 → 4.使者との出会い
第二幕: 5.第一関門突破 → 6.試練・仲間・敵対者 → 7.最も危険な場所への接近 → 8.最大の試練
第三幕: 9.報酬 → 10.帰路 → 11.復活 → 12.宝を持って帰還"""

integrated_plot = ollama_chat(
    prompt=prompt,
    system="あなたは物語構造の専門家です。",
    temperature=TEMPERATURE_CONFIG["plot"]
)
```

---

## 16. 物語執筆システム

### 16.1 執筆プロンプト（共通テンプレート）

```python
def write_chapter(chapter_num, plot, characters, max_chars=4000):
    """章を執筆"""
    prompt = f"""下記のプロット第{chapter_num}章を最大{max_chars}文字までの文量で執筆してください。

注意事項：
- 物語の全体構造を損なわないこと
- 各章のできごと、登場人物たちの感情や行動を具体的かつドラマチックに書くこと
- 具体的な出来事を省略することなく、目の前に物語世界が浮かんでくるような、
  ディティールの深い文学的な表現を常に意識すること
- 各章の見出しは、プロットのままではなく、各章の内容に応じた文学的な表現に改変すること

プロット：
{plot}

登場人物資料：
{characters}"""

    return ollama_chat(
        prompt=prompt,
        system="あなたは現代を代表する小説家です。",
        temperature=TEMPERATURE_CONFIG["writing"]
    )
```

### 16.2 10章執筆ループ

```python
story_chapters = []

for i in range(1, 11):
    print(f"第{i}章を執筆中...")
    chapter = write_chapter(
        chapter_num=i,
        plot=integrated_plot,
        characters=f"""
- 主人公: {protagonist}
- 使者: {messenger}
- 援助者: {supporter}
- 敵対者: {adversary}
        """,
        max_chars=4000
    )
    story_chapters.append(chapter)

    # 進捗保存（中断時の復旧用）
    save_json(
        {"chapter": i, "content": chapter},
        "stories",
        f"chapter_{i}_draft"
    )
```

### 16.3 タイトル生成

```python
prompt = f"""下記のプロットの作品名を提案してください。
文学的で印象に残るタイトルにしてください。

{integrated_plot}"""

title = ollama_chat(
    prompt=prompt,
    system="あなたは優れた小説家です。",
    temperature=TEMPERATURE_CONFIG["writing"]
)
```

---

## 17. ビジュアルプロンプト生成

**変更点**: 英語生成もgpt-oss:20bで対応。

```python
prompt = f"""下記の人物像から想定されるキャラクターの外見的特徴を
400文字程度の英文で説明してください。

人物像:
{character_profile}

画像生成AIで使用するため、具体的な外見描写（年齢、性別、髪型、服装、
体格、表情など）を英語で詳しく記述してください。"""

visual_prompt = ollama_chat(
    prompt=prompt,
    system="You are an expert at creating visual prompts for AI art generation.",
    temperature=0.7
)
```

---

## 18. データ永続化（ローカルストレージ）

### 18.1 ファイルシステムベースの保存

```python
import json
from pathlib import Path
from datetime import datetime

class StoryStorage:
    def __init__(self, base_dir="output"):
        self.base_dir = Path(base_dir)
        self.stories_dir = self.base_dir / "stories"
        self.characters_dir = self.base_dir / "characters"
        self.plots_dir = self.base_dir / "plots"
        self.analysis_dir = self.base_dir / "analysis"

        # ディレクトリ作成
        for dir_path in [self.stories_dir, self.characters_dir,
                         self.plots_dir, self.analysis_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)

    def save_story(self, title, chapters, metadata):
        """完成した物語を保存"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_'))

        # Markdown形式で保存
        md_path = self.stories_dir / f"{timestamp}_{safe_title}.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(f"# {title}\n\n")
            for i, chapter in enumerate(chapters, 1):
                f.write(f"## 第{i}章\n\n{chapter}\n\n")

        # メタデータをJSON形式で保存
        json_path = md_path.with_suffix(".json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

        return md_path

    def save_characters(self, story_id, characters):
        """キャラクター情報を保存"""
        path = self.characters_dir / f"{story_id}_characters.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(characters, f, ensure_ascii=False, indent=2)
        return path

    def save_plot(self, story_id, plot):
        """プロット情報を保存"""
        path = self.plots_dir / f"{story_id}_plot.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(plot, f, ensure_ascii=False, indent=2)
        return path

    def save_analysis(self, story_id, analysis):
        """ナラティブ分析を保存"""
        path = self.analysis_dir / f"{story_id}_analysis.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(analysis, f, ensure_ascii=False, indent=2)
        return path
```

### 18.2 SQLite データベース（オプション）

より高度なクエリやメタデータ管理が必要な場合、SQLiteを使用：

```python
import sqlite3
from datetime import datetime

class StoryDatabase:
    def __init__(self, db_path="data/story_data.db"):
        self.db_path = db_path
        self.init_database()

    def init_database(self):
        """データベーステーブルを初期化"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 物語メタデータテーブル
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS stories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            file_path TEXT,
            plot_type TEXT,
            word_count INTEGER
        )
        """)

        # キャラクターテーブル
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS characters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            story_id INTEGER,
            name TEXT,
            role TEXT,
            profile TEXT,
            FOREIGN KEY (story_id) REFERENCES stories(id)
        )
        """)

        # ナラティブ分析テーブル
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS analysis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            story_id INTEGER,
            analysis_type TEXT,
            content TEXT,
            FOREIGN KEY (story_id) REFERENCES stories(id)
        )
        """)

        conn.commit()
        conn.close()

    def insert_story(self, title, file_path, plot_type, word_count):
        """物語メタデータを挿入"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO stories (title, file_path, plot_type, word_count)
        VALUES (?, ?, ?, ?)
        """, (title, file_path, plot_type, word_count))
        story_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return story_id
```

---

## 19. 出力仕様

**変更なし**。クラウド版と同じ出力仕様を使用。

### 19.1 出力フォーマット

| 出力物 | フォーマット | 言語 | 文字数目安 | 保存先 |
|---|---|---|---|---|
| ナラティブ分析レポート（×3） | Markdown / JSON | 日本語 | 各400字 | `output/analysis/` |
| キャラクタープロフィール（×4） | JSON | 日本語 | 主人公400字、他200字 | `output/characters/` |
| 10章プロット | JSON / Markdown | 日本語 | 可変 | `output/plots/` |
| 物語本文（10章） | Markdown | 日本語 | 各章2,000〜4,000字 | `output/stories/` |
| 作品タイトル | テキスト | 日本語 | — | メタデータに含む |
| ビジュアルプロンプト（×4） | テキスト | 英語 | 各400字 | `output/characters/` |
| 世界観設定 | Markdown / JSON | 日本語 | 可変 | `output/plots/` |
| プロット骨子（A〜E） | JSON | 日本語 | 可変 | `output/plots/` |

---

## 20. 実装構成一覧

### 20.1 推奨ファイル構成

```
100-times-ai-heros-journey/
├── notebooks/
│   └── local_story_generator.ipynb    ← メインノートブック
├── src/
│   ├── __init__.py
│   ├── ollama_client.py               ← Ollama API クライアント
│   ├── story_generator.py             ← 物語生成コア
│   ├── character_generator.py         ← キャラクター生成
│   ├── plot_generator.py              ← プロット生成
│   └── storage.py                     ← データ永続化
├── output/
│   ├── stories/                       ← 生成された物語
│   ├── characters/                    ← キャラクター情報
│   ├── plots/                         ← プロット情報
│   └── analysis/                      ← ナラティブ分析
├── data/
│   └── story_data.db                  ← SQLite DB（オプション）
├── config/
│   └── settings.json                  ← 設定ファイル
├── requirements.txt                    ← Python依存関係
└── README.md

```

### 20.2 モジュール分割（推奨）

**`src/ollama_client.py`** — Ollama API クライアント
```python
class OllamaClient:
    def __init__(self, base_url="http://localhost:11434", model="gpt-oss:20b"):
        self.base_url = base_url
        self.model = model

    def chat(self, prompt, system="", temperature=0.7):
        """テキスト生成"""
        ...

    def json_chat(self, prompt, temperature=0.3):
        """JSON形式でデータ生成"""
        ...

    def check_connection(self):
        """接続確認"""
        ...
```

**`src/story_generator.py`** — 物語生成コア
```python
class StoryGenerator:
    def __init__(self, ollama_client, storage):
        self.client = ollama_client
        self.storage = storage

    def analyze_narrative(self, narrative_input):
        """ナラティブ分析"""
        ...

    def generate_elements(self, narrative_input):
        """要素プール生成"""
        ...

    def generate_story(self, characters, plot):
        """物語執筆"""
        ...
```

---

## 21. クラウド版との差異

| 項目 | クラウド版 | ローカル版 |
|---|---|---|
| **実行環境** | Google Colab | ローカルマシン（Jupyter / Python） |
| **AIモデル** | OpenAI (o3-mini)<br>Claude (claude-3-5-sonnet)<br>DeepSeek (deepseek-reasoner) | Ollama (gpt-oss:20b) のみ |
| **API呼び出し** | `ai()`, `claude()`, `dsr1()` | `ollama_chat()`, `ollama_json()` |
| **認証** | APIキー（環境変数 / ハードコード） | 不要（ローカル接続のみ） |
| **データ保存** | Google Sheets（オプション） | ローカルファイルシステム / SQLite |
| **依存関係** | `openai==0.28`, `anthropic` | `requests` / `ollama` |
| **インターネット接続** | 必須 | 不要（モデルDL後） |
| **コスト** | API従量課金 | ゼロ（電力コストのみ） |
| **プライバシー** | データは外部API送信 | すべてローカルで完結 |
| **処理速度** | APIレイテンシ依存 | ローカルGPU/CPUスペック依存 |

---

## 22. パフォーマンス考慮事項

### 22.1 推奨ハードウェア

| コンポーネント | 最小要件 | 推奨要件 |
|---|---|---|
| **CPU** | 4コア以上 | 8コア以上（Apple M1/M2 推奨） |
| **メモリ** | 16GB | 32GB以上 |
| **ストレージ** | 20GB（モデル用） | SSD 50GB以上 |
| **GPU** | なし（CPU推論可） | NVIDIA GPU 8GB VRAM以上 |

### 22.2 処理時間の見積もり

**gpt-oss:20b の推論速度（参考値）**:
- Apple M2 Max (CPU): 約 15-20 tokens/sec
- NVIDIA RTX 4090 (GPU): 約 50-80 tokens/sec

**100ループ + 10章執筆の総処理時間**:
- CPU推論: 約 8-12時間
- GPU推論: 約 2-4時間

### 22.3 最適化手法

1. **バッチ処理**: 複数プロンプトをまとめて処理（要実装）
2. **キャッシュ活用**: 共通プロンプトの結果をキャッシュ
3. **並列化**: 独立したタスク（キャラクター生成）を並列実行
4. **プログレッシブ生成**: 段階的に生成数を減らす（100→50→10）
5. **GPU利用**: 可能であればOllamaのGPU推論を有効化

```bash
# GPU推論の有効化（NVIDIA GPU）
CUDA_VISIBLE_DEVICES=0 ollama serve
```

---

## 23. 今後の拡張性

### 23.1 マルチモデル対応

将来的に複数のローカルモデルを使い分ける：
- **分析**: `mistral:7b-instruct`（軽量・高速）
- **執筆**: `gpt-oss:20b`（高品質）
- **構造化**: `llama3:70b`（大規模推論）

### 23.2 UI改善

- Gradio / Streamlit を使った Web UI
- リアルタイムプレビュー
- 生成プロセスの可視化

### 23.3 多言語対応

- 英語・中国語など他言語でのナラティブ入力
- 多言語物語生成

### 23.4 高度な永続化

- PostgreSQL / MongoDB などのデータベース統合
- バージョン管理システム（物語の履歴管理）

---

## 参考文献

- Joseph Campbell『千の顔をもつ英雄』（The Hero with a Thousand Faces）
- Christopher Vogler『The Writer's Journey: Mythic Structure for Writers』
- Ollama 公式ドキュメント: https://ollama.com/
- gpt-oss モデル情報: https://huggingface.co/gpt-oss

---

## 補足: Ollama API リファレンス

### Chat API

```bash
curl http://localhost:11434/api/chat -d '{
  "model": "gpt-oss:20b",
  "messages": [
    {"role": "system", "content": "You are a novelist."},
    {"role": "user", "content": "Write a story opening."}
  ],
  "temperature": 0.8,
  "stream": false
}'
```

### JSON Mode

```bash
curl http://localhost:11434/api/chat -d '{
  "model": "gpt-oss:20b",
  "messages": [
    {"role": "user", "content": "Generate 5 character names in JSON format"}
  ],
  "format": "json",
  "stream": false
}'
```

---

**ドキュメント作成日:** 2026-02-14
**次回レビュー予定:** 実装完了後
