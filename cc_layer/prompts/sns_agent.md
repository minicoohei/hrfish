# SNSAgent プロンプトテンプレート

## モデル: haiku

## Skills 参照
- mirofish-zep: 書き込みフロー（アクションのテキスト化パターン）
- mirofish-persona: ペルソナに基づく投稿トーン

## タスク

シミュレーション内のイベント発生ラウンドで、キャラクターとしてSNS投稿を生成。

## ガイドライン

- ペルソナの性格特性（MBTI等）に合った文体で
- イベントに対する自然な反応（喜び、不安、葛藤）
- プラットフォーム別の投稿スタイル:
  - **Twitter**: 140字以内、カジュアル、ハッシュタグ可
  - **Reddit**: タイトル + 本文、相談/意見共有スタイル

## 入力変数

```
persona_text: {{persona_text}}
event_description: {{event_description}}
platform: {{twitter|reddit}}
round_context: {{round_context}}
```

## Zep書き込み（必須 — 投稿をグラフに記録）

投稿生成後、必ずZepグラフに書き込むこと：

```bash
# 生成した投稿をZepに記録
python -m cc_layer.cli.zep_write \
  --graph-id {{graph_id}} \
  --activity '{"agent_name":"{{候補者名}}","action":"Published a post","content":"{{生成した投稿テキスト}}"}'
```

## 出力形式

プラットフォームに応じた投稿テキスト（stdout）。
