# MultipathLoopOrchestrator プロンプトテンプレート

## モデル: opus（オーケストレーター本体）

## 概要

Swarm-in-the-Loop シミュレーションのメインループを制御する。
Phase 0 完了後、各ラウンドで Phase A → B → C → D を順次実行する。

## 前提条件

### セッションディレクトリ構造

```
{session_dir}/
├── agent_state.json          ← Phase 0 で生成済み
├── agents.json               ← Swarm エージェント定義
├── paths/
│   ├── path_a.json
│   ├── path_b.json
│   ├── path_c.json
│   ├── path_d.json
│   └── path_e.json
├── swarm/
│   ├── round_01/
│   │   ├── actions.jsonl     ← Phase B 出力
│   │   └── suggestions.json  ← Phase C 出力
│   └── ...
├── checkpoint.json           ← 進捗管理
└── summary_round_10.md       ← 10ラウンド中間レポート
```

### Phase 0 完了確認

```bash
# agent_state.json と paths/ が存在すること
test -f {session_dir}/agent_state.json && test -d {session_dir}/paths && echo "Phase 0 OK"
```

## 実行フロー

全 {total_rounds} ラウンドについて以下を繰り返す。

### Phase A: シミュレーションティック

Python CLI でパス状態を1ラウンド進める。トークン消費なし（deterministic）。

```bash
python -m cc_layer.cli.sim_tick \
  --session-dir {session_dir} \
  --round-num {round_num}
```

**出力**: 各パスの状態ファイルが更新される。

### Phase B: Swarm 議論（SNS会話生成）

**モデル: sonnet**

1. Zep から候補者背景と前ラウンドの文脈を取得:

```bash
python -m cc_layer.cli.zep_search \
  --graph-id {graph_id} \
  --query "{candidate_name} のキャリア状況 ラウンド{round_num}" \
  --mode quick
```

2. Swarm エージェントの会話を生成:

```bash
python -m cc_layer.cli.swarm_sync --mode export-conversation \
  --session-dir {session_dir} \
  --round-num {round_num} \
  --prompt-file cc_layer/prompts/swarm_round_agent.md
```

**出力**: `{session_dir}/swarm/round_{round_num}/actions.jsonl`

### Phase C: 影響抽出（会話分析）

**モデル: opus**

1. Zep から過去の提案履歴を取得:

```bash
python -m cc_layer.cli.zep_search \
  --graph-id {graph_id} \
  --query "過去の修正提案 {candidate_name}" \
  --mode quick
```

2. 会話ログからパス修正提案を抽出:

```bash
python -m cc_layer.cli.swarm_sync --mode export-conversation \
  --session-dir {session_dir} \
  --round-num {round_num} \
  --prompt-file cc_layer/prompts/influence_extractor.md \
  --phase extract
```

**出力**: `{session_dir}/swarm/round_{round_num}/suggestions.json`

### Phase D: 状態反映・記録

1. 提案をパス状態に反映（confidence >= 0.6 のみ）:

```bash
python -m cc_layer.cli.inject_event \
  --session-dir {session_dir} \
  --round-num {round_num} \
  --suggestions-file {session_dir}/swarm/round_{round_num}/suggestions.json
```

2. ラウンド結果を Zep に書き込み:

```bash
python -m cc_layer.cli.zep_write \
  --graph-id {graph_id} \
  --activity '{"round": {round_num}, "action": "SimulationRound", "summary": "ラウンド{round_num}完了"}'
```

## モデル割り当て

| フェーズ | モデル | トークン消費 |
|---------|--------|------------|
| Phase A (sim_tick) | Python CLI | 0（deterministic） |
| Phase B (swarm) | sonnet | 中（会話生成） |
| Phase C (extract) | opus | 中（分析・抽出） |
| Phase D (inject) | Python CLI + Zep | 低（書き込みのみ） |

## エラー回復

### チェックポイント管理

各ラウンド完了時に `checkpoint.json` を更新する:

```bash
# ラウンド完了後に記録
python -c "
import json
cp = {'last_completed_round': {round_num}, 'status': 'ok', 'timestamp': '$(date -Iseconds)'}
with open('{session_dir}/checkpoint.json', 'w') as f:
    json.dump(cp, f, indent=2)
"
```

### 中断からの再開

```bash
# checkpoint.json から最後の完了ラウンドを取得
LAST=$(python -c "import json; print(json.load(open('{session_dir}/checkpoint.json'))['last_completed_round'])")
echo "Resume from round $((LAST + 1))"
```

### フェーズ別リトライ

- **Phase A 失敗**: sim_tick をリトライ（deterministic なので冪等）
- **Phase B 失敗**: swarm_sync をリトライ（actions.jsonl を再生成）
- **Phase C 失敗**: influence_extractor をリトライ（suggestions.json を再生成）
- **Phase D 失敗**: inject_event をリトライ（冪等に設計されている）

各フェーズは最大3回リトライ。3回失敗した場合はユーザーに報告して停止する。

## 10ラウンドチェックポイント

ラウンド10完了時にユーザーに中間サマリーを表示する:

```bash
# 中間サマリー生成
python -m cc_layer.cli.sim_tick \
  --session-dir {session_dir} \
  --round-num 10 \
  --summary-only > {session_dir}/summary_round_10.md
```

**表示内容:**
- 各パスの現在状態（役職、年収、満足度）
- Swarm議論のハイライト（最も議論されたトピック）
- Phase C で採用された提案の一覧
- 残りラウンドの見通し

ユーザー確認後、ラウンド11以降を続行する。

## 入力変数

```
session_dir: {session_dir}
graph_id: {graph_id}
candidate_name: {candidate_name}
total_rounds: {total_rounds}
round_num: {round_num}            ← ループ内で動的に更新
```
