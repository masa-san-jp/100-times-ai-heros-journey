# ローカル版開発ガイド

このドキュメントでは、Ollama + gpt-oss:20bを使用した完全ローカル版の開発について説明します。

## 📋 目次

1. [プロジェクト構造](#プロジェクト構造)
2. [開発フロー](#開発フロー)
3. [ハーネスの使い方](#ハーネスの使い方)
4. [本番実装](#本番実装)
5. [GitHubへのアップロード](#githubへのアップロード)

---

## プロジェクト構造

```
100-times-ai-heros-journey/
├── README.md                                # プロジェクト概要（クラウド版+ローカル版）
├── DEVELOPMENT.md                           # このファイル
├── .gitignore                               # Git除外設定
├── docs/
│   ├── design-specification.md             # クラウド版設計仕様書
│   └── design-spec-local.md                # ローカル版設計仕様書 ⭐
├── harness/                                 # 開発ハーネス（GitHubにアップロードしない）
│   ├── README.md                           # ハーネス詳細ドキュメント
│   ├── QUICKSTART.md                       # クイックスタートガイド
│   ├── config.json                         # ハーネス設定
│   ├── requirements.txt                    # Python依存関係
│   ├── 01_test_ollama_connection.py       # Ollama接続テスト
│   ├── 02_test_narrative_analysis.py      # ナラティブ分析テスト
│   ├── 03_test_character_generation.py    # キャラクター生成テスト
│   ├── run_all_tests.py                   # 全テスト実行スクリプト
│   ├── logs/                               # テストログ（自動生成）
│   ├── test_output/                        # テスト出力（自動生成）
│   └── mock_data/                          # モックデータ
├── src/                                     # 本番実装（今後作成）
│   ├── ollama_client.py
│   ├── story_generator.py
│   ├── character_generator.py
│   └── ...
├── output/                                  # 生成された物語（GitHubにアップロードしない）
│   ├── stories/
│   ├── characters/
│   ├── plots/
│   └── analysis/
└── data/                                    # データベース（GitHubにアップロードしない）
    └── story_data.db
```

---

## 開発フロー

### フェーズ1: ハーネスによる検証 ✅ 完了

1. **環境セットアップ**
   - Ollamaインストール
   - gpt-oss:20bダウンロード
   - Python依存関係インストール

2. **段階的テスト**
   - ✅ Ollama接続テスト
   - ✅ ナラティブ分析テスト
   - ✅ キャラクター生成テスト
   - ✅ プロット生成テスト
   - ✅ 物語執筆テスト

3. **問題の特定と解決**
   - パフォーマンス測定
   - エラーハンドリング確認
   - JSON生成精度確認

### フェーズ2: 本番実装 ✅ 完了

1. **コア機能の実装** ✅
   ```
   src/
   ├── __init__.py            # パッケージ初期化
   ├── ollama_client.py       # Ollama API クライアント (225行)
   ├── narrative_analyzer.py  # ナラティブ分析 (172行)
   ├── character_generator.py # キャラクター生成 (271行)
   ├── plot_generator.py      # プロット生成 (322行)
   └── story_generator.py     # 物語生成オーケストレーター (240行)
   ```

2. **テスト作成**
   - ユニットテスト
   - 統合テスト
   - エンドツーエンドテスト

3. **UI実装（オプション）**
   - Jupyter Notebook
   - または Gradio / Streamlit

### フェーズ3: 最適化

1. **パフォーマンス改善**
   - 並列処理
   - キャッシュ
   - バッチ処理

2. **エラーハンドリング強化**
   - リトライロジック
   - フォールバック
   - グレースフルデグラデーション

3. **ドキュメント整備**
   - API ドキュメント
   - ユーザーガイド
   - トラブルシューティング

---

## ハーネスの使い方

### クイックスタート

```bash
# 1. Ollamaサーバーを起動
ollama serve

# 2. ハーネスディレクトリに移動
cd harness

# 3. すべてのテストを実行
python3 run_all_tests.py
```

詳細は [harness/QUICKSTART.md](harness/QUICKSTART.md) を参照してください。

### 個別テストの実行

```bash
# Ollama接続テスト（5-10秒）
python3 01_test_ollama_connection.py

# ナラティブ分析テスト（5-10分）
python3 02_test_narrative_analysis.py

# キャラクター生成テスト（5-10分）
python3 03_test_character_generation.py
```

### テスト結果の確認

```bash
# ログファイル
cat harness/logs/connection_test.log
cat harness/logs/narrative_analysis_test.log
cat harness/logs/character_generation_test.log

# 生成された出力
ls -la harness/test_output/
cat harness/test_output/analysis_desire.txt
cat harness/test_output/character_protagonist.txt
```

### 設定のカスタマイズ

`harness/config.json` を編集：

```json
{
  "ollama": {
    "model": "gpt-oss:20b",    // 別モデルに変更可能
    "timeout": 300              // タイムアウト設定
  },
  "temperature": {
    "analysis": 0.5,            // タスク別のtemperature
    "writing": 1.0
  },
  "test_mode": {
    "enabled": true,            // テストモード
    "reduced_loops": 3          // ループ回数削減
  }
}
```

---

## 本番実装

### Step 1: コア機能の実装

ハーネスで検証したコードを `src/` に実装します。

**例: `src/ollama_client.py`**

```python
import requests
import json

class OllamaClient:
    def __init__(self, base_url="http://localhost:11434", model="gpt-oss:20b"):
        self.base_url = base_url
        self.model = model

    def chat(self, prompt, system="", temperature=0.7):
        """テキスト生成"""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": False
        }

        response = requests.post(
            f"{self.base_url}/api/chat",
            json=payload,
            timeout=300
        )
        response.raise_for_status()
        return response.json()["message"]["content"]

    def json_chat(self, prompt, temperature=0.3):
        """JSON形式でデータ生成"""
        # ハーネスで検証したコードを実装
        pass
```

### Step 2: Jupyter Notebookの作成

**`notebooks/local_story_generator.ipynb`**

```python
# セル1: インポート
from src.ollama_client import OllamaClient
from src.story_generator import StoryGenerator

# セル2: クライアント初期化
client = OllamaClient()

# セル3: ナラティブ入力
narrative = {
    "author": "...",
    "missing": "...",
    # ...
}

# セル4: 物語生成
generator = StoryGenerator(client)
story = generator.generate(narrative)
```

### Step 3: テストの作成

```bash
# テスト用ディレクトリ
mkdir -p tests

# ユニットテストを作成
touch tests/test_ollama_client.py
touch tests/test_story_generator.py
```

---

## GitHubへのアップロード

### アップロードされるファイル

以下のファイルはGitHubにアップロードされます：

```
✅ README.md
✅ DEVELOPMENT.md
✅ .gitignore
✅ docs/design-specification.md
✅ docs/design-spec-local.md
✅ src/*.py（本番実装）
✅ tests/*.py（テスト）
✅ requirements.txt
✅ notebooks/*.ipynb（Notebook）
```

### アップロードされないファイル

以下のファイルは `.gitignore` で除外されます：

```
❌ harness/                    # 開発ハーネス全体
❌ output/                     # 生成された物語
❌ data/                       # データベース
❌ *.log                       # ログファイル
❌ __pycache__/                # Pythonキャッシュ
❌ .ipynb_checkpoints/         # Notebookチェックポイント
```

### 開発履歴の管理

開発履歴はローカルで管理し、GitHubにはアップロードしません：

```bash
# 開発履歴用ディレクトリ
mkdir -p harness/dev_history

# メモを記録
echo "$(date): ナラティブ分析テスト完了" >> harness/dev_history/$(date +%Y-%m-%d).md
```

### Gitコミットの推奨

```bash
# 設計仕様書をコミット
git add docs/design-spec-local.md
git commit -m "docs: ローカル版設計仕様書を作成"

# .gitignoreをコミット
git add .gitignore
git commit -m "chore: 開発ファイルを.gitignoreに追加"

# READMEをコミット
git add README.md
git commit -m "docs: ローカル版開発手順をREADMEに追加"

# 本番実装をコミット（後日）
git add src/
git commit -m "feat: ローカル版コア機能を実装"
```

---

## パフォーマンスベンチマーク

### ハードウェア要件

| コンポーネント | 最小要件 | 推奨要件 |
|---|---|---|
| CPU | 4コア | 8コア以上（Apple M1/M2） |
| メモリ | 16GB | 32GB以上 |
| ストレージ | 20GB | SSD 50GB以上 |
| GPU | なし | NVIDIA GPU 8GB VRAM以上 |

### 処理時間の目安

| タスク | Apple M2 Max (CPU) | NVIDIA RTX 4090 (GPU) |
|---|---|---|
| Ollama接続テスト | 5-10秒 | 5-10秒 |
| ナラティブ分析（3項目） | 3-5分 | 1-2分 |
| キャラクター生成（4人） | 5-10分 | 2-4分 |
| 10章執筆 | 30-60分 | 10-20分 |
| 100ループ全体 | 8-12時間 | 2-4時間 |

---

## トラブルシューティング

### よくある問題

1. **Ollamaサーバーに接続できない**
   ```bash
   ollama serve
   ```

2. **メモリ不足**
   - より小さいモデルを使用: `ollama pull llama3:8b`

3. **処理が遅い**
   - GPU推論を有効化
   - テストモードで実行（ループ回数削減）

4. **JSONパースエラー**
   - temperature を下げる（0.3以下）
   - プロンプトを明確にする

詳細は [harness/README.md](harness/README.md) を参照してください。

---

## 次のステップ

1. ✅ ハーネスですべてのテストを実行
2. ✅ プロット生成・物語執筆テストを追加
3. ⏳ `src/` に本番実装を作成
4. ⏳ Jupyter Notebookでエンドツーエンドテスト
5. ⏳ ドキュメント整備
6. ⏳ GitHubにコミット

---

## 参考資料

- [ローカル版設計仕様書](docs/design-spec-local.md)
- [ハーネスREADME](harness/README.md)
- [クイックスタート](harness/QUICKSTART.md)
- [Ollama公式ドキュメント](https://ollama.com/)

---

**作成日**: 2026-02-14
**最終更新**: 2026-02-14
