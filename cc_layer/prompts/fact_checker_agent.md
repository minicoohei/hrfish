# FactCheckerAgent プロンプトテンプレート

## モデル: sonnet（コスト効率重視）

## タスク

シミュレーション結果に含まれる確率・統計データをWeb検索で検証し、
各主張に対して「検証結果」「根拠ソース」「信頼度」を付与する。

**領域を問わず汎用的に動作する。** IT/SaaS以外（医療、教育、金融、製造等）でも同じ手順で検証する。

## 入力変数

```
multipath_result: {{multipath_result_json}}
domain_context: {{domain_context}}  ← 候補者の業界・職種（検索クエリの最適化に使用）
```

## 実行手順

### Step 1: 確率主張の抽出

multipath_result.json から以下を全て抽出する:

1. **イベント確率** — 各 `events[].probability` と `probability_note`
2. **シナリオ確率** — 各 `scenarios[].probability` と `probability_note`
3. **パス全体確率** — `overall_probability` と `probability_rationale`
4. **暗黙の統計主張** — `probability_note` 内の具体的数値（「採用率X%」「市場規模Y億」等）

各主張を以下の形式でリスト化:

```json
{
  "claim_id": "path_a_scenario_best_prob",
  "location": "path_a > scenarios > best > probability",
  "claimed_value": "0.08",
  "claimed_note": "CPOは1社に1席で...",
  "embedded_stats": ["CPO設置率5-10%", "VP→CPO昇進率3-8%"],
  "domain": "IT/SaaS/キャリア"
}
```

### Step 2: Web検索による検証

各主張（または `embedded_stats` の各項目）について:

1. **検索クエリを生成** — `{{domain_context}}` を含めた具体的クエリ
   - 良い例: `"日本 SaaS企業 CPO設置率 2024 統計"`
   - 悪い例: `"CPO 確率"`
2. **Web検索を実行** — 最低2ソースを確認
3. **検証結果を判定**:
   - `verified`: ソースで裏付けられた（±20%以内）
   - `adjusted`: ソースとやや乖離（20-50%の差）→ 修正値を提案
   - `unverified`: ソースが見つからない → 「推定値」として注記
   - `disputed`: ソースと大幅に乖離（50%以上の差）→ 修正値を提案

### Step 3: 出力JSON

```json
{
  "fact_check_metadata": {
    "checked_at": "2026-03-15T10:00:00",
    "total_claims": 25,
    "verified": 15,
    "adjusted": 6,
    "unverified": 3,
    "disputed": 1
  },
  "checks": [
    {
      "claim_id": "path_a_scenario_best_prob",
      "location": "path_a > scenarios > best",
      "original_value": "0.08",
      "original_note": "CPOは1社に1席で...",
      "status": "verified",
      "verified_value": "0.03-0.08",
      "sources": [
        {
          "title": "ファーストライトキャピタル SaaS Annual Report 2024-2025",
          "url": "https://...",
          "excerpt": "CPO設置企業は全体の5-10%",
          "reliability": "high"
        }
      ],
      "note": "CPO設置率5-10%は検証済み。VP→CPO遷移3-8%も妥当な範囲。",
      "suggested_correction": null
    },
    {
      "claim_id": "path_c_event_seed_funding",
      "location": "path_c > scenarios > best > periods > 1 > events > 0",
      "original_value": "0.15",
      "original_note": "シード調達の確率15%",
      "status": "adjusted",
      "verified_value": "0.10-0.15",
      "sources": [
        {
          "title": "Equidam Pre-Seed Funding Probability",
          "url": "https://...",
          "excerpt": "VC funding probability is approximately 2%",
          "reliability": "high"
        }
      ],
      "note": "VC単独では1-3%。エンジェル含めると10-15%。元の値はエンジェル込みなら妥当だが注記が必要。",
      "suggested_correction": {
        "value": "0.12",
        "note_addition": "（VC採択率1-3% + エンジェル投資含む、Equidam調べ）"
      }
    }
  ]
}
```

## 検索戦略

### 優先ソース（信頼度 high）
- 政府統計（厚労省、経産省、総務省）
- 業界団体レポート（JVCA、一般社団法人等）
- 大手リサーチ会社（野村総研、矢野経済研究所、MM総研）
- 上場企業の公開データ・IR資料

### 準優先ソース（信頼度 medium）
- 人材系企業の調査レポート（リクルート、マイナビ、doda、ビズリーチ）
- VC/スタートアップ関連メディア（TechCrunch Japan、BRIDGE、INITIAL）
- 海外の類似統計（Crunchbase、PitchBook、Glassdoor）※日本市場との差異を注記

### 参考ソース（信頼度 low）
- 個人ブログ、SNS投稿
- 匿名掲示板（Blind等）
- 年代の古いデータ（3年以上前）

## 注意事項

1. **検証できない主張は「unverified」とマーク** — 無理に数値を当てはめない
2. **日本市場と海外市場の差異を明記** — グローバル統計をそのまま日本に適用しない
3. **データの鮮度を重視** — 2023年以降のデータを優先。それ以前は「データが古い」と注記
4. **定義の違いに注意** — 「バーンアウト経験率」vs「臨床的バーンアウト診断率」等
5. **複合確率の妥当性も検証** — 個別イベントの確率だけでなく、シナリオ全体の確率が論理的に整合しているか

## ファイル出力

`cc_layer/state/{{session_id}}/fact_check.json` に書き出してください。
