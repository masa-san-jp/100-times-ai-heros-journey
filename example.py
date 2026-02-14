#!/usr/bin/env python3
"""
使用例: 物語生成の基本的な流れ
"""

from src.ollama_client import OllamaConfig
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

    # ステップ2: Ollama設定（オプション）
    config = OllamaConfig(
        base_url="http://localhost:11434",
        model="gpt-oss:20b",
        timeout=600  # 物語生成は時間がかかるので10分
    )

    # ステップ3: StoryGeneratorを初期化
    generator = StoryGenerator(ollama_config=config)

    # ステップ4: 物語を生成
    print("物語生成を開始します...")
    print("（処理時間: 約5-10分）")
    print()

    try:
        story = generator.generate(
            narrative=narrative,
            plot_type="旅 (Quest)"
        )

        # ステップ5: 結果を保存
        print(f"タイトル: {story.title}")
        print(f"章数: {len(story.chapters)}章")
        print(f"総文字数: {sum(len(c) for c in story.chapters)}文字")
        print()

        # ファイルに保存
        story_path = generator.save_story(story)
        print(f"✓ 物語を保存しました: {story_path}")

        analysis_path = generator.save_analysis(story.narrative_analysis)
        print(f"✓ 分析結果を保存しました: {analysis_path}")

        print("\n完了しました！")

    except Exception as e:
        print(f"✗ エラーが発生しました: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
