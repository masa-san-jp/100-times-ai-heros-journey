# 100 Times AI Hero's Journey

AIを活用してヒーローズ・ジャーニーの物語構造に基づいた物語を自動生成するGoogle Colabノートブックです。

## 概要

このプロジェクトは、Joseph・キャンベルの「ヒーローズ・ジャーニー（英雄の旅）」理論に基づき、OpenAI APIを使用して物語を自動生成するシステムです。作家のナラティブや世界観設定を入力として、12段階の物語構造に沿った完全な物語プロットを生成します。

## 主な機能

### 1. AI統合
- OpenAI API（o3-mini、GPT-4o-miniなど）を使用した物語生成
- JSON形式でのデータ構造化
- カスタマイズ可能なreasoning effort設定

### 2. 物語構造生成
ヒーローズ・ジャーニーの12段階に基づいた物語構造：
1. 日常世界
2. 冒険への呼びかけ
3. 拒否
4. 師との出会い
5. 第一関門の突破
6. 試練、仲間、敵
7. 最大の試練
8. 報酬
9. 帰路
10. 復活
11. 宝を持ち帰る

### 3. キャラクター生成
以下のキャラクタータイプを自動生成：
- **主人公（Protagonist）**: 物語の中心人物
- **援助者（Supporter）**: 主人公をサポートする人物
- **使者（Messenger）**: 主人公に冒険を促す人物
- **敵対者（Adversary）**: 主人公と対立する人物

### 4. 世界観設定
以下の要素を含む詳細な世界観を構築：
- 日常世界の描写
- 非日常世界の設定
- 社会構造
- 組織体
- 生活風習
- 人々の価値観

### 5. データ管理
- Google Spreadsheetsとの統合
- 生成したデータの自動保存
- Markdown形式での出力

## 使用方法

### 必要条件
- Google Colab環境
- OpenAI APIキー
- Google Sheetsへのアクセス権限（オプション）

### セットアップ

1. **依存関係のインストール**
```python
!pip install openai==0.28
```

2. **APIキーの設定**
```python
openai.api_key = "your-api-key-here"
```

3. **基本設定の入力**
作家のナラティブとして以下の項目を入力：
- 自己紹介
- 欠けているもの
- 物語のキーワード

### 実行フロー

1. **初期設定**
   - ライブラリのインポート
   - API認証
   - ヘルパー関数の定義

2. **作家のナラティブ入力**
   - 自分の特徴や価値観を記述
   - 現在の課題や欠落感を表現
   - 物語のテーマとなるキーワードを設定

3. **主人公の生成**
   - AIが作家のナラティブに基づいて主人公を創造
   - 性格、背景、目標などを詳細に設定

4. **サポートキャラクターの生成**
   - 援助者、使者、敵対者を自動生成
   - それぞれのキャラクターの役割と特徴を定義

5. **世界観の構築**
   - 日常世界と非日常世界の設定
   - 社会構造や文化の詳細化

6. **プロット骨子の生成**
   - A～Eパートに分けて物語の骨子を作成
   - 各パートで重要なイベントや転換点を設定

7. **最終プロットの生成**
   - すべての要素を統合
   - 12段階の物語構造に沿った完全なプロットを生成

## ヘルパー関数

### `ai(prompt, model="o3-mini")`
OpenAI APIを使用してテキストを生成します。

**パラメータ:**
- `prompt`: AIへの指示文
- `model`: 使用するモデル（デフォルト: o3-mini）

**戻り値:** 生成されたテキスト

### `ai_list(prompt, model="o3-mini")`
JSON形式でデータを生成します。

**パラメータ:**
- `prompt`: AIへの指示文
- `model`: 使用するモデル

**戻り値:** JSON形式のデータ（辞書型）

### `show(data)`
データをMarkdown形式で美しく表示します。

### `rich_print(markdown_text)`
Markdown形式のテキストをレンダリングして表示します。

## Google Sheets統合

生成したデータをGoogle Sheetsに保存できます：

```python
import gspread
from google.auth import default
from google.colab import auth

auth.authenticate_user()
creds, _ = default()
gc = gspread.authorize(creds)

# スプレッドシートを開く
sheet_url = 'your-sheet-url'
spreadsheet = gc.open_by_url(sheet_url)
worksheet = spreadsheet.worksheet('test')
```

## カスタマイズ

### モデルの変更
異なるAIモデルを使用する場合：

```python
# GPT-4o-miniを使用
result = ai("プロンプト", model="gpt-4o-mini")

# DeepSeek APIを使用する場合（コメントアウトを解除）
# openai.api_base = "https://api.deepseek.com"
# openai.api_key = "your-deepseek-key"
```

### Reasoning Effortの調整
o3-miniモデルのreasoning effortを変更：
- `"low"`: 高速だが精度は低い
- `"medium"`: バランス型（デフォルト）
- `"high"`: 高精度だが時間がかかる

## 注意事項

⚠️ **セキュリティ**
- APIキーは環境変数として管理することを推奨します
- ノートブックを公開する前に、APIキーを削除してください

⚠️ **コスト**
- OpenAI APIの使用には料金が発生します
- 特にo3-miniモデルは高reasoning effortで高額になる可能性があります

⚠️ **データ管理**
- Google Sheetsに保存する場合は適切なアクセス権限を設定してください

## ライセンス

MIT License

## 貢献

プルリクエストを歓迎します。大きな変更の場合は、まずissueを開いて変更内容を議論してください。

## 作者

masa-jp-art

## ローカル版開発（Ollama + gpt-oss:20b）

### 概要

完全にローカル環境で動作するバージョンです。Ollamaとgpt-oss:20bモデルを使用することで、外部APIに依存せず、プライバシーを保ちながら物語を生成できます。

### モデル選択ガイド

ローカル版では目的・マシンスペックに応じてモデルを選択できます。

| モデル | 種別 | 推奨メモリ | 用途 |
|---|---|---|---|
| **`gpt-oss:20b`** | 標準（**デフォルト**） | 約15GB | バランス重視・推奨 |
| `gpt-oss:20b-q8_0` | 量子化版 (Q8) | 約12GB | ほぼ同等品質・省メモリ |
| `gpt-oss:20b-q5_K_M` | 量子化版 (Q5) | 約8GB | バランス型 |
| `gpt-oss:20b-q4_K_M` | 量子化版 (Q4) | 約7GB | メモリ効率重視 |
| `gpt-oss:20b-q4_0` | 量子化版 (Q4) | 約6GB | 最小メモリ構成 |
| `gpt-oss:120b` | 高性能 | 約80GB以上 | 最高品質・高スペック機向け |
| `gpt-oss:120b-q4_K_M` | 高性能量子化版 | 約45GB | 省メモリ高性能版 |

> **量子化版について**: Q数が低いほどメモリ使用量は小さくなりますが、生成品質はやや低下します。RAM が16GB未満の場合は `q4_K_M` や `q4_0` をお試しください。

> **`gpt-oss:120b` について**: より高精度な物語生成が必要な高スペックマシン（64GB RAM 以上推奨）向けです。デフォルトは引き続き `gpt-oss:20b` です。

モデルを変更するには `OllamaConfig` の `model=` 引数を指定します:

```python
from src.ollama_client import OllamaConfig, AVAILABLE_MODELS

# 量子化版を使用（メモリ節約）
config = OllamaConfig(model="gpt-oss:20b-q4_K_M")

# 高性能マシン向け
config = OllamaConfig(model="gpt-oss:120b")

# 利用可能なモデル一覧を確認
print(AVAILABLE_MODELS)
```

### 出力ディレクトリ構造

何度も実行してアイデアを探索するプロジェクト用途を想定し、実行ごとに一意のディレクトリへ出力を保存します。

```
output/
├── run_20250315_120530/       ← 1回目の実行
│   ├── 20250315_120530_タイトル.md   （物語）
│   └── narrative_analysis.md         （ナラティブ分析）
├── run_20250315_145200/       ← 2回目の実行
│   ├── 20250315_145200_タイトル.md
│   └── narrative_analysis.md
└── ...
```

`save_run()` メソッドを使うと、物語と分析結果が同じ実行ディレクトリに一括保存されます:

```python
run_dir = generator.save_run(story)
print(f"保存先: {run_dir}/")
```

従来の `save_story()` / `save_analysis()` も引き続き利用できます（後方互換性あり）。

### 開発ハーネスの使用方法

開発ハーネスは、ローカル版を安全に開発・テストするためのツールセットです。

#### 1. 前提条件

```bash
# Ollamaのインストール（macOS）
brew install ollama

# gpt-oss:20bモデルのダウンロード
ollama pull gpt-oss:20b

# Ollamaサーバーの起動
ollama serve
```

#### 2. 依存関係のインストール

```bash
cd harness
pip install -r requirements.txt
```

#### 3. テストの実行

```bash
# すべてのテストを実行
python3 run_all_tests.py

# または、個別にテストを実行
python3 01_test_ollama_connection.py
python3 02_test_narrative_analysis.py
python3 03_test_character_generation.py
```

#### 4. テスト結果の確認

```bash
# ログファイルを確認
cat harness/logs/connection_test.log
cat harness/logs/narrative_analysis_test.log

# 生成されたテスト出力を確認
ls -la harness/test_output/
```

#### 5. 本番実装の使用

```bash
# 依存関係のインストール
pip install -r requirements.txt

# 使用例の実行
python3 example.py
```

**コード例:**

```python
from src.ollama_client import OllamaConfig
from src.narrative_analyzer import NarrativeInput
from src.story_generator import StoryGenerator

# ナラティブ入力を準備
narrative = NarrativeInput(
    author="あなたの自己紹介",
    missing="欠けているもの",
    status="現在の状態",
    # ... 他の項目
)

# 物語生成
generator = StoryGenerator()
story = generator.generate(narrative, plot_type="旅 (Quest)")

# 実行ごとのディレクトリに保存（output/run_YYYYMMDD_HHMMSS/ が自動作成されます）
run_dir = generator.save_run(story)
print(f"保存先: {run_dir}/")
```

### ドキュメント

- [ローカル版設計仕様書](docs/design-spec-local.md) - 詳細な設計仕様
- [開発ハーネスREADME](harness/README.md) - ハーネスの詳細な使い方

### 開発状況

- [x] 設計仕様書作成
- [x] 開発ハーネス作成
- [x] Ollama接続テスト
- [x] ナラティブ分析テスト
- [x] キャラクター生成テスト
- [x] プロット生成テスト
- [x] 物語執筆テスト
- [x] 本番実装（src/ディレクトリ）
- [ ] 統合テスト
- [ ] Jupyter Notebook作成

### 注意事項

⚠️ **開発ファイル**: `harness/` ディレクトリの内容はGitHubにアップロードされません（`.gitignore`で除外設定済み）

⚠️ **ハードウェア要件**:
- CPU: 8コア以上推奨（Apple M1/M2 推奨）
- メモリ: 32GB以上推奨（gpt-oss:20b 標準版）、量子化版 (q4_K_M) は 16GB でも動作可能
- ストレージ: 20GB以上（モデル用）
- **gpt-oss:120b を使用する場合**: 64GB RAM 以上を推奨

⚠️ **処理時間**: gpt-oss:20bは大規模モデルのため、CPU推論では処理に時間がかかります。

## 参考文献

- Joseph Campbell『千の顔をもつ英雄』
- Christopher Vogler『The Writer's Journey: Mythic Structure for Writers』
- [Ollama 公式ドキュメント](https://ollama.com/)
