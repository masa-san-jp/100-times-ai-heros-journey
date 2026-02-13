# Plan: タスク別 reasoning_effort 設定機能の実装

**対象Issue:** #2 「ローカルバージョンを作成したい」 — 要件3
**目的:** タスクごとに `reasoning_effort` を最適化できるようにする

---

## 1. 現状分析

### 現在の問題
- `ai()` と `ai_list()` の両関数で `reasoning_effort="medium"` がハードコードされている
- すべてのAPI呼び出しが同一のreasoning_effortで実行されるため、タスクの複雑さに応じた最適化ができない

### 対象関数と呼び出し箇所

| 関数 | 定義箇所 | reasoning_effort |
|------|----------|------------------|
| `ai(prompt, model)` | Cell 3 (L160) | `"medium"` ハードコード |
| `ai_list(prompt, model)` | Cell 3 (L174) | `"medium"` ハードコード |
| `claude(prompt)` | Cell 12 (L20936) | なし（Anthropic APIは別パラメータ） |
| `dsr1(prompt, model)` | Cell 15 (L21567) | なし |

---

## 2. 設計方針

### 2.1 関数シグネチャの変更

`ai()` と `ai_list()` に `reasoning_effort` パラメータを追加する。

```python
# Before
def ai(prompt, model="o3-mini"):
    # reasoning_effort="medium" がハードコード

# After
def ai(prompt, model="o3-mini", reasoning_effort="medium"):
    # 引数で制御可能に
```

同様に `ai_list()` も変更する。

### 2.2 タスク別推奨設定マップ

タスクの特性に基づき、以下の3段階で分類する。

| reasoning_effort | 適用タスク | 理由 |
|------------------|-----------|------|
| **`"high"`** | ナラティブ分析（願望/抑圧/葛藤）、統合プロット生成 | 深い分析・複雑な構造把握が必要 |
| **`"medium"`** | キャラクター生成（主人公/使者/援助者/敵対者）、10章プロット生成、プロット骨子(A-E)、世界観生成 | バランスの取れた品質が必要 |
| **`"low"`** | 要素プールのリスト生成（wants/abilities/roles 各100個）、ビジュアルプロンプト生成、プロット形式分類、テスト呼び出し | 大量生成・単純変換タスク |

### 2.3 設定の外部化（config辞書）

ノートブック冒頭にタスク別設定の辞書を配置し、一箇所で管理・変更できるようにする。

```python
REASONING_CONFIG = {
    "analysis":       "high",    # ナラティブ分析（願望/抑圧/葛藤）
    "narrative":      "high",    # ナラティブ要素抽出
    "element_pool":   "low",     # 要素プール生成（wants/abilities/roles）
    "plot_classify":  "low",     # プロット形式分類
    "character":      "medium",  # キャラクター生成
    "plot":           "medium",  # プロット生成
    "visual":         "low",     # ビジュアルプロンプト
    "world":          "medium",  # 世界観生成
    "plot_skeleton":  "medium",  # プロット骨子(A-E)
    "integrated_plot":"high",    # 統合プロット
    "default":        "medium",  # デフォルト
}
```

---

## 3. 実装ステップ

### Step 1: `ai()` / `ai_list()` 関数にパラメータ追加（Cell 3）

- `reasoning_effort` を引数として追加（デフォルト値: `"medium"`）
- API呼び出し時に引数の値を使用する

### Step 2: 設定辞書 `REASONING_CONFIG` を追加（Cell 3の先頭）

- タスク種別をキーとした設定辞書をセルの先頭に配置
- ユーザーがここを編集するだけで全体の挙動を変更可能にする

### Step 3: 各呼び出し箇所に適切な `reasoning_effort` を適用

以下の箇所を変更する。

| セル | 呼び出し | 変更内容 |
|------|---------|---------|
| Cell 3 | `ai("テスト出力を行って")` | そのまま（デフォルト値使用） |
| Cell 3 | `ai_list("テスト出力を行って")` | そのまま（デフォルト値使用） |
| Cell 6 | `ai(...)` × 3（願望/抑圧/葛藤分析） | `reasoning_effort=REASONING_CONFIG["analysis"]` |
| Cell 7 | `ai_list(...)`（ナラティブ要素抽出） | `reasoning_effort=REASONING_CONFIG["narrative"]` |
| Cell 8 | `ai_list(...)` × 3（wants/abilities/roles） | `reasoning_effort=REASONING_CONFIG["element_pool"]` |
| Cell 9 | `ai_list(...)`（プロット形式分類） | `reasoning_effort=REASONING_CONFIG["plot_classify"]` |
| Cell 10 | `ai(...)` × 5（キャラクター+プロット生成ループ） | キャラクター: `REASONING_CONFIG["character"]`、プロット: `REASONING_CONFIG["plot"]` |
| Cell 18 | `ai(...)`（プロット再生成） | `reasoning_effort=REASONING_CONFIG["plot"]` |
| Cell 19 | `ai(...)` × 10（OpenAI物語執筆） | `reasoning_effort=REASONING_CONFIG["plot"]` |
| Cell 20-23 | `ai(...)` × 4（ビジュアルプロンプト） | `reasoning_effort=REASONING_CONFIG["visual"]` |
| Cell 24 | `ai(...)`（世界観生成） | `reasoning_effort=REASONING_CONFIG["world"]` |

### Step 4: 設計仕様書の更新（`docs/design-specification.md`）

- セクション6.1, 6.2: 関数シグネチャにパラメータ追加を反映
- セクション7: タスク別reasoning_effort設定の説明を追加

---

## 4. 変更対象ファイル

| ファイル | 変更内容 |
|---------|---------|
| `20250208-100-Times-AI-Heros-Journey-v.10.ipynb` | 関数定義の変更、設定辞書の追加、各呼び出し箇所の更新 |
| `docs/design-specification.md` | 関数仕様と設定の記述を更新 |

---

## 5. 期待される効果

- **コスト最適化**: 単純なタスクに `"low"` を使うことでAPI推論コストを削減
- **品質向上**: 複雑な分析タスクに `"high"` を使うことでより深い分析結果を取得
- **柔軟性**: `REASONING_CONFIG` 辞書を編集するだけで、全タスクのreasoning_effortを一括制御可能
- **後方互換性**: デフォルト値 `"medium"` により、既存の呼び出しは変更なしで動作
