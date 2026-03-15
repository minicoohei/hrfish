# ConfigAgent プロンプトテンプレート

## モデル: sonnet

## Skills 参照
- mirofish-career: イベントタイプ定義・ブロッカールール・スコアリング重み
- mirofish-zep: Zepグラフからの背景情報取得

## タスク

シミュレーション要件・候補者プロフィール・ドキュメント情報から、
**SimulationParameters JSON** を生成してください。

## 入力変数

```
graph_id: {{graph_id}}
requirement: {{simulation_requirement}}
profiles: {{profiles_json}}
document_text: {{document_text}} (省略時あり)
```

## Zep操作（推奨）

設定生成の前にZepグラフを検索し、エンティティの関係性を把握すること。

```bash
python -m cc_layer.cli.zep_search --graph-id {{graph_id}} --mode entities
python -m cc_layer.cli.zep_search --graph-id {{graph_id}} \
  --query "候補者の職歴・スキル・目標" --mode quick
```

## 出力JSON仕様

以下のdataclass構造に完全一致するJSONを生成してください。

### TimeSimulationConfig

```json
{
  "total_simulation_hours": 72,
  "minutes_per_round": 60,
  "agents_per_hour_min": 5,
  "agents_per_hour_max": 20,
  "peak_hours": [19, 20, 21, 22],
  "peak_activity_multiplier": 1.5,
  "off_peak_hours": [0, 1, 2, 3, 4, 5],
  "off_peak_activity_multiplier": 0.05,
  "morning_hours": [6, 7, 8],
  "morning_activity_multiplier": 0.4,
  "work_hours": [9, 10, 11, 12, 13, 14, 15, 16, 17, 18],
  "work_activity_multiplier": 0.7
}
```

### AgentActivityConfig (プロフィールごとに1つ)

```json
{
  "agent_id": 1,
  "entity_uuid": "エンティティUUID",
  "entity_name": "名前",
  "entity_type": "CareerAdvisor",
  "activity_level": 0.5,
  "posts_per_hour": 1.0,
  "comments_per_hour": 2.0,
  "active_hours": [8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22],
  "response_delay_min": 5,
  "response_delay_max": 60,
  "sentiment_bias": 0.0,
  "stance": "neutral",
  "influence_weight": 1.0
}
```

**stance の選択肢:** supportive, opposing, neutral, observer
**activity_level:** 主要候補者は0.7-0.9、サブキャラは0.3-0.5

### EventConfig

```json
{
  "initial_posts": [
    {
      "content": "投稿内容",
      "platform": "twitter",
      "poster_agent_id": 1,
      "importance": "high"
    }
  ],
  "scheduled_events": [
    {
      "trigger_round": 10,
      "event_type": "career_change",
      "description": "転職面接",
      "posts": []
    }
  ],
  "hot_topics": ["AI", "転職", "マネジメント"],
  "narrative_direction": "技術リーダーからマネジメントへの転換ストーリー",
  "career_phases": [
    {
      "phase_id": 1,
      "phase_name": "現在の評価",
      "trigger_round": 1,
      "scenario_description": "現職での状況",
      "evaluation_focus": "現在のスキルと課題",
      "career_developments": ["チームリード経験"],
      "injected_posts": []
    }
  ]
}
```

### 最終出力 (SimulationParameters)

```json
{
  "simulation_id": "sim_001",
  "project_id": "proj_001",
  "graph_id": "{{graph_id}}",
  "simulation_requirement": "{{requirement}}",
  "time_config": { ... },
  "agent_configs": [ ... ],
  "event_config": { ... },
  "twitter_config": {
    "platform": "twitter",
    "recency_weight": 0.4,
    "popularity_weight": 0.3,
    "relevance_weight": 0.3,
    "viral_threshold": 10,
    "echo_chamber_strength": 0.5
  },
  "reddit_config": null,
  "llm_model": "claude-sonnet",
  "llm_base_url": "",
  "generation_reasoning": "生成理由の要約"
}
```

## 生成ガイドライン

1. **career_phases は必ず3つ**: 現在(phase_id=1)、短期1-2年(phase_id=2)、中期3-5年(phase_id=3)
2. **trigger_round**: total_rounds を3等分して各フェーズに割り当て
3. **agent_configs**: profiles の各エントリに対応する設定を生成
4. **hot_topics**: requirement と document_text から5-10個のキーワード抽出
5. **initial_posts**: シミュレーション開始時の状況設定投稿を2-3件
6. **narrative_direction**: requirement に基づくストーリーの方向性を1文で

## ファイル出力

JSONを `cc_layer/state/{{session_id}}/sim_config.json` に書き出してください。
