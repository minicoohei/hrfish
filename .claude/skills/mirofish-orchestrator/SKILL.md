---
name: mirofish-orchestrator
description: MiroFish CC-Native シミュレーション全体フロー・CLI呼出手順・SubAgent起動手順
---

# MiroFish オーケストレーター Skill

## 概要

CC セッション（Opus）がキャリアシミュレーション全体を制御するための手順書。
Python CLI で決定論的処理を行い、SubAgent でクリエイティブ処理を行うハイブリッド方式。

## モデル階層

| レイヤー | モデル | 役割 |
|---------|--------|------|
| オーケストレーター | Opus | 全体制御、ペルソナ生成、レポート生成 |
| SNSエージェント | Sonnet/Haiku | SNS投稿・反応生成 |
| ルーティン処理 | Haiku | 定型的なラウンドアクション |
| 決定論的処理 | Python CLI | イベント評価、ブロッカー計算、スコアリング |

## 並列SubAgent制限

- **同時起動上限: 10** （それ以上はキューイングされる）
- Phase 1 Step 2（5並列）、Phase 2b（5並列）が最大
- Phase 2a+2b を同時起動する場合は合計6（Opus1+Sonnet5）→ 上限内

## 実行フロー

### Phase -2: 入力収集（AskUserQuestion）

シミュレーション開始前に、ユーザーから必要な情報を収集する。
**必ず `AskUserQuestion` ツールを使って対話的に確認すること。**

#### 必須入力（AskUserQuestionで確認）

1. **ドキュメント**: 「履歴書や職務経歴書のファイルパスを教えてください」
2. **シミュレーション要件**: 「どのようなキャリアシミュレーションを行いたいですか？（例: IT業界でのマネジメント転換、海外転職の可能性）」
3. **候補者基本情報**（ドキュメントから読み取れない場合）:
   - 年齢、性別
   - 現在の年収
   - 家族構成（配偶者、子供の年齢）
   - 住宅ローン残高（該当する場合）
4. **シミュレーション設定**（オプション、デフォルトあり）:
   - パス数（デフォルト: 5）
   - 重視する指標（年収/ワークライフバランス/満足度）

#### 収集フロー

```
AskUserQuestion("シミュレーションを開始します。以下を教えてください:

1. 履歴書・職務経歴書のファイルパス
2. シミュレーションの目的（例: 「マネジメントキャリアへの転換可能性を探りたい」）

※ファイルがない場合は、経歴を直接テキストで入力いただいてもOKです。")

→ ユーザー回答

AskUserQuestion("ありがとうございます。追加で確認させてください:

- 現在の年収（概算でOK）:
- 家族構成（配偶者・お子さんの有無と年齢）:
- 住宅ローン残高（該当する場合）:

※答えたくない項目はスキップで構いません。")

→ ユーザー回答 → Phase -1 へ
```

### Zep CLI ツール（全Phase で使用）

```bash
# エンティティ一覧取得
python -m cc_layer.cli.zep_search --graph-id {graph_id} --mode entities

# クイック検索（セマンティック + BM25）
python -m cc_layer.cli.zep_search --graph-id {graph_id} --query "検索クエリ" --mode quick

# 深い洞察検索（LLMサブクエスチョン分解）
python -m cc_layer.cli.zep_search --graph-id {graph_id} --query "分析クエリ" --mode insight --requirement "要件"

# 全体スナップショット
python -m cc_layer.cli.zep_search --graph-id {graph_id} --mode panorama

# Zepへの書き込み（facts）
python -m cc_layer.cli.state_export --state-file ... --format zep-facts | \
  python -m cc_layer.cli.zep_write --graph-id {graph_id} --stdin-facts

# Zepへの書き込み（アクティビティ）
python -m cc_layer.cli.zep_write --graph-id {graph_id} \
  --activity '{"agent_name":"名前","action":"Published a post","content":"投稿内容"}'
```

### Phase -1: ドキュメント前処理 & グラフ構築（新規パイプライン）

**設計方針: OpenAI API不使用。** 決定論的処理はPython CLI、クリエイティブ処理はClaudeのSubAgentが担当。

```bash
# 1. ドキュメントからテキスト抽出（Python CLI — OpenAI不要）
python -m cc_layer.cli.text_process \
  --input-files resume.pdf cover_letter.txt \
  --mode extract --preprocess \
  --output-file cc_layer/state/session_xxx/extracted_text.txt

# 2. デフォルトオントロジー生成（Python CLI — OpenAI不要）
python -m cc_layer.cli.ontology_generate \
  --default \
  --output-file cc_layer/state/session_xxx/ontology.json

# 3. Zepナレッジグラフ構築（Python CLI — Zep API使用、OpenAI不要）
python -m cc_layer.cli.graph_build \
  --text-file cc_layer/state/session_xxx/extracted_text.txt \
  --ontology-file cc_layer/state/session_xxx/ontology.json \
  --graph-name "session_xxx" \
  --output-file cc_layer/state/session_xxx/graph_info.json
# → graph_id を取得

# 4. エンティティからベースプロフィール生成（Python CLI — OpenAI不要）
python -m cc_layer.cli.profile_generate \
  --graph-id {graph_id} \
  --no-llm \
  --output-file cc_layer/state/session_xxx/profiles.json
```

#### 4.5. シミュレーション設定生成（SubAgent — OpenAI不要）

`sim_config_generate` CLI（OpenAI依存）の代わりに、SubAgentがSimulationParameters JSONを直接生成。

```
Agent(model=sonnet, prompt="""
Skills: mirofish-career を参照。
cc_layer/prompts/config_agent.md のフォーマットに従い、
以下からSimulationParameters JSONを生成してください。

graph_id: {graph_id}
requirement: {requirement}
profiles: {profiles_json}
document_text: {document_text}

出力: cc_layer/state/session_xxx/sim_config.json に書き出してください。
""")
```

#### 5. ナレッジキュレーション（Tavily外部検索 — 前提条件収集）

**シミュレーションの現実性を担保する重要ステップ。** Tavilyで最新の労働市場データ・業界動向を取得し、
PathDesigner/PathExpander の入力コンテキストに含める。

```bash
# 5a. 業界ナレッジ収集（Tavily + LLM パイプライン）
#   候補者のコンテキストに基づき、関連する業界データを構造化して保存
python -m cc_layer.cli.knowledge_curate \
  --ontology-file cc_layer/state/session_xxx/ontology.json \
  --candidate-context "{age}歳、{current_role}、{industry}業界{years}年" \
  --output-dir cc_layer/state/session_xxx/knowledge/

# 5b. 転職市場データ取得
python -m cc_layer.cli.external_search \
  --mode job-market --profession "{profession}" --industry "{industry}"
# → cc_layer/state/session_xxx/knowledge/job_market.json に保存

# 5c. 業界ニュース・トレンド取得
python -m cc_layer.cli.external_search \
  --mode industry-news --industry "{industry}" --keywords "{keywords}"
# → cc_layer/state/session_xxx/knowledge/industry_news.json に保存

# 5d. HR動向（リスキリング、採用トレンドなど）
python -m cc_layer.cli.external_search \
  --mode hr-trends --keywords "{relevant_keywords}"
# → cc_layer/state/session_xxx/knowledge/hr_trends.json に保存
```

**5b-5dは並列実行可能。** 結果は `knowledge/` ディレクトリに保存し、後続PhaseのSubAgentに渡す。

#### 5e. ナレッジ統合（Phase 1 への橋渡し）

```bash
# 収集したナレッジを候補者コンテキストに注入する形式で取得
python -m cc_layer.cli.knowledge_search \
  --candidate-context "{age}歳、{current_role}" \
  --injection-point "top_player" \
  --max-chars 3000
# → knowledge_context テキストとして Phase 1 の SubAgent に渡す
```

**TAVILY_API_KEY未設定時:** `external_search` はエラーを返す。`knowledge_curate` も Tavily依存部分は失敗するが、
既存のローカルナレッジファイル（`preset_knowledge/`）があれば `knowledge_search` で利用可能。
Tavilyなしでも最低限のシミュレーションは可能（精度は低下する）。

### Phase 0: 入力解析 & 初期化

```bash
# 1. Zep からエンティティ取得してプロフィール構築
python -m cc_layer.cli.zep_search --graph-id {graph_id} --mode entities

# 2. プロフィール + フォーム入力から初期状態生成
python -m cc_layer.cli.sim_init \
  --profile '{"name":"田中太郎","age":35,"current_role":"シニアエンジニア",...}' \
  --form '{"family_members":[...],"marital_status":"married",...}' \
  --seed 42 \
  --output-dir cc_layer/state/session_xxx
```

**Zep操作（mirofish-zep参照）:** エンティティ読み取り → プロフィール構築

### Phase 1: マルチパスシミュレーション（SubAgent + Python スコアリング）

旧方式（Python決定論的480tick）を廃止。Claudeが実際にキャリアについて推論する。

#### Step 1: パス定義（Sonnet — 1回）

```
Agent(model=sonnet, prompt="""
cc_layer/prompts/path_designer_agent.md のフォーマットに従い、
候補者の取りうるキャリアパスを5つ設計してください。

graph_id: {graph_id}
identity: {identity_json}
profiles: {profiles_json}
requirement: {requirement}
document_text: {document_text}

## 現実世界コンテキスト（Tavily取得済み）
knowledge_context: {knowledge_context}
job_market: {job_market_json}
industry_trends: {industry_news_json}

※上記データは最新の労働市場・業界動向。パス設計時に現実の求人市場・トレンドを反映すること。

出力: cc_layer/state/session_xxx/path_designs.json
""")
```

#### Step 1.5: 報酬水準リファレンス生成（Python CLI）

パス展開前に、候補者コンテキストとパス設計から報酬水準テーブルを生成:

```bash
python -m cc_layer.cli.compensation_fetch \
  --mode build \
  --candidate-context "{age}歳、{current_role}、年収{income}万" \
  --paths-file cc_layer/state/session_xxx/path_designs.json \
  --format prompt \
  > cc_layer/state/session_xxx/compensation_ref.md
```

TAVILY_API_KEY が設定されている場合、`--mode update` で Web から最新データを補完可能:

```bash
python -m cc_layer.cli.compensation_fetch \
  --mode update \
  --candidate-context "{age}歳、{current_role}" \
  --paths-file cc_layer/state/session_xxx/path_designs.json
```

#### Step 2: パス展開（Sonnet × 5 並列）

path_designs.json の各パスに対して並列起動:

```
Agent(model=sonnet, prompt="""
cc_layer/prompts/path_expander_agent.md のフォーマットに従い、
以下のキャリアパスを10年間・4期に分けて展開してください。

graph_id: {graph_id}
identity: {identity_json}
path_design: {path_design_json}
requirement: {requirement}

## 報酬水準リファレンス（compensation_fetch生成）
{compensation_ref_md}

## 現実世界コンテキスト（Tavily取得済み）
knowledge_context: {knowledge_context}
job_market: {job_market_json}

※年収水準は報酬水準リファレンスを参照し、現実的な数値を使うこと。
※転職難易度・業界成長率などは現実世界コンテキストを参照。

出力: cc_layer/state/session_xxx/path_expanded_{path_id}.json
""")
```

**5パスを単一メッセージ内の5つの Agent ツールで同時起動**

#### Step 3: スコアリング & ランキング（Python CLI）

```bash
python -m cc_layer.cli.path_score \
  --input-dir cc_layer/state/session_xxx/ \
  --designs-file cc_layer/state/session_xxx/path_designs.json \
  --top-n 5 \
  --output-file cc_layer/state/session_xxx/multipath_result.json
```

**LLM呼び出し: 1+5=6回** （旧方式の480tickから大幅削減、かつClaudeが実際に推論）

### Phase 1.5: SNS Agent Swarm（Tmux × 10 = 50キャラ）

50キャラクターがSNS上で投稿・反応・フォローし合う社会シミュレーション。
10のTmux CCセッション（各5キャラ）がラウンド単位でファイルベースIPCで同期。

#### 準備

```bash
# 1. エージェント定義JSON作成（profiles.jsonベース + 追加NPC）
#    ConfigAgent or Orchestratorが生成

# 2. Swarm初期化（エージェントをワーカーに分配）
python -m cc_layer.cli.swarm_sync --mode init \
  --session-dir cc_layer/state/session_xxx \
  --agents-file cc_layer/state/session_xxx/swarm_agents.json \
  --num-workers 10

# 3. 10 Tmuxセッション起動
./.claude/scripts/swarm_launch.sh cc_layer/state/session_xxx 20
```

#### ラウンドループ（Orchestratorが制御）

```bash
for ROUND in $(seq 1 20); do
  # 1. ラウンド開始シグナル
  python -m cc_layer.cli.swarm_sync --mode prepare-round \
    --session-dir cc_layer/state/session_xxx --round-num $ROUND

  # 2. 全ワーカー完了を待機（ポーリング）
  # check-round の all_done が true になるまで
  python -m cc_layer.cli.swarm_sync --mode check-round \
    --session-dir cc_layer/state/session_xxx \
    --round-num $ROUND --num-workers 10

  # 3. アクションをマージ → 次ラウンドのタイムライン生成
  python -m cc_layer.cli.swarm_sync --mode merge \
    --session-dir cc_layer/state/session_xxx \
    --round-num $ROUND --num-workers 10
done
```

#### 完了後

```bash
# 全アクションをZep形式でエクスポート
python -m cc_layer.cli.swarm_sync --mode export-zep \
  --session-dir cc_layer/state/session_xxx \
  --output-file cc_layer/state/session_xxx/swarm_episodes.json

# Zepへ書き込み
python -m cc_layer.cli.zep_write --graph-id {graph_id} \
  --stdin-facts < cc_layer/state/session_xxx/swarm_episodes.json
```

#### 通信アーキテクチャ

```
Orchestrator ──prepare-round──▶ ready file
                                  │
     ┌────────────────────────────┼────────────────────────┐
     ▼                            ▼                        ▼
  Worker 0                     Worker 1      ...        Worker 9
  read-timeline               read-timeline             read-timeline
  → SubAgent×5               → SubAgent×5              → SubAgent×5
  write-actions               write-actions             write-actions
     │                            │                        │
     └────────────────────────────┼────────────────────────┘
                                  │
Orchestrator ◀──check-round───── │
             ◀──merge──────────── ▼
                          timeline_round_N+1.json
```

**コスト概算:** 50キャラ × 20ラウンド = 1000アクション。各ワーカーが5キャラ分を1回のSubAgent呼出で生成する場合、10ワーカー × 20ラウンド = 200 SubAgent呼出。

### Phase 2: クリエイティブ後処理（SubAgent 並列）

multipath_result.json を読み込み、top N パスに対してクリエイティブ処理を実行。

#### 2a. ペルソナ深掘り & プロフィール拡張（Opus）

Phase -1 の `profile_generate --no-llm` で生成したベースプロフィールを、
Zep RAG + シミュレーション結果を使ってリッチなナラティブペルソナに拡張する。
**OpenAI の OasisProfileGenerator が担っていたLLMプロフィール生成をこのSubAgentが置換。**

```
Agent(model=opus, prompt="""
Skills: mirofish-zep, mirofish-persona を参照。

以下のシミュレーション結果とベースプロフィールから、候補者のペルソナを深掘りしてください。

1. Zep RAGで候補者の背景情報（学歴、職歴、関係性）を検索
2. ベースプロフィールの bio/persona を詳細なナラティブに拡張
3. 構造的テンプレートに内的独白・心理描写を追加し、人間味のあるナラティブに拡張

graph_id: {graph_id}
identity: {identity_json}
base_profiles: {profiles_json}
final_states: {top_paths_final_states_json}
""")
```

#### 2b. パスナラティブ生成（Sonnet × N 並列）

top N パスそれぞれに対して並列起動：

```
Agent(model=sonnet, prompt="""
Skills: mirofish-zep, mirofish-persona, mirofish-career を参照。

以下のキャリアパスの全スナップショットから、10年間のキャリアストーリーを
1000-2000字で生成してください。イベントの因果関係、心情の変化、
ブロッカーによる葛藤を描写してください。

パス: {path_label}
identity: {identity_json}
snapshots: {path_snapshots_json}
""")
```

**並列起動のポイント:** 単一メッセージ内で複数の Agent ツールを呼ぶ

#### 2c. SNS投稿生成（Haiku — オプション）

イベント発生ラウンドのみ、代表的なSNS投稿を生成：

```
Agent(model=haiku, prompt="""
あなたは以下のペルソナを持つ人物です。
{persona_text}

今期の出来事「{event_description}」について、
{platform}（Twitter/Reddit）に投稿してください。
""")
```

### Phase 3: レポート生成（単一 Opus SubAgent）

```
Agent(model=opus, prompt="""
Skills: mirofish-zep, mirofish-report, mirofish-career を参照。

以下のデータからキャリアシミュレーションレポートを生成してください。
Zep MCP を使ってグラフから追加情報を検索できます。

graph_id: {graph_id}
multipath_result: {multipath_result_json}
narratives: {narratives_json}
simulation_requirement: {requirement}

出力: cc_layer/state/session_xxx/report.md に書き出してください。
""")
```

**Zep操作:** InsightForge（分析セクション）、Panorama（概要）、QuickSearch（補足）

### Phase 4: 結果提示 & 対話モード

- レポートの要約をユーザーに提示
- 各パスのスコアとランキングを表示
- 質問に対してZep MCPで追加検索して回答

## 状態管理

```
cc_layer/state/session_xxx/
├── extracted_text.txt     ← text_process で生成
├── ontology.json          ← ontology_generate で生成
├── graph_info.json        ← graph_build で生成
├── profiles.json          ← profile_generate で生成
├── sim_config.json        ← sim_config_generate で生成
├── agent_state.json       ← sim_init で生成
├── multipath_result.json  ← multipath_run で生成
├── narrative_*.md         ← NarrativeAgent(Sonnet) で生成
├── persona_*.md           ← PersonaAgent(Opus) で生成
├── report.md              ← ReportAgent(Opus) で生成
├── knowledge/             ← knowledge_curate + external_search で生成
│   ├── job_market.json    ← 転職市場データ（Tavily）
│   ├── industry_news.json ← 業界ニュース（Tavily）
│   └── hr_trends.json     ← HR動向（Tavily）
└── knowledge_context.txt  ← knowledge_search で統合済みテキスト
```

### Zep 同期タイミング

| タイミング | 操作 | コマンド |
|-----------|------|---------|
| Phase 0 完了後 | 初期状態をZepへ書込 | `python -m cc_layer.cli.state_export --state-file ... --format zep-facts` → Zep MCP |
| Phase 1 完了後 | シミュレーション結果をZepへ書込 | 同上（最終状態で再実行） |
| Phase 3 中 | Zepからグラフ検索 | Zep MCP の search / insight_forge |

## エラーハンドリング

- CLI の exit code が 1 → stderr を確認して原因特定
- SubAgent タイムアウト → 再起動して直前の状態から再実行
- multipath_run.py の部分失敗 → `failed_paths` フィールドを確認、成功パスのみで続行

## CLI ヘルプ

全CLI は `--help` でself-documenting:
```bash
# 前処理パイプライン
python -m cc_layer.cli.text_process --help
python -m cc_layer.cli.ontology_generate --help
python -m cc_layer.cli.graph_build --help
python -m cc_layer.cli.profile_generate --help
python -m cc_layer.cli.sim_config_generate --help

# シミュレーション
python -m cc_layer.cli.sim_init --help
python -m cc_layer.cli.sim_tick --help
python -m cc_layer.cli.multipath_run --help
python -m cc_layer.cli.inject_event --help

# Zep連携
python -m cc_layer.cli.state_export --help
python -m cc_layer.cli.state_import --help
python -m cc_layer.cli.zep_search --help
python -m cc_layer.cli.zep_write --help

# ナレッジ
python -m cc_layer.cli.knowledge_curate --help
python -m cc_layer.cli.knowledge_search --help
python -m cc_layer.cli.external_search --help
python -m cc_layer.cli.compensation_fetch --help
```

## Phase X: Swarm-in-the-Loop 複眼評価（オプション）

マルチパスシミュレーション後に、Swarmエージェントの議論でパスの内容を動的に変化させる。

### 実行フロー

各ラウンドで Phase A→B→C→D のサイクルを回す:

- **Phase A**: `sim_tick` × 5パス並列（Python CLI, 0 token）
- **Phase B**: Swarm議論（Sonnet SubAgent × 2-3）
  - プロンプト: `cc_layer/prompts/swarm_round_agent.md`
- **Phase C**: 影響抽出（Opus SubAgent × 1）
  - プロンプト: `cc_layer/prompts/influence_extractor.md`
- **Phase D**: パス注入（`inject_event` CLI）

### 関連CLI

- `python -m cc_layer.cli.inject_event` — 示唆イベントをCareerStateに注入
- `python -m cc_layer.cli.swarm_sync --mode export-conversation` — 会話ログ出力
- `python -m cc_layer.cli.sanitizer` — Webコンテンツサニタイズ

### 詳細

フロー全体: `cc_layer/prompts/multipath_loop_orchestrator.md`
設計仕様: `docs/superpowers/specs/2026-03-14-swarm-in-the-loop-design.md`
