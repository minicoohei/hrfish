# MiroFish パイプライン実行ガイド

## 概要
誰がCCセッションを立ち上げても、このガイドに従えば
キャリアシミュレーションHTMLレポートを生成できる。

## 前提条件
- Python 3.11+, pydantic v2
- cc_layer パッケージが import 可能

## 進捗確認
```bash
python -m cc_layer.cli.pipeline_run --session-dir {SESSION} --phase status
```

## Step 0: 入力収集
AskUserQuestion で以下を収集:
1. 履歴書（ファイルパス or テキスト）
2. 基本情報（年齢、年収、家族構成、ローン等）
3. シミュレーション要件（関心領域・キャリア目標）

profile.json, form.json, resume.txt を生成して SESSION_DIR に配置。

## Step 1: 初期化
```bash
python -m cc_layer.cli.sim_init \
  --profile @{SESSION}/profile.json \
  --form @{SESSION}/form.json \
  --seed 42 --output-dir {SESSION}
```

## Step 2: パス設計 (SubAgent)
Agent(model=sonnet, prompt=cc_layer/prompts/path_designer_agent.md)
入力: agent_state.json + resume.txt
出力: path_designs.json (5パス)

## Step 2.5: 報酬水準リファレンス生成
```bash
python -m cc_layer.cli.compensation_fetch \
  --mode build \
  --candidate-context "{age}歳、{role}、年収{income}万" \
  --paths-file {SESSION}/path_designs.json \
  --format prompt > {SESSION}/compensation_ref.md
```

## Step 3: パス展開 (SubAgent x5 並列)
5つの Agent(model=sonnet) を並列起動。
各パスに対し path_expander_agent.md をプロンプトとして使用。
compensation_ref.md の内容をプロンプトに含めること。
出力: path_expanded_path_{a-e}.json

## Step 4: スコアリング + 正規化
```bash
python -m cc_layer.cli.multipath_run \
  --state-file {SESSION}/agent_state.json \
  --round-count 40 --top-n 5 \
  --output-file {SESSION}/multipath_result.json

python -m cc_layer.cli.pipeline_run --session-dir {SESSION} --phase normalize
```

## Step 5: Swarmエージェント生成
```bash
python -m cc_layer.cli.generate_swarm_agents \
  --session-dir {SESSION} --num-workers 6 --num-paths 5
```

## Step 6: Swarm会話生成 (SubAgent)
SwarmRoundAgent を起動して40ラウンドの会話を生成。
出力: swarm/all_actions_round_001-040.jsonl

正規化:
```bash
python -m cc_layer.cli.pipeline_run --session-dir {SESSION} --phase normalize
```

## Step 7: ファクトチェック
```bash
python -m cc_layer.cli.fact_check extract --session-dir {SESSION}
```

Agent(model=sonnet, prompt=cc_layer/prompts/fact_checker_agent.md)
入力: fact_check_claims.json + multipath_result.json
出力: fact_check.json

```bash
python -m cc_layer.cli.fact_check merge \
  --session-dir {SESSION} \
  --checks {SESSION}/fact_check.json
```

## Step 8: マクロトレンド (SubAgent)
Agent(model=sonnet) でWeb検索を使った市場調査。
出力: macro_trends.json

構造:
```json
{
  "trends": [
    {
      "trend_id": "...",
      "label": "...",
      "category": "...",
      "description": "...",
      "probability": 0.8,
      "timeframe": "2026-2030",
      "impact_by_path": {
        "path_a": {
          "direction": "positive",
          "magnitude": "high",
          "detail": "..."
        }
      },
      "sources": [
        {
          "title": "...",
          "excerpt": "..."
        }
      ]
    }
  ],
  "salary_benchmarks": [
    {
      "role": "...",
      "range": "...",
      "source": "...",
      "note": "..."
    }
  ]
}
```

## Step 9: レポート生成 (Python)
```bash
python -m cc_layer.cli.pipeline_run \
  --session-dir {SESSION} --phase report
```

normalize → validate → report_html → report.html の順に実行される。

## デモモード (SubAgent不要)
fixtures にサンプルデータ同梱:
```bash
python -m cc_layer.cli.pipeline_run \
  --session-dir cc_layer/fixtures/session_demo --phase report
```

## SubAgent 起動テンプレート

各 SubAgent は Agent ツールで起動する。
プロンプトテンプレートは `cc_layer/prompts/` 以下を参照。

- `path_designer_agent.md` → Agent(model=sonnet)
- `path_expander_agent.md` → Agent(model=sonnet) × 5 並列
- `persona_agent.md` → Agent(model=opus)
- `narrative_agent.md` → Agent(model=sonnet) × N 並列
- `fact_checker_agent.md` → Agent(model=sonnet) ← **シミュレーション後に必ず実行**
- `report_agent.md` → Agent(model=opus)
- `sns_agent.md` → Agent(model=haiku)

## ファクトチェック（シミュレーション後の必須ステップ）

**multipath_run の直後、レポート生成の前に必ず実行すること。**

```bash
# Step 1: 確率主張を抽出
python -m cc_layer.cli.fact_check extract \
  --session-dir {SESSION}

# Step 2: FactCheckerAgent で検証（SubAgent起動）
#   入力: fact_check_claims.json + multipath_result.json
#   出力: fact_check.json
#   プロンプト: cc_layer/prompts/fact_checker_agent.md

# Step 3: 検証結果を統合
python -m cc_layer.cli.fact_check merge \
  --session-dir {SESSION} \
  --checks {SESSION}/fact_check.json

# Step 4: サマリー確認
python -m cc_layer.cli.fact_check summary \
  --session-dir {SESSION}
```

## データ正規化

SubAgentの出力はフィールド名が揺れる場合がある（例: `final_salary` vs `final_state.annual_income`）。
`pipeline_run --phase normalize` が自動で正規化するため、SubAgent出力後に必ず実行すること。

## レポート生成時の入力データ

report_html.py は以下を読み込む:

1. `multipath_result.json` — シナリオ分岐付きの全パスデータ
2. `swarm_agents.json` — 30人のエージェント定義
3. `swarm/all_actions_round_*.jsonl` — Swarm会話履歴
4. `agent_state.json` — 候補者プロフィール・家族・財務
5. `fact_check_result.json` — ファクトチェック結果（オプション）
6. `macro_trends.json` — マクロトレンド分析（オプション）
