# 100 Times AI Hero's Journey

作家の自己ナラティブから、ヒーローズ・ジャーニー形式の物語を生成するPython CLI/APIです。
標準ではOllama上のローカルモデルを使うため、入力と生成物を外部APIへ送らずに実行できます。

**目次**

- 概要: [目的とコンセプト](#目的とコンセプト) / [使い方の流れ](#使い方の流れ) / [兄弟リポジトリ](#兄弟リポジトリ)
- 使う: [まず動かす](#まず動かす) / [入力を変える](#入力を変える) / [繰り返し生成・途中再開](#繰り返し生成途中再開) / [生成後に振り返る](#生成後に振り返る)
- 詳しく: [CLIオプション](#cliオプション) / [モデルの選択](#モデルの選択) / [生成される工程](#生成される工程) / [ストーリーボードを作る](#ストーリーボードを作る) / [出力構成](#出力構成) / [Python API](#python-api) / [外部APIを使う場合](#外部apiを使う場合)
- 背景: [変遷](#変遷) / [開発・テスト](#開発テスト) / [制約と目安](#制約と目安) / [ライセンス](#ライセンス)

## 目的とコンセプト

[設計仕様書](docs/design-specification.md)より。

### 目的

Joseph Campbell の「ヒーローズ・ジャーニー（英雄の旅）」理論に基づき、作家の個人的なナラティブ（自己物語）をAIで分析・変換し、
12段階の物語構造に沿った完全なフィクション作品を自動生成する。

### 基本コンセプト

- **入力:** 作家自身の内面（願望・欠落・葛藤・記憶など）を構造化した自己ナラティブ
- **処理:** 複数のAIモデルによる分析→要素生成→キャラクター創造→プロット構築→物語執筆
- **出力:** 10章構成の完全な小説原稿、キャラクタープロフィール、世界観設定、ビジュアルプロンプト

### 設計思想

1. **作家の深層心理を物語に昇華する**: 入力された自己ナラティブからAIが願望・抑圧・葛藤を抽出し、キャラクターと物語に投影する
2. **ランダム性による多様性**: 生成要素の組み合わせにランダム選択を導入し、同一入力から最大100パターンの異なる物語を生成可能にする
3. **マルチモデル活用**: 各モデルの得意領域を活かす（Colab版では分析・構造化にOpenAI、文学的執筆にClaude、推論にDeepSeek。現在のローカル版はOllamaを標準とし、各クラウドプロバイダーも選択可能）

## 使い方の流れ

| 段階 | コマンド | 生成されるもの |
|---|---|---|
| 1. 入力を作る | `create_narrative.py` | 13項目の自己ナラティブ `narrative.json` |
| 2. 物語を生成する | `run_pipeline.py` | 分析・世界観・キャラクター・プロット・章本文・ビジュアルプロンプト |
| 3. 生成結果を集計する | `analyze_batch.py` | 作品一覧、要素の頻度表、LLMによる横断パターンと問い（`batch_report.md`） |
| 4. ストーリーボードを作る | `render_storyboard.py` | ショットリストと16:9画像（`storyboard/`） |

## 兄弟リポジトリ

AI創作の各工程に対応する関連リポジトリです。

- [100-times-ai-heroes](https://github.com/masa-san-jp/100-times-ai-heroes)：ローカルCSV、Ollama、ComfyUIを使って、キャラクター設定と全身画像を生成します。
- [100-times-ai-heros-journey](https://github.com/masa-san-jp/100-times-ai-heros-journey)（本リポジトリ）：自己ナラティブから、ヒーローズ・ジャーニー形式の物語を生成します。
- [100-times-ai-world-building](https://github.com/masa-san-jp/100-times-ai-world-building)：AIを活用した世界観構築ワークフローをJupyter Notebookで体験できます。
- [100-times-ai-manga-drawing](https://github.com/masa-san-jp/100-times-ai-manga-drawing)：生成AIを活用したマンガ作画の実験・制作ワークフローを扱います。

## まず動かす

### 必要なもの

- Python 3.10以上
- [Ollama](https://ollama.com/)
- 生成に使うOllamaモデル（未インストールの場合、CLIが明示指定モデルまたは既定モデルを自動取得します）

Python依存関係は `requests` のみです。テストも実行する場合は開発依存関係を入れます。
ストーリーボードシート（PNG）が必要な場合だけ、追加で `requirements-image.txt` を入れます。

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
# ストーリーボードシートも作る場合（任意）
python -m pip install -r requirements-image.txt
# テストも行う場合
python -m pip install -r requirements-dev.txt
```

Ollamaを起動したターミナルとは別のターミナルで、次を実行します。

```bash
ollama serve
```

最初は1作品・候補プール3件で動作を確認してください。完全版は既定で12段階・10章です。

```bash
python run_pipeline.py \
  --narrative-json narrative.example.json \
  --loops 1 \
  --pool-size 3 \
  --model gpt-oss:20b \
  --batch-id quickstart
```

完了すると、`output/batch_quickstart/` に分析、世界観、プロット、本文、メタデータが保存されます。
`gpt-oss:20b` が未インストールなら、CLIが `ollama pull gpt-oss:20b` を実行します。
既に別のモデルを使いたい場合は `--model` を変更してください。

## 入力を変える

13項目を対話形式で入力する場合は、次のコマンドを実行してください。回答はローカルのJSONに保存されます。

```bash
python create_narrative.py --out narrative.json
```

既存のJSONを編集する場合は `--from` を指定します。手書きでJSONを作成して `--narrative-json` に渡す方法も引き続き利用できます。

```bash
python create_narrative.py --from narrative.json --out narrative.json
```

`--narrative-json` には次の13項目を持つJSONを指定します。

`author`, `missing`, `status`, `memories`, `mission`, `success`, `loss`, `taboo`,
`inhibit`, `daily`, `change`, `acceptance`, `desire`

各値は文字列です。項目が欠けているJSONはサンプル値で補完されるため、
本番利用では13項目をすべて自分の内容に置き換えてください。

```json
{
  "author": "自己紹介",
  "missing": "自分に欠けていると感じるもの",
  "status": "現在の状態",
  "memories": "印象に残っている記憶",
  "mission": "果たしたい使命",
  "success": "成功のイメージ",
  "loss": "失うことが怖いもの",
  "taboo": "越えたくない境界",
  "inhibit": "自分を抑えているもの",
  "daily": "日常",
  "change": "変化のきっかけ",
  "acceptance": "受け入れられること／受け入れにくいこと",
  "desire": "本当の願望"
}
```

## 繰り返し生成・途中再開

`--loops N`（旧名 `--variations N`）が生成する完成作品数です。
`--pool-size` はキャラクター生成に使う願望・能力・課題の候補数で、作品数や章数ではありません。
100作品を生成する場合は、例えば次のように固定バッチ名を付けます。

```bash
python run_pipeline.py \
  --narrative-json narrative.example.json \
  --model gpt-oss:20b \
  --loops 100 \
  --pool-size 100 \
  --seed 42 \
  --batch-id experiment-01
```

処理を中断した場合は、同じナラティブJSONを指定して再開します。`--loops` はそのバッチの最終目標数です。
完了済みの `run_001` などはスキップされ、保存済みの準備データと章チェックポイントが再利用されます。

```bash
python run_pipeline.py \
  --narrative-json narrative.example.json \
  --model gpt-oss:20b \
  --loops 100 \
  --resume output/batch_experiment-01
```

同じ内容の作品はデフォルトで重複除外されます。重複を許可する場合は `--allow-duplicates` を指定します。
重複試行の上限は `--max-attempts N` で変更できます。

章本文は章ごとにチェックポイント保存されます。出力上限で章が切れた場合は、既定で最大2回続きを生成します。
この回数は `--max-chapter-continuations N` で変更できます。

## 生成後に振り返る

バッチ生成後は、作品群を横断した決定的集計と振り返りレポートを作成できます。
まずはLLMを使わず、完了済みrunの一覧と選択要素の頻度だけを確認できます。

```bash
python analyze_batch.py output/batch_experiment-01 --no-llm
```

LLMによる作品ごとの要約と横断解釈も行う場合は、生成時と同じプロバイダー・モデル指定を使えます。
作品ごとの要約は各 `run_XXX/cross_summary.json` にキャッシュされ、`--refresh` を付けたときだけ再生成されます。

```bash
python analyze_batch.py output/batch_experiment-01 \
  --provider ollama --model gpt-oss:20b --num-ctx 32768
```

`batch_report.md` は人が読むためのレポート、`batch_report.json` は同じ内容の機械可読版です。
未完了runは自動的にスキップされ、件数が概要に記載されます。レポートは傾向と該当作品を並べますが、
解釈を断定・診断せず、元ナラティブとの対応は問いの形で提示する設計です。`--num-ctx` はOllamaの
分析用コンテキスト長で、本文が推定入力上限を超える場合は冒頭と末尾を残して中略し、警告を表示します。

## ストーリーボードを作る

画像生成に必要な ComfyUI、Qwen Image 2.1、Viggle Turbo用カスタムノードは、次のコマンドで導入できます。
モデルを含めてディスクを約33GB使い、Qwen Research License（研究・評価目的に限る）の確認が必要です。

```bash
python setup_storyboard.py
```

既存の ComfyUI（100-times-ai-heroes で導入済みのものを含む）は、`--comfyui-dir` で指定できます。既存 venv の依存は変更せず、必要な場合だけ `--update-deps` で導入します。
モデルを後から導入する場合は `--skip-models`、予定だけ確認する場合は `--dry-run` を使います。
ComfyUI は画像生成時に未起動なら自動起動・終了されます。

### 出力例

作例「風の鼓音」（`gpt-oss:20b` で生成した10章の物語）から作った、全10コマのうちの4コマです。

<table>
<tr><td width="50%"><img src="examples/batch_full-gpt-oss-20b/run_001/storyboard/shot_01.png" alt="shot_01"><br><sub>第1章・大ロング　灰色の街並み</sub></td><td width="50%"><img src="examples/batch_full-gpt-oss-20b/run_001/storyboard/shot_04.png" alt="shot_04"><br><sub>第4章・ロング　夕暮れの石畳</sub></td></tr>
<tr><td width="50%"><img src="examples/batch_full-gpt-oss-20b/run_001/storyboard/shot_05.png" alt="shot_05"><br><sub>第5章・ミディアム　壁の鼓音</sub></td><td width="50%"><img src="examples/batch_full-gpt-oss-20b/run_001/storyboard/shot_07.png" alt="shot_07"><br><sub>第7章・クローズアップ　風の鼓音</sub></td></tr>
</table>

全10コマは [風の鼓音のストーリーボード](examples/batch_full-gpt-oss-20b/run_001/) で、章ごとの本文の引用とあわせて読めます。

### 使い方

```bash
python render_storyboard.py output/batch_experiment-01/run_001
python render_storyboard.py output/batch_experiment-01 --runs 1,3-5 --seed 42
```

ショットリストだけを作る場合は`--shots-only`、既存の`shots.json`から画像だけを作る場合は`--images-only`を使います。
ショットサイズは物語段階から決定的に割り当てられます。既存の`shots.json`を`--rebuild-prompts`で補正することもできますが、`setting` / `action`は旧サイズ前提のため、サイズに合わせた場面から作り直す場合は`--refresh-shots`を推奨します。
11段階版は、12段階版の「最も危険な場所への接近」を持たない既存の段階定義に対応し、`extreme_long, long, close_up, full, long, medium, close_up, full, long, close_up, extreme_long`の順で割り当てます。
`--shots-only`または画像生成の完了時には、画像一覧の`storyboard_sheet.png`とMarkdown形式の`storyboard.md`も出力されます。
シートの列数は`--sheet-columns N`（既定値2）で変更できます。Pillowを導入していない環境では、シートだけを警告付きでスキップし、`storyboard.md`は出力します。
`--force`を付けない限り、manifestの同じショットIDが成功済みで現在のpromptと一致する画像はスキップされるため、途中で中断しても同じコマンドを再実行できます。
`--character-refs`は`off` / `closeup` / `all`を指定できます。既定値は`closeup`で、`close_up`または`medium`のショットだけに参照画像を渡します。`all`は全ショット、`off`は参照なしです。値なしの`--character-refs`は後方互換のため`all`として扱います。参照を使うショットに登場するキャラクターだけの参照画像を`storyboard/characters/`に生成し、既存の参照画像は再利用します。`shot_size`がない旧`shots.json`のショットは参照なしとして扱います。
既定では参照画像の生成が走るため、参照画像1枚は約1〜2.7分です。#25の実測では、1ショットの生成時間は参照なし約59秒、1人参照約62秒、2人参照約83秒でした（モデル読み込みやマシンの状態により変動します）。参照workflowを持たないprofileでは、警告を表示して参照なしで続行します。
ComfyUIの接続先は環境変数`COMFYUI_URL`で変更でき、未設定時は`http://127.0.0.1:8188`です。
`--dry-run`は生成予定のショット数・プロンプト・推定時間を表示して終了します。`shots.json`がないrunでは、プロンプト表示のためLLMでショットリストを作成します。
既定profileは720×400（16:9）です。M4 Maxで `examples/batch_full-gpt-oss-20b/run_001` の10ショットを生成した実測では、ショットリスト生成（`gpt-oss:20b`）が約5分、画像が1枚約47〜85秒でした（モデル読み込み、プロンプトの長さ、マシンの状態により変動します）。

出力は各`run_XXX/storyboard/`に保存されます。

```text
storyboard/
├── shots.json
├── shots.md
├── characters/             # 参照画像を使うショットがあるとき（既定の closeup を含む）
├── shot_01.png ... shot_NN.png
├── storyboard_sheet.png
├── storyboard.md
└── render_manifest.json
```

セットアップ後の `.runtime/` には、ComfyUI本体、専用venv、`comfyui.json`、起動ログが保存されます。

`render_manifest.json`にはprofile、モデルファイル、解像度、各ショットのshot_size・参照使用有無・seed・prompt・所要秒数・成否・エラーが記録されます。

既定の画像モデルは `qwen-image-2.1-turbo`（Qwen-Image 2.1 + Viggle 6ステップLoRA）です。
ライセンスは [Qwen Research License Agreement](https://huggingface.co/Qwen/Qwen-Image-2.1/blob/main/LICENSE) で、利用目的は研究・評価に限られます。
モデルとライセンスの確認内容は兄弟リポジトリの [MODEL_LICENSES.md](https://github.com/masa-san-jp/100-times-ai-heroes/blob/main/docs/MODEL_LICENSES.md) にも記載しています。

## CLIオプション

| オプション | 既定値 | 用途 |
|---|---:|---|
| `--model NAME` | 自動選択 | Ollamaモデル。未導入なら自動取得 |
| `--provider NAME` | `ollama` | `ollama` / `openai` / `anthropic` / `deepseek` |
| `--loops N` | `1` | 完成作品の目標数 |
| `--pool-size N` | `100` | 願望・能力・課題の候補数 |
| `--journey-stages 11\|12` | `12` | ヒーローズ・ジャーニーの段階数 |
| `--chapter-count N` | `10` | 1作品の章数 |
| `--resume DIR` | なし | 既存バッチを途中再開 |
| `--batch-id NAME` | 自動生成 | `output/batch_NAME` として保存 |
| `--no-chapters` | 無効 | 章本文を生成せずプロットまで作成 |
| `--no-world` | 無効 | 世界観生成を省略 |
| `--no-skeleton` | 無効 | プロット骨子A〜Eを省略 |
| `--no-visual-prompts` | 無効 | ビジュアルプロンプトを省略 |
| `--allow-duplicates` | 無効 | 重複除外を無効化 |
| `--list-models` | 無効 | インストール済みOllamaモデルを表示 |
| `--timeout SEC` | `600` | 1回のLLMリクエストのタイムアウト |

全オプションは次で確認できます。

```bash
python run_pipeline.py --help
```

## モデルの選択

インストール済みモデルの一覧を確認できます。

```bash
python run_pipeline.py --list-models
```

`--model` を省略した場合の動作は次のとおりです。

1. Ollamaにインストール済みのモデルがあれば、それを選択する
2. 対話端末で複数ある場合は番号で選択する
3. `gpt-oss:20b` があれば優先する。なければ一覧の先頭を選ぶ
4. モデルが1つもなければ `gpt-oss:20b` を自動取得する

現在のマシンに入っているモデルは環境によって異なります。`qwen3.8:27b`、`gpt-oss:20b`、
`gemma4:e4b` など、Ollamaで利用できるモデル名を `--model` に指定できます。

## 生成される工程

完全版パイプラインは次の成果物を順に作ります。

1. ナラティブ分析（願望・抑圧・葛藤・10要素）
2. キャラクター用要素プール
3. プロット形式の分類
4. 物語世界
5. 主人公、使者、援助者、敵対者
6. プロット骨子A〜E
7. ヒーローズ・ジャーニーの11または12段階プロット
8. 指定章数の本文
9. タイトル
10. キャラクター別ビジュアルプロンプト
11. Markdown、JSON、チェックポイントの保存

標準の12段階は次のとおりです。

1. 日常世界
2. 冒険への呼びかけ
3. 拒否
4. 師との出会い
5. 第一関門の突破
6. 試練、仲間、敵
7. 最も危険な場所への接近
8. 最大の試練
9. 報酬
10. 帰路
11. 復活
12. 宝を持ち帰る

自動評価やランキング機能は現在実装していません。

## 出力構成

```text
output/
└── batch_<名前または日時>/
    ├── narrative.json
    ├── analysis.json
    ├── analysis.md
    ├── element_pools.json
    ├── plot_types.json
    ├── world.md
    ├── batch_manifest.json
    ├── batch_report.md          # analyze_batch.py 実行後
    ├── batch_report.json        # analyze_batch.py 実行後
    └── run_001/
        ├── <日時>_<タイトル>.md
        ├── metadata.json
        ├── narrative_analysis.md
        ├── world.md
        ├── plot_skeleton.md
        ├── visual_prompts.md
        ├── cross_summary.json   # analyze_batch.py(LLMあり)実行後
        └── storyboard/          # render_storyboard.py 実行後
            ├── shots.json
            ├── shots.md
            ├── shot_01.png ... shot_NN.png
            ├── storyboard_sheet.png
            ├── storyboard.md
            └── render_manifest.json
```

生成途中または失敗時には、`run_001/` に `draft.json`、`chapter_01.md`、
`chapter_progress.json` が追加されます。これらは再開に使われ、完成後は最終成果物へ整理されます。
`batch_manifest.json` には完了数、試行数、重複破棄数、設定、エラー内容が記録されます。

`output/` と `data/` は `.gitignore` で除外されています。共有用の完成作例は [examples/README.md](examples/README.md) を参照してください。

## Python API

CLIと同じ完全版パイプラインをPythonから呼び出せます。

```python
import json

from src.colab_pipeline import ColabParityPipeline, PipelineConfig
from src.narrative_analyzer import NarrativeInput
from src.ollama_client import OllamaConfig

with open("narrative.example.json", encoding="utf-8") as handle:
    narrative = NarrativeInput(**json.load(handle))

pipeline = ColabParityPipeline(
    ollama_config=OllamaConfig(model="gpt-oss:20b")
)
batch = pipeline.run(
    narrative,
    PipelineConfig(
        pool_size=3,
        variation_count=1,
        output_dir="output",
        random_seed=42,
    ),
)
print(batch.output_dir)
```

同じ処理をコードから試す短い例は [example.py](example.py) にあります。
低レベルの `StoryGenerator` は、分析済みの材料を個別に扱いたい場合に利用できます。
通常の一括生成、途中再開、重複除外には `ColabParityPipeline` を推奨します。

## 外部APIを使う場合

標準設定は外部APIを使わないOllamaです。クラウドプロバイダーを使う場合は、APIキーを環境変数に設定します。
CLI実装は追加SDKではなくHTTP経由で呼び出すため、`requirements.txt` のまま利用できます。

```bash
export OPENAI_API_KEY=...
python run_pipeline.py --provider openai --model o3-mini --loops 1

export ANTHROPIC_API_KEY=...
python run_pipeline.py --provider anthropic --model claude-3-5-sonnet-20241022 --loops 1

export DEEPSEEK_API_KEY=...
python run_pipeline.py --provider deepseek --model deepseek-reasoner --loops 1
```

API利用では入力が外部サービスへ送られ、サービスごとの料金・利用可能モデル・規約が適用されます。
APIキーをソースコードやナラティブJSONへ書かないでください。

Python APIでは、分析・プロット・執筆に異なるクライアントを指定することもできます。
Google Sheets保存用の `src/sheet_storage.py` は `gspread` のWorksheet互換オブジェクトを受け取りますが、
認証処理と `gspread` のインストールは利用者が用意してください。

## 変遷

コミット履歴・Issue・プルリクエストに基づく経緯です。

### Colabノートブック版（〜2025年）

出発点は、Google Colab上のノートブックです（リポジトリに残っているのは2025年2月8日付の v.10）。
分析と構造化にOpenAI（o3-mini）、文学的執筆にClaude、推論にDeepSeekを使い、生成結果はGoogle Sheetsに保存する構成でした。

### 設計仕様書の作成とローカル版の開発（2026年2月）

2026年2月11日にリポジトリを作成し（[初回コミット](https://github.com/masa-san-jp/100-times-ai-heros-journey/commit/6a462a7)）、
ノートブックの[設計仕様書](docs/design-specification.md)を作成しました（[#1](https://github.com/masa-san-jp/100-times-ai-heros-journey/issues/1)）。
続けて[Issue #2](https://github.com/masa-san-jp/100-times-ai-heros-journey/issues/2)では、次の3点が挙げられています。

- 推論をローカルの `gpt-oss:20b` に置き換える
- Google Sheetsではなくローカルにプロジェクトごとのフォルダを作り、制作ログを残す
- タスクごとに最適な推論の深さ（reasoning effort）を設定する

その後、Ollama + `gpt-oss:20b` による完全ローカル版の基盤（[#3](https://github.com/masa-san-jp/100-times-ai-heros-journey/issues/3)）、タスク別の reasoning effort（[#5](https://github.com/masa-san-jp/100-times-ai-heros-journey/issues/5)）、
`src/` 以下の本番実装（[#6](https://github.com/masa-san-jp/100-times-ai-heros-journey/issues/6)）が追加され、修正とテストの追加（[#7](https://github.com/masa-san-jp/100-times-ai-heros-journey/issues/7)）が続きました。

### モデル選択の拡充（2026年3月）

量子化版や `gpt-oss:120b` などのモデルを選べるようにし、実行ごとに出力ディレクトリを分けるようにしました（[#9](https://github.com/masa-san-jp/100-times-ai-heros-journey/issues/9)）。

### ローカル版パイプラインの整備（2026年8月）

Colab版と同等の工程（分析 → 要素プール → 世界観 → キャラクター → 骨子 → 12段階プロット → 10章本文 → ビジュアルプロンプト）を
ローカルで一括実行できる `run_pipeline.py` を追加しました。途中再開、重複除外、章ごとのチェックポイント、OpenAI・Anthropic・DeepSeekへの切り替えに対応しています。
あわせて、章本文が出力上限で途中切れしても成功扱いになる問題（[#10](https://github.com/masa-san-jp/100-times-ai-heros-journey/issues/10)）に対し、検出と継続生成を追加しました。

3つのモデル（`gemma4:e4b`、`gpt-oss:20b`、`qwen3.8:27b`）で生成した[完成作例](examples/README.md)を追加しました。
[兄弟リポジトリ](#兄弟リポジトリ)の一覧もREADMEに追加しました。

### 入力作成・集計機能の追加（2026年9月）

- 対話形式で13項目のナラティブJSONを作成する `create_narrative.py`（[#13](https://github.com/masa-san-jp/100-times-ai-heros-journey/issues/13)）
- 生成済みバッチの作品一覧・頻度集計と、LLMによる横断パターン抽出を行う `analyze_batch.py`（[#12](https://github.com/masa-san-jp/100-times-ai-heros-journey/issues/12)）
- Colabノートブックの `legacy/` への移動と、個人設定ファイルのGit管理からの除外（[#11](https://github.com/masa-san-jp/100-times-ai-heros-journey/issues/11)）

### ストーリーボード画像生成の追加（2026年9月）

生成した作品から、16:9のストーリーボード画像をローカルで作れるようになりました（`render_storyboard.py`、[#21](https://github.com/masa-san-jp/100-times-ai-heros-journey/issues/21)）。
画像生成には、兄弟リポジトリ [100-times-ai-heroes](https://github.com/masa-san-jp/100-times-ai-heroes) と同じ ComfyUI + Qwen-Image 2.1 を使います。

- 作品の各章から、場面・構図・登場人物をまとめたショットリスト（絵コンテ台本）を作成（[#23](https://github.com/masa-san-jp/100-times-ai-heros-journey/issues/23)）
- ショットリストから720×400の画像を生成。作品単体とバッチに対応し、途中再開できる（[#22](https://github.com/masa-san-jp/100-times-ai-heros-journey/issues/22)、[#24](https://github.com/masa-san-jp/100-times-ai-heros-journey/issues/24)）
- キャラクター参照画像を使い、コマ間で人物の見た目を揃える（[#25](https://github.com/masa-san-jp/100-times-ai-heros-journey/issues/25)）
- 全コマを並べた一覧シート画像と `storyboard.md` を出力（[#26](https://github.com/masa-san-jp/100-times-ai-heros-journey/issues/26)）
- 大ロングからクローズアップまでのショットサイズを物語の段階から割り当て、引きのショットを含める（[#32](https://github.com/masa-san-jp/100-times-ai-heros-journey/issues/32)、[#37](https://github.com/masa-san-jp/100-times-ai-heros-journey/issues/37)）
- キャラクター参照は、クローズアップとミディアムのコマだけに使う（[#33](https://github.com/masa-san-jp/100-times-ai-heros-journey/issues/33)）
- `gpt-oss:20b` 以外のモデルで生成した作品にも対応（[#38](https://github.com/masa-san-jp/100-times-ai-heros-journey/issues/38)）

作例は [examples/batch_full-gpt-oss-20b/run_001/](examples/batch_full-gpt-oss-20b/run_001/) で読めます。

### 旧Colab版について

`legacy/20250208-100-Times-AI-Heros-Journey-v.10.ipynb` が元のGoogle Colab版です。
ノートブックを使う場合は、ノートブック内の依存関係・APIキー設定・セル実行順に従ってください。
ローカル版とは依存関係や保存形式が異なります。

## 開発・テスト

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

テストはOllamaへ接続せず、クライアント契約・生成器・途中再開・重複除外などを検証します。
詳細な設計メモは [docs/design-spec-local.md](docs/design-spec-local.md) を参照してください。

## 制約と目安

- 生成時間はモデル、量子化、GPU/CPU、コンテキスト長、同時実行中の負荷で大きく変わります。
- 20B級モデルでは、最初の1作品でも数分〜数十分かかる場合があります。まず `--loops 1 --pool-size 3` で確認してください。
- 100作品を生成すると、各作品の本文・付随成果物ぶんの時間とディスク容量が必要です。
- ローカル版は入力と出力をローカルに保存しますが、指定したクラウドプロバイダーを使う場合はこの限りではありません。
- 生成物はAI出力です。公開前に内容、権利、個人情報、安全性を確認してください。

## ライセンス

MIT License（[LICENSE](LICENSE)）
