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

## 参考文献

- Joseph Campbell『千の顔をもつ英雄』
- Christopher Vogler『The Writer's Journey: Mythic Structure for Writers』
