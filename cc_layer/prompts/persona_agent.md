# PersonaAgent プロンプトテンプレート

## モデル: opus

## Skills 参照
- mirofish-zep: Zepグラフからの背景情報取得
- mirofish-persona: ペルソナテンプレート構造とナラティブ拡張ガイド
- mirofish-career: イベントタイプとブロッカーの意味理解

## タスク

以下のシミュレーション結果から、候補者の**ナラティブペルソナ**を生成してください。

構造的テンプレート（PersonaRendererの出力）をベースに、以下を追加します：
1. **内的独白**: その人が今何を感じ、何を考えているか
2. **心理描写**: ブロッカーや制約に対する葛藤、家族への思い
3. **将来への展望**: キャリアパスごとの希望や不安

## 入力変数

```
graph_id: {{graph_id}}
identity: {{identity_json}}
final_states: {{top_paths_final_states_json}}
```

## Zep操作（必須 — これなしではMiroFish的なペルソナにならない）

ペルソナ生成の**前に必ずZep RAGを検索**し、候補者の背景情報を取得すること。

```bash
# 1. エンティティ一覧を取得（候補者の全属性・関係性）
python -m cc_layer.cli.zep_search --graph-id {{graph_id}} --mode entities

# 2. 候補者の詳細検索（学歴、職歴、スキル、人間関係）
python -m cc_layer.cli.zep_search --graph-id {{graph_id}} \
  --query "{{候補者名}}の経歴とスキル" --mode quick

# 3. 深い洞察が必要な場合（性格特性、行動パターン）
python -m cc_layer.cli.zep_search --graph-id {{graph_id}} \
  --query "{{候補者名}}の強みと弱み、行動特性" --mode insight
```

**取得した情報をペルソナに反映する:**
- エンティティの `summary` → ペルソナの背景描写に
- `related_edges` の fact → 人間関係の描写に
- `attributes` → 具体的な数値やスキルの裏付けに

## 出力形式

パスごとにマークダウン形式のナラティブペルソナを生成。
ファイル出力先: `cc_layer/state/{{session_id}}/persona_{{path_id}}.md`
