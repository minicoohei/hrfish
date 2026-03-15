# MiroFish Career Simulator - 内部仕様リファレンス

## 概要

MiroFish のマルチパスキャリアシミュレータは、1ラウンド=四半期（3ヶ月）単位で CareerState を更新しながら、確率的ライフイベントとブロッカー制約を適用してキャリアパスを並列シミュレーションする。

---

## 1. LifeEventType 一覧（24種）

### 1-A. スケジュールイベント（PathConfig で設定）

これらは `build_default_paths` / `build_llm_paths` でラウンド番号を指定して配置される。

| # | EventType | 値 | 用途 |
|---|-----------|-----|------|
| 1 | `PROMOTION` | `promotion` | 昇進 |
| 2 | `DEMOTION` | `demotion` | 降格 |
| 3 | `JOB_CHANGE` | `job_change` | 転職・起業 |
| 4 | `STARTUP` | `startup` | 起業（独立イベント） |
| 5 | `LAYOFF` | `layoff` | リストラ |
| 6 | `TRANSFER` | `transfer` | 転勤 |
| 7 | `OVERSEAS_ASSIGNMENT` | `overseas` | 海外赴任 |
| 8 | `SKILL_ACQUISITION` | `skill_acquisition` | スキル習得 |
| 9 | `CAREER_PHASE_CHANGE` | `career_phase_change` | キャリアフェーズ遷移 |

### 1-B. 確率イベント（LifeEventEngine が毎ラウンド判定）

| # | EventType | 発火条件 | 確率/ラウンド | 備考 |
|---|-----------|----------|--------------|------|
| 10 | `ELDER_CARE_START` | 親が75歳以上、介護ブロッカー未発動、親notesに「介護」なし | **5%** | 親ごとに判定 |
| 11 | `ELDER_CARE_END` | 親notesに「介護」あり | **10%** | 平均2.5年で終了 |
| 12 | `MARKET_CRASH` | `cash_buffer > 500` | **2%** | 期待値: 50ラウンド(12.5年)に1回 |
| 13 | `SALARY_INCREASE` | 雇用中（`employer != ""`）、`salary_annual > 0`、4ラウンドごと | **60%** | `salary_increase_pct: 3` |
| 14 | `SALARY_DECREASE` | `stress_level > 0.8` | **15%** | 満足度 -0.2 |
| 15 | `MARRIAGE` | `marital_status == "single"`、28-38歳 | **3%** | 月額支出 +5万 |
| 16 | `CHILD_BIRTH` | 子2人未満、25-42歳 | 既婚: **4%** / 未婚: **1.5%** | |
| 17 | `DIVORCE` | `marital_status == "married"` | 通常: **2%** / ストレス>0.7: **4%** | 資産60%に減少 |
| 18 | `HEALTH_ISSUE` | 常時判定 | 通常: **2%** / ストレス>0.8: **5%** | ストレス+0.3、WLB-0.2 |
| 19 | `SIDE_BUSINESS` | 雇用中、30-45歳、`stress < 0.5` | **2%** | 資産+30万、ストレス+0.1 |
| 20 | `RESKILLING` | 常時判定 | 28-40歳: **4%** / 他: **2%** | 支出+3万、満足度+0.1 |
| 21 | `HOUSING_PURCHASE` | 雇用中、ローンなし、28-42歳、`salary >= 400` | **2%** | ローン = 年収x5、支出+5万 |
| 22 | `PARENTAL_LEAVE` | 0歳の子がいる | **30%** | WLB+0.3、ストレス-0.1 |
| 23 | `RURAL_MIGRATION` | 雇用中、overseas未ブロック | 通常: **1.5%** / ストレス>0.6かつWLB<0.4: **3%** | 年収85%、支出-8万 |
| 24 | `OVERSEAS_MIGRATION` | overseas/startup未ブロック | 35歳以下: **2%** / 他: **0.8%** | 年収130%、支出+10万 |

### 排他制御（同一ラウンド内）

- `MARRIAGE` と `DIVORCE` は共存不可（先に判定された方を優先）
- `RURAL_MIGRATION` と `OVERSEAS_MIGRATION` は共存不可（同上）

---

## 2. BlockerType 一覧（6種）

| # | BlockerType | 条件 | blocked_actions | 有効期限 |
|---|-------------|------|-----------------|----------|
| 1 | `CHILDCARE` | 子が0-6歳 | `overseas_assignment`, `startup`, `long_business_trip` | 条件消滅まで（子が7歳） |
| 2 | `EXAM_PERIOD` | 子が15歳（中3）or 18歳（高3） | `relocation_transfer`, `overseas_assignment` | 4ラウンド（1年） |
| 3 | `EDUCATION_COST` | 子が19-22歳（大学生） | `salary_decrease_job_change`, `startup` | 条件消滅まで（子が23歳） |
| 4 | `MORTGAGE` | `mortgage_remaining > salary_annual * 3` | `startup`, `salary_decrease_job_change` | 条件消滅まで |
| 5 | `ELDER_CARE` | 親notesに「介護」あり | `relocation_transfer`, `overseas_assignment`, `long_business_trip` | 条件消滅まで |
| 6 | `AGE_WALL` | 35歳以上 | 35-44歳: `career_change_to_new_field_easy` / 45歳以上: `career_change_to_new_field` | 恒久 |

---

## 3. スコアリング（DEFAULT_SCORE_WEIGHTS）

パス完了後、`score_path()` で総合スコアを算出しランキングする。

| 指標 | 重み | 計算方法 | キャップ |
|------|------|----------|---------|
| `salary` | **0.25** | `final_salary / 1500` | 1.0（1500万円で最大） |
| `cash` | **0.15** | `max(final_cash_buffer, 0) / 5000` | 1.0（5000万円で最大） |
| `low_stress` | **0.15** | `1.0 - avg_stress` | -- |
| `satisfaction` | **0.25** | `final_satisfaction`（そのまま） | -- |
| `wlb` | **0.20** | `final_wlb`（そのまま） | -- |

- 環境変数 `SCORE_WEIGHT_SALARY` 等で上書き可能
- `score = salary_score * 0.25 + cash_score * 0.15 + (1 - stress) * 0.15 + satisfaction * 0.25 + wlb * 0.20`

---

## 4. イベント適用ロジック（apply_event）

各イベントが CareerState に与える変更の一覧。`state_changes` dict による直接上書きに加え、以下の型別ロジックが先に適用される。

| EventType | 型別ロジック（apply_event内） |
|-----------|------------------------------|
| `PROMOTION` | `years_in_role = 0`、満足度+0.2、ストレス+0.1 |
| `JOB_CHANGE` | `years_in_role = 0`、ストレス+0.15、`satisfaction = 0.6` |
| `LAYOFF` | `employer = ""`、`role = "求職中"`、`salary = 0`、ストレス+0.4、`satisfaction = 0.1` |
| `MARRIAGE` | `marital_status = "married"`、支出+5万、満足度+0.1、ストレス-0.1、配偶者をfamilyに追加 |
| `CHILD_BIRTH` | 支出+8万、WLB-0.2、子（age=0）をfamilyに追加 |
| `ELDER_CARE_START` | ストレス+0.3、WLB-0.3、最初の未介護親を「要介護」マーク |
| `ELDER_CARE_END` | ストレス-0.2、WLB+0.2、親notesクリア |
| `SALARY_INCREASE` | `salary = salary * (1 + pct/100)`（state_changesの`salary_increase_pct`使用） |
| `MARKET_CRASH` | `cash_buffer *= 0.7`（30%減） |
| `DIVORCE` | `marital_status = "divorced"`、ストレス+0.3、満足度-0.15、`cash *= 0.6`、配偶者をfamilyから除去 |
| `HEALTH_ISSUE` | ストレス+0.3、WLB-0.2 |
| `HOUSING_PURCHASE` | state_changesの`mortgage_remaining`と`monthly_expenses`を適用 |
| `OVERSEAS_MIGRATION` | ストレス+0.2、満足度+0.15 |
| `RURAL_MIGRATION` | WLB+0.3、ストレス-0.2 |
| `PARENTAL_LEAVE` | WLB+0.3、ストレス-0.1 |
| `SIDE_BUSINESS` | 資産+30万、ストレス+0.1 |
| `RESKILLING` | 支出+3万、満足度+0.1 |

**適用順序**: 型別ロジック → `state_changes` dictの残りキーを `setattr` → `events_this_round` にdescription追加

---

## 5. ラウンドメカニクス（tick_round）

毎ラウンド開始時に `tick_round()` が呼ばれ、以下を実行する。

### 5-A. 加齢（4ラウンドごと）

```
if current_round % 4 == 0:
    current_age += 1
    years_in_role += 1
    全family memberのage += 1
```

- 1ラウンド = 3ヶ月（四半期）
- 4ラウンド = 1年

### 5-B. 財務計算（毎ラウンド）

```
quarterly_salary = salary_annual / 4
quarterly_expenses = monthly_expenses * 3
cash_buffer += int(quarterly_salary - quarterly_expenses)
```

### 5-C. ローン返済（毎ラウンド、残額 > 0 の場合）

```
quarterly_payment = min(mortgage_remaining, 75)   # 約25万/月
mortgage_remaining -= quarterly_payment
cash_buffer -= quarterly_payment
```

### 5-D. ストレス自然減衰（毎ラウンド）

```
stress_level = max(0.1, stress_level * 0.95)
```

- 毎ラウンド5%減衰、下限0.1

---

## 6. デフォルトパス構成（build_default_paths）

LLM未使用時の3パス固定構成。

| パスID | ラベル | スケジュールイベント |
|--------|--------|---------------------|
| `path_a` | 現職継続 | R8: 昇進（年収 x1.15）、R(mid): 定期昇給（+5%） |
| `path_b` | 同業転職 | R4: 同業界転職（年収 x1.2） |
| `path_c` | 起業挑戦 or 異業種転職 | startupブロックなし → R4: 起業（年収 x0.4）、R(mid): 事業成長（+80%）。ブロック時 → R4: 異業種転職（年収 x0.85） |

- `mid = round_count // 2`
- seed_offset: path_a=0, path_b=100, path_c=200

---

## 7. LLMパス生成（build_llm_paths）

- `num_paths` 個（デフォルト12）のパスをLLMで生成
- Tavily検索で求人市場情報を取得し、実在企業名をパスに反映
- 失敗時は5パスのフォールバック（現職昇進/同業転職/異業種転職/フリーランス/現状維持）
- `run_expanded_and_select()` でスコアリング後 top_n（デフォルト5）を選出

---

## 8. シミュレーション実行フロー

```
initialize(identity, state, path_configs, round_count=40)
  |
  v
run_all()   # ThreadPoolExecutor で並列実行（max_workers=6）
  |
  +-- _run_single_path(config) x N本
  |     |
  |     +-- for round in 1..round_count:
  |           1. state_store.tick_round()      # 加齢・財務・ストレス減衰
  |           2. event_engine.evaluate()       # スケジュール + 確率イベント判定
  |           3. state_store.apply_event()     # 各イベント適用
  |           4. blocker_engine.evaluate()     # ブロッカー再評価
  |           5. state_store.snapshot()        # スナップショット記録
  |
  v
generate_comparison_report()   # 全パスの最終指標比較
score_path()                   # ランキング算出
```

---

## ソースファイル

| ファイル | 役割 |
|----------|------|
| `backend/app/models/life_simulator.py` | Enum定義、データモデル（BaseIdentity, CareerState, LifeEvent, AgentSnapshot, SimulationPath） |
| `backend/app/services/life_event_engine.py` | 確率イベント判定、スケジュールイベント管理、排他制御 |
| `backend/app/services/blocker_engine.py` | 6カテゴリのブロッカー評価 |
| `backend/app/services/agent_state_store.py` | tick_round、apply_event、スナップショット |
| `backend/app/services/multipath_simulator.py` | パス構成、スコアリング、並列実行、比較レポート |

---

## Swarm示唆イベントタイプ（inject_event用）

Swarm-in-the-Loop の Phase C で生成される示唆イベント。`inject_event` CLI で CareerState に注入される。

| タイプ | 説明 |
|--------|------|
| pivot | 事業/職種/業界の転換 |
| opportunity | 新しい機会の発見 |
| risk | リスクの顕在化・早期化 |
| blocker | 新しい制約の発生 |
| acceleration | キャリア進展の加速 |
| deceleration | キャリア進展の減速 |
| network | 人脈/ネットワークの変化 |
| skill_shift | スキルセットの転換 |
| lifestyle_change | ライフスタイルの変化 |

### 許可されたstate_changesフィールド

role, employer, industry, salary_annual, skills, stress_level, job_satisfaction, work_life_balance, side_business, years_in_role

### バリデーション

- confidence >= 0.6 のみ注入
- salary_annual は現在値の3倍以下
- 1ラウンドあたり最大2パスまで変更可能
