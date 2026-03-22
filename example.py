#!/usr/bin/env python3
"""
使用例: 物語生成の基本的な流れ

モデル選択ガイド:
  標準（デフォルト）:
    gpt-oss:20b          - 推奨。バランスの取れた品質と速度（約15GB RAM）

  量子化版（メモリ節約・高速化が必要な場合）:
    gpt-oss:20b-q8_0     - ほぼ同等品質（約12GB RAM）
    gpt-oss:20b-q5_K_M   - バランス型（約8GB RAM）
    gpt-oss:20b-q4_K_M   - メモリ効率重視（約7GB RAM）
    gpt-oss:20b-q4_0     - 最小メモリ構成（約6GB RAM）

  高性能マシン向け（64GB RAM 以上を推奨）:
    gpt-oss:120b         - 最高品質（約80GB RAM）
    gpt-oss:120b-q4_K_M  - 省メモリ高性能版（約45GB RAM）
"""

from src.ollama_client import OllamaConfig, AVAILABLE_MODELS
from src.narrative_analyzer import NarrativeInput
from src.story_generator import StoryGenerator


def main():
    """メイン関数"""

    # ステップ1: ナラティブ入力を準備
    narrative = NarrativeInput(
        author="知らないことを学んだり、本質を考えたり、空想をするのが好き。",
        missing="私には人間的な感情が欠けている。他者との感情的な交流と関係性を築くことの難しさを象徴するものである。",
        status="成功とは何かわからない状態",
        memories="いつも一人で遊んでいて、孤独感を感じていた。",
        mission="家族、友人、同僚など身近な存在と、積極的に自発的に感情的なコミュニケーションを図ること。",
        success="手に入るイメージが湧かない。",
        loss="安心できる自分だけの世界。",
        taboo="自分自身の意思や他者の尊厳を損なうこと。",
        inhibit="自分自身のプライド、他者に敬われたい気持ち。",
        daily="孤独、空想、創造。",
        change="友人や尊敬する人との会話の中で得られる気づき。",
        acceptance="許せないかもしれない。",
        desire="全ての人に尊敬され、敬われたい。"
    )

    # ステップ2: Ollama設定
    # デフォルトは gpt-oss:20b。他のモデルに変更するには model= を書き換えてください。
    # 利用可能モデル一覧は AVAILABLE_MODELS を参照（from src.ollama_client import AVAILABLE_MODELS）
    config = OllamaConfig(
        base_url="http://localhost:11434",
        model="gpt-oss:20b",    # 変更例: "gpt-oss:20b-q4_K_M" や "gpt-oss:120b"
        timeout=600             # 物語生成は時間がかかるので10分
    )

    # ステップ3: StoryGeneratorを初期化
    generator = StoryGenerator(ollama_config=config)

    # ステップ4: 物語を生成
    print("物語生成を開始します...")
    print(f"モデル: {config.model}")
    print("（処理時間: 約5-10分）")
    print()

    try:
        story = generator.generate(
            narrative=narrative,
            plot_type="旅 (Quest)"
        )

        # ステップ5: 結果を実行ごとのディレクトリに保存
        # output/run_YYYYMMDD_HHMMSS/ ディレクトリを自動作成し、
        # 物語と分析結果をそれぞれ保存します。
        # 繰り返し実行するたびに新しいディレクトリが作られるため、
        # 過去の結果を上書きせずにアイデア探索できます。
        print(f"タイトル: {story.title}")
        print(f"章数: {len(story.chapters)}章")
        print(f"総文字数: {sum(len(c) for c in story.chapters)}文字")
        print()

        run_dir = generator.save_run(story)
        print(f"✓ 実行結果を保存しました: {run_dir}/")

        print("\n完了しました！")

    except Exception as e:
        print(f"✗ エラーが発生しました: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
