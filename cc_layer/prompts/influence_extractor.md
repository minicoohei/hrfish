# InfluenceExtractor プロンプトテンプレート（Phase C）

## モデル: opus

## Skills 参照
- mirofish-zep: 会話ログからインサイト抽出
- mirofish-career: パス状態の変更可能フィールド

## タスク

Swarm議論（Phase B）の会話ログを分析し、各キャリアパスへの修正提案を抽出する。
会話から得られたインサイトのみに基づき、ハルシネーションを排除した提案を生成する。

## 現在のパス状態

{path_states}

## 会話ログ（Phase B出力）

{conversation_log}

## 過去の提案履歴

{past_suggestions}

## 反ハルシネーション制約（厳守）

以下の5つの制約を全て満たすこと。1つでも違反した場合、その提案は無効とする。

### 制約1: ソース引用必須

提案には必ず会話ログからの**原文引用**を含めること。
引用は `source_quote` フィールドに、発言者名と共に記録する。

**NG例**: 会話に存在しない発言を引用する
**OK例**: `"source_quote": "agent_id=3 田中: AIスキルがあれば年収800万は狙える"`

### 制約2: 未議論パスはnull

会話ログで言及されていないパスについては、提案を `null` とする。
推測や補完で提案を生成してはならない。

### 制約3: 信頼度スコア

各提案に `confidence` スコア（0.0〜1.0）を付与する。
**閾値: 0.6** — これ未満の提案は出力に含めるが、適用時にスキップされる。

| スコア | 基準 |
|--------|------|
| 0.9-1.0 | 複数エージェントが一致して支持、具体的根拠あり |
| 0.7-0.8 | 2名以上が言及、論理的に妥当 |
| 0.5-0.6 | 1名のみ言及、または根拠が弱い |
| 0.3-0.4 | 少数意見、反論あり |
| 0.0-0.2 | 根拠不十分、推測的 |

### 制約4: 最大2パス変更

1ラウンドで修正提案を出せるパスは**最大2つ**まで。
3パス以上に変更が必要な場合は、信頼度の高い上位2つのみ採用する。

### 制約5: 過去提案との整合性

`past_suggestions` に含まれる過去の提案と矛盾する場合は、
`consistency_note` フィールドに矛盾の理由と、なぜ今回の提案が妥当かを記載する。

## 許可されるタイプ（suggestion_type）

| タイプ | 説明 |
|--------|------|
| pivot | キャリアの方向転換 |
| opportunity | 新しい機会の発見 |
| risk | リスク要因の顕在化 |
| blocker | キャリアを阻む障害 |
| acceleration | キャリア成長の加速 |
| deceleration | キャリア成長の減速 |
| network | 人脈・ネットワークの変化 |
| skill_shift | 必要スキルの変化 |
| lifestyle_change | ライフスタイルの変化 |

## 許可される状態変更（state_changes キー）

| フィールド | 型 | 例 |
|-----------|-----|-----|
| role | string | "シニアエンジニア" |
| employer | string | "スタートアップX社" |
| industry | string | "ヘルスケアIT" |
| salary_annual | number | 8500000 |
| skills | list[string] | ["Python", "MLOps"] |
| stress_level | float (0-1) | 0.7 |
| job_satisfaction | float (0-1) | 0.6 |
| work_life_balance | float (0-1) | 0.5 |
| side_business | string | null |
| years_in_role | number | 2 |

## 出力形式

JSON形式。パスごとに `null` または提案オブジェクトを出力する。

```json
{
  "round_num": {round_num},
  "path_a": null,
  "path_b": {
    "suggestion_type": "opportunity",
    "description": "AI領域の求人増加により、転職市場が活性化",
    "source_quote": "agent_id=3 田中: 最近のAI求人、前年比2倍になってるらしい",
    "confidence": 0.75,
    "state_changes": {
      "role": "MLエンジニア",
      "salary_annual": 9000000,
      "skills": ["Python", "PyTorch", "MLOps"]
    },
    "consistency_note": null
  },
  "path_c": {
    "suggestion_type": "risk",
    "description": "業界再編によるポジション不安定化",
    "source_quote": "agent_id=7 鈴木: あの業界、来年の統合でかなりポジション減るって聞いた",
    "confidence": 0.62,
    "state_changes": {
      "stress_level": 0.8,
      "job_satisfaction": 0.4
    },
    "consistency_note": "前回ラウンドでは安定と評価したが、新情報により見直し"
  },
  "path_d": null,
  "path_e": null
}
```

## 入力変数

```
round_num: {round_num}
path_states: {path_states}
conversation_log: {conversation_log}
past_suggestions: {past_suggestions}
```
