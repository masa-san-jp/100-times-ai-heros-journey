# 100 Times AI Hero's Journey

作家の自己ナラティブから、ヒーローズ・ジャーニー形式の物語を生成するPython CLI/APIです。
物語構造は、ヒーローズ・ジャーニー（12段・11段）、ストーリーサークル（8段）、セーブ・ザ・キャット（15段）、起承転結（4段）から選べます（[物語構造を選ぶ](#物語構造を選ぶ)）。
標準ではOllama上のローカルモデルを使うため、入力と生成物を外部APIへ送らずに実行できます。

📖 **関連記事:** [noteの記事を読む](https://note.com/masa_san_jp/n/n33dead2ffc6f)

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
| 3'. 構造の違うバッチを比べる（任意） | `compare_batches.py` | 構造・段数・要素の頻度・作品一覧を並べた比較表（`comparison_report.md`） |
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

### 物語構造の異なるバッチを比べる

同じナラティブから`--structure`を変えて生成した複数のバッチを、並べて比べられます。LLMは使いません。

```bash
python compare_batches.py output/batch_journey output/batch_kishotenketsu \
  --output-dir output/comparison_journey-vs-kishotenketsu
```

`comparison_report.md`（人が読む版）と`comparison_report.json`（機械可読版）を出力します。内容は次のとおりです。
- バッチごとの構造・段数・作品数・平均章数・プロット形式・モデル
- 構造の段の並び
- 選ばれた要素（want / ability / role / narrative）の頻度
- 作品一覧と本文へのリンク

構造の良し悪しは判定しません。各バッチの`narrative.json`が一致しない場合はエラーになります。異なるナラティブのバッチも比べる場合は`--allow-different-narratives`を付けてください。
`structure`を記録していない以前のバッチは、`batch_manifest.json`の`journey_stage_count`から`journey-11` / `journey-12`として扱います。

## ストーリーボードを作る

画像生成に必要な ComfyUI、Qwen Image 2.1、Viggle Turbo用カスタムノードは、次のコマンドで導入できます。
モデルを含めてディスクを約33GB使い、Qwen Research License（研究・評価目的に限る）の確認が必要です。

```bash
python setup_storyboard.py
```

既存の ComfyUI（100-times-ai-heroes で導入済みのものを含む）は、`--comfyui-dir` で指定できます（専用 venv が別の場所にある場合は `--comfyui-venv` も指定します）。既存 venv の依存は変更せず、必要な場合だけ `--update-deps` で導入します。
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
| `--structure NAME` | `journey-12` | 物語構造。`journey-12` / `journey-11` / `story-circle-8` / `save-the-cat-15` / `kishotenketsu-4`（[生成される工程](#生成される工程)を参照） |
| `--journey-stages 11\|12` | `12` | ヒーローズ・ジャーニーの段階数（互換用。`--structure journey-11` と同じ。`--structure`と同時には指定できません） |
| `--emotional-arc NAME` | 作品ごとに自動 | 段ごとの感情の上下を決める形を全作品で固定する。`rags-to-riches` / `tragedy` / `man-in-a-hole` / `icarus` / `cinderella` / `oedipus`（[感情曲線を指定する](#感情曲線を指定する)を参照） |
| `--situation N` | 作品ごとに自動 | ポルティの劇的状況（1〜36）を全作品で固定する（[劇的状況を指定する](#劇的状況を指定する)を参照） |
| `--plot-type NAME` | 作品ごとに自動 | プロット形式を全作品で固定する。21個の形式のどれか（`src/colab_features.py`の`DEFAULT_PLOT_TYPES`）と一字一句同じ名前に限る |
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
7. 選んだ物語構造（既定はヒーローズ・ジャーニー12段階）に沿ったプロット
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

### 物語構造を選ぶ

`--structure NAME`でプロットの構造を選べます。同じナラティブ・同じ人物から、構造を変えて物語を比べるための機能です。

| 名前 | 構造 | 段数 | 段の名前 |
|---|---|---:|---|
| `journey-12`（既定） | ヒーローズ・ジャーニー | 12 | 上記の12段階 |
| `journey-11` | ヒーローズ・ジャーニー（旧版） | 11 | 12段階から「最も危険な場所への接近」を除いたもの |
| `story-circle-8` | ダン・ハーモンのストーリーサークル | 8 | You、Need、Go、Search、Find、Take、Return、Change |
| `save-the-cat-15` | ブレイク・スナイダーのセーブ・ザ・キャット | 15 | Opening Image、Theme Stated、Set-Up、Catalyst、Debate、Break into Two、B Story、Fun and Games、Midpoint、Bad Guys Close In、All Is Lost、Dark Night of the Soul、Break into Three、Finale、Final Image |
| `kishotenketsu-4` | 起承転結 | 4 | 起（導入）、承（展開）、転（転換・ひねり）、結（結果） |

```bash
python run_pipeline.py --structure story-circle-8 --loops 1 --pool-size 3 --no-chapters
```

- 追加した3構造の段の名前は、二次資料（Wikipedia と解説記事、確認日2026-11-25）によります。一次資料の確認は [arayashiki-kb のイシュー #39](https://github.com/masa-san-jp/arayashiki-kb/issues/39) で進めていて、終わったら名前を見直します。
  - https://www.studiobinder.com/blog/dan-harmon-story-circle
  - https://www.studiobinder.com/blog/save-the-cat-beat-sheet/
  - https://en.wikipedia.org/wiki/Story_structure
- 各段の幕（第一幕〜第三幕）は、セーブ・ザ・キャットの13〜15が第三幕であること以外は暫定です。
- 各段の役割の説明文（プロンプトに入る日本語の文）も暫定です。一般的な解説に沿って書いたもので、出典との照合はしていません。一次資料の確認後に、段の名前と一緒に見直します。
- 選んだ構造は`batch_manifest.json`の`structure`に保存され、`--resume`ではその構造を使います。別の構造を指定して再開するとエラーになります。
- 章数が段数より多い場合（例: 起承転結で10章）は、段数と同じ章数になります。
- プロット骨子A〜Eは、選んだ構造の段を5つの部（A 始まり、B 展開、C 山場、D 決着、E 結末）に割り当てて作ります。ヒーローズ・ジャーニー（`journey-12` / `journey-11`）の骨子は従来どおりです。

  | 構造 | A | B | C | D | E |
  |---|---|---|---|---|---|
  | `story-circle-8` | 1〜2 | 3〜4 | 5〜6 | 7 | 8 |
  | `save-the-cat-15` | 1〜6 | 7〜9 | 10〜12 | 13〜14 | 15 |
  | `kishotenketsu-4` | 起 | 承 | 転 | 結（出来事の決着） | 結（新しい状態） |
- ストーリーボードのショットサイズは、4・8・15段それぞれに並びを用意しています（`config/storyboard/shot_plan.json`）。

自動評価やランキング機能は現在実装していません。

### 感情曲線を指定する

プロットの各段に、感情の上下（上昇・下降）が付きます。形は作品ごとに下の6つから自動で選ばれ（プロット形式と同じく乱数で選び、`--seed`で再現できます）、`--emotional-arc NAME`を付けると全作品をその形に固定できます。

| 名前 | 形 | 感情の上下 |
|---|---|---|
| `rags-to-riches` | 貧から富へ | 上昇 |
| `tragedy` | 悲劇 | 下降 |
| `man-in-a-hole` | 穴に落ちた男 | 下降→上昇 |
| `icarus` | イカロス | 上昇→下降 |
| `cinderella` | シンデレラ | 上昇→下降→上昇 |
| `oedipus` | オイディプス | 下降→上昇→下降 |

```bash
python run_pipeline.py --emotional-arc man-in-a-hole --loops 1 --pool-size 3 --no-chapters  # 固定したいときだけ
```

- 形の上下の並びを、選んだ構造の段数に前から等分して割り振ります（例: `journey-12`と`man-in-a-hole`は1〜6段が下降、7〜12段が上昇）。
- 各段の上下は、プロット生成のプロンプトの段の一覧に`［感情: 上昇］`の形で入ります。プロット本文の「N. 名前 (第X幕)」の形式は変わりません。
- 6つの形の出典は、Reagan ほか「The emotional arcs of stories are dominated by six basic shapes」（EPJ Data Science 5:31、2016）。Project Gutenberg の英語の小説1,327冊の語の感情価から得られた基本形です。知識ベースの[arayashiki-culture cul-0024](https://github.com/masa-san-jp/arayashiki-culture/blob/main/entries/reagan-2016-emotional-arcs-of-stories.md)にまとめてあります。ヴォネガットが講演で語った形とは数も名前も同じではありません。
- 各作品の形は`metadata.json`の`selected_elements.emotional_arc`に残り、`analyze_batch.py`の頻度表と`compare_batches.py`の要素比較に出ます。
- `batch_manifest.json`の`emotional_arc`は固定指定の値です（自動のときは`null`）。固定したバッチを`--resume`するとその形を使い、別の形を指定するとエラーになります。

### 劇的状況を指定する

作品ごとに、プロット形式とは別の軸として、ポルティ『36の劇的状況』（1895）の状況が1つ付きます。状況は、選ばれたプロット形式と同じ意味のものを除いた中から乱数で選ばれ（`--seed`で再現できます）、`--situation N`（1〜36）を付けると全作品をその状況に固定できます。

```bash
python run_pipeline.py --situation 12 --loops 1 --pool-size 3 --no-chapters  # 固定したいときだけ
```

- 形式と同じ意味の状況（形式「復讐」と状況「罪を追う復讐」など）は、`config/story/dramatic_situations.json`の除外表に従って選びません。重なりの判断に推論（LLM）は使いません。
- 除外表は、21個のプロット形式すべてについて、選ばない状況の番号を書きます。いま除外があるのは、ラブストーリー（28 妨げられる恋、29 敵を愛する）、ミステリー／犯罪（11 謎）、サバイバル／ディストピア（6 災厄）、復讐（3 罪を追う復讐、4 近親のための復讐）、陰謀・政治劇（8 反乱、30 野心）です。状況の本文は見出しのほか未読のため、見出しの意味で判断しています。
- 除外表は形式の名前で引くため、プロット形式の分類で21個と一字一句同じ名前で返らなかった候補は捨てます。候補が1つも残らなければ、生成を始める前にエラーで止まります。`--plot-type`も21個のどれかに限ります。
- `--situation`で固定した状況を除外する形式は、候補から外します。
- 状況は、プロンプトの【物語形式】に`- **劇的状況**: 獲得（ポルティ『36の劇的状況』第12状況 Obtenir）`の形で入り、人物・プロット骨子・プロットの生成に使われます。
- 36状況の見出しと日本語の仮訳は、仏語原典（Project Gutenberg 72036）を読んだ知識ベースの[arayashiki-culture cul-0086](https://github.com/masa-san-jp/arayashiki-culture/blob/main/entries/polti-1895-thirty-six-dramatic-situations.md)によります。
- 各作品の状況は`metadata.json`の`selected_elements.dramatic_situation`に残り、`analyze_batch.py`の頻度表と`compare_batches.py`の要素比較に出ます。
- `batch_manifest.json`の`dramatic_situation`は固定指定の番号です（自動のときは`null`）。固定したバッチを`--resume`するとその状況を使い、別の状況を指定するとエラーになります。

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
`batch_manifest.json` には完了数、試行数、重複破棄数、設定（物語構造`structure`を含む）、エラー内容が記録されます。
各runの`metadata.json`にも、使った物語構造`structure`と段数`stage_count`が記録されます。

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
- ComfyUI・画像モデル・Viggle Turbo用カスタムノードを `setup_storyboard.py` で導入し、画像生成時にComfyUIを自動で起動・停止（[#48](https://github.com/masa-san-jp/100-times-ai-heros-journey/issues/48)）

作例は [examples/batch_full-gpt-oss-20b/run_001/](examples/batch_full-gpt-oss-20b/run_001/) で読めます。

### 物語構造の選択と比較（2026年11月）

同じナラティブ・同じ人物から、異なる物語構造で物語を作って比べられるようになりました（[#51](https://github.com/masa-san-jp/100-times-ai-heros-journey/issues/51)）。

- `--structure` で、ヒーローズ・ジャーニー（12段・11段）に加え、ストーリーサークル（8段）、セーブ・ザ・キャット（15段）、起承転結（4段）を選べる。段の名前と並びは構造の定義で固定し、ストーリーボードのショットサイズも段数ごとに割り当てる（[#52](https://github.com/masa-san-jp/100-times-ai-heros-journey/pull/52)）
- プロット骨子A〜Eを、選んだ構造の段から作る（[#53](https://github.com/masa-san-jp/100-times-ai-heros-journey/issues/53)）
- 構造の異なる複数のバッチを並べて比べる `compare_batches.py`（[#54](https://github.com/masa-san-jp/100-times-ai-heros-journey/issues/54)）

プロップの31機能、ポルティの36状況、ヴォネガットの感情曲線は見送り、[#55](https://github.com/masa-san-jp/100-times-ai-heros-journey/issues/55) に記録しています。

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
