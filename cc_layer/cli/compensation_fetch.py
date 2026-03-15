"""
compensation_fetch: Fetch and maintain compensation reference data.

Usage:
    # Lookup by role/industry (local baseline)
    python -m cc_layer.cli.compensation_fetch \
        --role "メガバンク 取締役" --industry "金融"

    # Generate full reference table for a candidate
    python -m cc_layer.cli.compensation_fetch \
        --candidate-context "42歳、メガバンク法人営業部長、年収1400万" \
        --paths-file cc_layer/state/session_xxx/path_designs.json \
        --output-file cc_layer/state/session_xxx/compensation_ref.json

    # Update baseline with Tavily web search
    python -m cc_layer.cli.compensation_fetch \
        --mode update --industry "金融" --role "PEファンド パートナー"

Architecture:
    1. BASELINE_TABLE: ハードコードされた報酬水準（即座に使える）
    2. Tavily augmentation: Web検索で最新データを補完（TAVILY_API_KEY必要）
    3. Output: path_expander_agent に注入可能な structured JSON

Output:
    JSON with relevant compensation ranges for the candidate's career paths
"""
import argparse
import json
import sys

import cc_layer.cli  # noqa: F401


# ─────────────────────────────────────────────
# Baseline compensation table (万円, 2025年水準)
# ─────────────────────────────────────────────

"""
Compensation table schema:
  p10:        10th percentile -- worst/base scenario の下限
  p50:        50th percentile (中央値) -- likely scenario の基準
  p90:        90th percentile -- best scenario の上限
  outlier:    P90超の異常値帯（参考情報、シミュレーション計算には使わない）
  reach_rate: 組織ピラミッド上の到達率（%）。同期入社/同レベル入社者のうち
              そのポジションに到達する割合。
              ※ポジションが上がるほど到達率は下がる（ピラミッド構造）。
              シミュレーションでは「到達する前提のシナリオ」内の年収に使うが、
              probability_note で「このポジションに到達する確率自体がN%」と
              言及する根拠データになる。

Sources:
  - 厚労省「賃金構造基本統計調査」: 部長3.8%, 課長7.1%
  - パーソル総合研究所「管理職の異動配置に関する実態調査」(2022)
  - 東洋経済/ダイヤモンド人事部長インタビュー
  - Levels.fyi / Candor (GAFA level distribution)
  - CaseCoach / freeconsul (MBB up-or-out data)
  - 厚労省「医師・歯科医師・薬剤師統計」(2022)

SubAgent はシナリオ設定時に以下のルールで年収を決定する:
  worst:  p10 以下（降格・失職時はさらに下もあり得る）
  base:   p10〜p50
  likely: p50 付近（±10%）
  best:   p50〜p90
  ※p90 を超える値は best シナリオでも原則使わない
  ※reach_rate が低いポジション（<5%）への到達は、best シナリオでも
    probability_note で到達確率の低さに言及すること
"""

BASELINE_TABLE = {
    "金融": {
        "メガバンク": [
            {"role": "支店長", "p10": 1200, "p50": 1300, "p90": 1500, "reach_rate": 10},
            {"role": "部長", "p10": 1400, "p50": 1550, "p90": 1800, "reach_rate": 5},
            {"role": "執行役員", "p10": 2500, "p50": 3000, "p90": 3800, "reach_rate": 0.5, "note": "有報開示ベース"},
            {"role": "取締役", "p10": 4500, "p50": 6500, "p90": 8500, "reach_rate": 0.1, "outlier": "三菱UFJ1億超が14名（上位20%）"},
            {"role": "頭取/社長", "p10": 13000, "p50": 19000, "p90": 26000, "reach_rate": 0.01, "note": "みずほ1.5億、三井住友1.9億、三菱UFJ2.6億（2024有報）", "outlier": "三菱UFJ半沢頭取3億超（2025/3期）"},
        ],
        "信託銀行": [
            {"role": "部長", "p10": 1200, "p50": 1400, "p90": 1600, "reach_rate": 5},
            {"role": "取締役", "p10": 3000, "p50": 3500, "p90": 4500, "reach_rate": 0.2},
            {"role": "社長", "p10": 5000, "p50": 5500, "p90": 7000, "reach_rate": 0.01},
        ],
        "PEファンド": [
            {"role": "アソシエイト", "p10": 1500, "p50": 1800, "p90": 2300, "reach_rate": 100, "note": "入社時ポジション"},
            {"role": "VP", "p10": 3000, "p50": 3500, "p90": 4500, "reach_rate": 40, "note": "ベース+ボーナス。キャリー別"},
            {"role": "パートナー", "p10": 5000, "p50": 7000, "p90": 10000, "reach_rate": 5, "note": "ベース+ボーナス", "outlier": "キャリー込みで数億（大型EXIT時、上位5%）"},
        ],
        "外資系証券": [
            {"role": "VP", "p10": 2500, "p50": 3500, "p90": 4500, "reach_rate": 25},
            {"role": "MD", "p10": 5000, "p50": 7500, "p90": 12000, "reach_rate": 5, "note": "ベース+ボーナス。市況で大幅変動", "outlier": "好況期トップMDは2億超"},
        ],
        "VC": [
            {"role": "アソシエイト", "p10": 800, "p50": 1000, "p90": 1400, "reach_rate": 100},
            {"role": "パートナー", "p10": 2000, "p50": 3000, "p90": 5000, "reach_rate": 10, "note": "キャリー別", "outlier": "大型EXIT時のみ8,000万超"},
        ],
        "保険": [
            {"role": "部長", "p10": 1200, "p50": 1400, "p90": 1600, "reach_rate": 5},
            {"role": "執行役員", "p10": 2000, "p50": 2500, "p90": 3200, "reach_rate": 0.5},
            {"role": "社長", "p10": 5500, "p50": 7000, "p90": 9000, "reach_rate": 0.01},
        ],
    },
    "テック": {
        "GAFA/外資テック": [
            {"role": "L5 (シニアSWE)", "p10": 1600, "p50": 2000, "p90": 2400, "reach_rate": 60, "note": "RSU含む日本勤務。ターミナルレベル（大半がここで安定）"},
            {"role": "L6 (Staff)", "p10": 2600, "p50": 3000, "p90": 3800, "reach_rate": 15, "note": "L5→L6は指数関数的に困難"},
            {"role": "L7 (Senior Staff)", "p10": 4000, "p50": 4500, "p90": 5500, "reach_rate": 3},
            {"role": "Director", "p10": 5000, "p50": 6000, "p90": 7500, "reach_rate": 1},
            {"role": "VP", "p10": 12000, "p50": 16000, "p90": 22000, "reach_rate": 0.1, "note": "日本法人は米国の70-80%", "outlier": "米国本社VPは$2.4M TC中央値"},
            {"role": "PM L5", "p10": 1500, "p50": 1800, "p90": 2300, "reach_rate": 50},
            {"role": "PM L6", "p10": 2500, "p50": 3000, "p90": 3800, "reach_rate": 15},
        ],
        "日系大手(NTT/NEC/富士通等)": [
            {"role": "エンジニア（課長級）", "p10": 850, "p50": 1000, "p90": 1150, "reach_rate": 40, "note": "年功序列で分散小"},
            {"role": "部長", "p10": 1200, "p50": 1400, "p90": 1700, "reach_rate": 8},
            {"role": "執行役員", "p10": 1800, "p50": 2200, "p90": 2800, "reach_rate": 0.5},
        ],
        "メガベンチャー(サイバー/楽天/LINE等)": [
            {"role": "マネージャー", "p10": 800, "p50": 1000, "p90": 1200, "reach_rate": 30},
            {"role": "部長/VP", "p10": 1200, "p50": 1500, "p90": 1900, "reach_rate": 8},
            {"role": "執行役員", "p10": 2000, "p50": 2500, "p90": 3500, "reach_rate": 1},
            {"role": "CTO/CxO", "p10": 3000, "p50": 4000, "p90": 5500, "reach_rate": 0.3},
        ],
        "スタートアップ": [
            {"role": "エンジニア", "p10": 500, "p50": 650, "p90": 850, "reach_rate": 100, "note": "SO別"},
            {"role": "リードエンジニア", "p10": 700, "p50": 900, "p90": 1100, "reach_rate": 30},
            {"role": "CTO（未上場）", "p10": 1200, "p50": 1500, "p90": 2000, "reach_rate": 5, "note": "SO別", "outlier": "SO行使益含むと数千万〜数億"},
            {"role": "CTO（上場）", "p10": 3000, "p50": 3500, "p90": 4500, "reach_rate": 1},
            {"role": "CEO（未上場）", "p10": 600, "p50": 1000, "p90": 1500, "reach_rate": 3, "note": "SO別。シード期は600-800が最頻"},
            {"role": "CEO（上場SaaS）", "p10": 3000, "p50": 4000, "p90": 6000, "reach_rate": 0.5, "outlier": "SO行使益で1億超は上位5%"},
        ],
        "フリーランス": [
            {"role": "SWE（ジュニア）", "p10": 480, "p50": 600, "p90": 780, "reach_rate": 100},
            {"role": "SWE（シニア）", "p10": 1000, "p50": 1300, "p90": 1700, "reach_rate": 40, "note": "稼働率80%前提"},
            {"role": "SWE（テックリード級）", "p10": 1500, "p50": 1800, "p90": 2300, "reach_rate": 10},
            {"role": "PMO/コンサル", "p10": 1200, "p50": 1500, "p90": 1900, "reach_rate": 15},
        ],
        "ヘルステック/SaaS": [
            {"role": "VP of Engineering", "p10": 2000, "p50": 2500, "p90": 3500, "reach_rate": 3},
            {"role": "CTO", "p10": 3000, "p50": 4000, "p90": 5500, "reach_rate": 1},
            {"role": "CEO", "p10": 2000, "p50": 3000, "p90": 5000, "reach_rate": 0.5, "outlier": "上場後は8,000万超も"},
        ],
    },
    "コンサル": {
        "戦略コンサル(MBB)": [
            {"role": "アソシエイト", "p10": 850, "p50": 1000, "p90": 1150, "reach_rate": 100},
            {"role": "マネージャー", "p10": 1500, "p50": 1800, "p90": 2300, "reach_rate": 50, "note": "残りは2-3年で退職"},
            {"role": "プリンシパル", "p10": 2800, "p50": 3500, "p90": 4500, "reach_rate": 15},
            {"role": "パートナー", "p10": 5000, "p50": 7000, "p90": 10000, "reach_rate": 2, "note": "新任Pは5,000-7,000が大多数。同期コホートの1-2%", "outlier": "シニアPは1.5億超（プロフィットシェア込み）"},
        ],
        "総合コンサル(Big4)": [
            {"role": "シニアコンサルタント", "p10": 700, "p50": 850, "p90": 1000, "reach_rate": 100},
            {"role": "マネージャー", "p10": 1000, "p50": 1200, "p90": 1450, "reach_rate": 30},
            {"role": "ディレクター", "p10": 1800, "p50": 2000, "p90": 2400, "reach_rate": 8},
            {"role": "パートナー", "p10": 2500, "p50": 3500, "p90": 5000, "reach_rate": 1.5, "note": "コンサル部門は監査部門より高い。全社員の1-2%"},
        ],
        "個人コンサル/顧問": [
            {"role": "独立1-3年目", "p10": 600, "p50": 1000, "p90": 1400, "reach_rate": 100, "note": "初年度は前職から大幅減もある"},
            {"role": "確立期（5年+）", "p10": 1500, "p50": 2000, "p90": 2800, "reach_rate": 40, "note": "5年以上継続できるのは約4割"},
            {"role": "著名コンサル", "p10": 3000, "p50": 3500, "p90": 4500, "reach_rate": 3, "note": "講演・出版含む"},
        ],
    },
    "事業会社": {
        "上場大手": [
            {"role": "課長", "p10": 800, "p50": 1000, "p90": 1150, "reach_rate": 35, "note": "同期入社の3-5割（近年は低下傾向）"},
            {"role": "部長", "p10": 1200, "p50": 1400, "p90": 1700, "reach_rate": 7, "note": "同期の4-10%（賃金構造基本統計: 全労働者の3.8%）"},
            {"role": "執行役員", "p10": 1800, "p50": 2500, "p90": 3200, "reach_rate": 0.5},
            {"role": "取締役", "p10": 2500, "p50": 3500, "p90": 4500, "reach_rate": 0.1, "note": "同期の0.1%（大企業で役員到達は1000人に1人）"},
            {"role": "CFO", "p10": 3000, "p50": 4500, "p90": 6500, "reach_rate": 0.05, "note": "時価総額により変動", "outlier": "時価総額1兆超の大手で8,000万超"},
            {"role": "CEO/社長", "p10": 4000, "p50": 6000, "p90": 9000, "reach_rate": 0.01, "note": "東証プライム社長中央値は約6,000万", "outlier": "時価総額上位で1.5億超（上位10%）"},
            {"role": "社外取締役", "p10": 500, "p50": 800, "p90": 1200, "reach_rate": None, "note": "1社あたり。兼任可能（3-5社）。外部登用のため到達率N/A"},
        ],
        "中堅/未上場": [
            {"role": "部長", "p10": 800, "p50": 1000, "p90": 1200, "reach_rate": 10},
            {"role": "取締役", "p10": 1200, "p50": 1500, "p90": 2200, "reach_rate": 1},
            {"role": "CFO", "p10": 1500, "p50": 2000, "p90": 2800, "reach_rate": 0.5},
            {"role": "CEO", "p10": 1500, "p50": 2500, "p90": 4000, "reach_rate": 0.1, "outlier": "急成長ベンチャーCEOは5,000万超も"},
        ],
        "経営企画/戦略": [
            {"role": "マネージャー", "p10": 800, "p50": 1000, "p90": 1200, "reach_rate": 35},
            {"role": "部長", "p10": 1200, "p50": 1400, "p90": 1700, "reach_rate": 7},
            {"role": "VP/執行役員", "p10": 1800, "p50": 2200, "p90": 2800, "reach_rate": 0.5},
        ],
    },
    "製造業": {
        "電機メーカー大手": [
            {"role": "課長", "p10": 850, "p50": 950, "p90": 1050, "reach_rate": 40, "note": "年功序列で分散小"},
            {"role": "部長", "p10": 1100, "p50": 1300, "p90": 1500, "reach_rate": 8},
            {"role": "事業部長", "p10": 1400, "p50": 1600, "p90": 1900, "reach_rate": 2},
            {"role": "執行役員", "p10": 1800, "p50": 2200, "p90": 2800, "reach_rate": 0.5},
            {"role": "取締役", "p10": 2500, "p50": 3500, "p90": 4500, "reach_rate": 0.1},
        ],
        "製造業コンサル/顧問": [
            {"role": "顧問（大手退職後）", "p10": 1000, "p50": 1200, "p90": 1700, "reach_rate": 5, "note": "部長以上の退職者が対象"},
            {"role": "技術コンサル", "p10": 800, "p50": 1000, "p90": 1400, "reach_rate": 10},
        ],
    },
    "広告/メディア": {
        "電通/博報堂": [
            {"role": "プランナー（5年目）", "p10": 650, "p50": 750, "p90": 880, "reach_rate": 80},
            {"role": "CD（クリエイティブディレクター）", "p10": 800, "p50": 1000, "p90": 1350, "reach_rate": 15},
            {"role": "局長", "p10": 1600, "p50": 2000, "p90": 2700, "reach_rate": 3},
            {"role": "執行役員", "p10": 4000, "p50": 5000, "p90": 7000, "reach_rate": 0.5},
            {"role": "執行役", "p10": 10000, "p50": 14000, "p90": 18000, "reach_rate": 0.05, "note": "電通G執行役3名平均1.4億（2024/12期有報）"},
        ],
        "デジタルマーケ": [
            {"role": "マネージャー", "p10": 600, "p50": 800, "p90": 1000, "reach_rate": 30},
            {"role": "ディレクター", "p10": 1000, "p50": 1200, "p90": 1450, "reach_rate": 8},
            {"role": "VP/CMO", "p10": 1500, "p50": 2000, "p90": 2800, "reach_rate": 1},
        ],
        "D2Cブランド": [
            {"role": "創業者（シード期）", "p10": 0, "p50": 400, "p90": 700, "reach_rate": 100, "note": "赤字期は年収0も"},
            {"role": "創業者（成長期）", "p10": 800, "p50": 1200, "p90": 1800, "reach_rate": 30, "note": "シード→成長期に生き残るのは約3割"},
            {"role": "創業者（上場/EXIT後）", "p10": 2000, "p50": 3000, "p90": 5000, "reach_rate": 3, "outlier": "大型EXIT時は1億超"},
        ],
    },
    "公務員/行政": {
        "地方自治体": [
            {"role": "主任", "p10": 450, "p50": 520, "p90": 580, "reach_rate": 70},
            {"role": "課長", "p10": 700, "p50": 800, "p90": 900, "reach_rate": 15},
            {"role": "部長", "p10": 900, "p50": 1000, "p90": 1100, "reach_rate": 3},
            {"role": "副市長/副知事", "p10": 1200, "p50": 1400, "p90": 1550, "reach_rate": 0.1, "note": "政治任用のため純粋な昇進とは異なる"},
        ],
        "都市計画コンサル": [
            {"role": "コンサルタント", "p10": 500, "p50": 650, "p90": 780, "reach_rate": 100},
            {"role": "ディレクター", "p10": 800, "p50": 1000, "p90": 1200, "reach_rate": 15},
            {"role": "パートナー", "p10": 1200, "p50": 1500, "p90": 1900, "reach_rate": 3},
        ],
        "NPO/まちづくり": [
            {"role": "代表", "p10": 300, "p50": 450, "p90": 650, "reach_rate": 100, "note": "助成金・受託依存。自ら設立するケースが大半"},
            {"role": "代表（成功事例）", "p10": 600, "p50": 800, "p90": 1100, "reach_rate": 10},
        ],
    },
    "デザイン": {
        "Web/UIデザイン": [
            {"role": "ジュニア（1-3年）", "p10": 300, "p50": 370, "p90": 440, "reach_rate": 100},
            {"role": "ミドル（3-5年）", "p10": 400, "p50": 500, "p90": 580, "reach_rate": 70},
            {"role": "シニア（5-8年）", "p10": 600, "p50": 700, "p90": 850, "reach_rate": 25},
            {"role": "リード/マネージャー", "p10": 700, "p50": 850, "p90": 1050, "reach_rate": 8},
        ],
        "PdM転身": [
            {"role": "PdM（3-5年目）", "p10": 600, "p50": 800, "p90": 1000, "reach_rate": 100, "note": "転身した人のベースライン"},
            {"role": "シニアPdM", "p10": 900, "p50": 1100, "p90": 1400, "reach_rate": 30},
            {"role": "VP of Product", "p10": 1500, "p50": 1800, "p90": 2300, "reach_rate": 5},
        ],
        "フリーランスデザイナー": [
            {"role": "独立1-2年目", "p10": 350, "p50": 500, "p90": 680, "reach_rate": 100},
            {"role": "確立期", "p10": 700, "p50": 900, "p90": 1150, "reach_rate": 35},
            {"role": "ブランド確立", "p10": 1000, "p50": 1300, "p90": 1800, "reach_rate": 5},
        ],
    },
    "士業/専門職": {
        "弁護士": [
            {"role": "アソシエイト（4大）", "p10": 1200, "p50": 1500, "p90": 1900, "reach_rate": 100},
            {"role": "パートナー（4大）", "p10": 3000, "p50": 5000, "p90": 8000, "reach_rate": 10, "note": "米国BigLawでは3-10%", "outlier": "トップPは1.5億超（上位5%）"},
            {"role": "独立", "p10": 700, "p50": 1200, "p90": 2200, "reach_rate": 62, "note": "弁護士の62%が1人事務所（日弁連統計）"},
        ],
        "医師": [
            {"role": "勤務医", "p10": 1200, "p50": 1500, "p90": 1900, "reach_rate": 75, "note": "厚労省調査の中央値は約1,500万"},
            {"role": "開業医", "p10": 2000, "p50": 2600, "p90": 3800, "reach_rate": 22, "note": "全医師の約22%が開業医。平均開業年齢41.3歳", "outlier": "自由診療・複数院は5,000万超"},
        ],
        "大学教授": [
            {"role": "准教授", "p10": 700, "p50": 850, "p90": 980, "reach_rate": 30, "note": "博士号取得者のうち常勤研究職に就けるのは一部"},
            {"role": "教授（国立）", "p10": 900, "p50": 1050, "p90": 1200, "reach_rate": 15, "note": "東大1,191万がトップ、地方は900万台。分散小"},
        ],
    },
}


def lookup(industry: str = "", role: str = "") -> list[dict]:
    """Lookup compensation ranges matching industry/role keywords."""
    results = []
    industry_lower = industry.lower()
    role_lower = role.lower()

    for ind_key, subcats in BASELINE_TABLE.items():
        if industry_lower and industry_lower not in ind_key.lower():
            # Fuzzy: also check subcategory names
            subcat_match = any(industry_lower in sk.lower() for sk in subcats)
            if not subcat_match:
                continue
        for subcat_key, roles in subcats.items():
            for r in roles:
                if role_lower and role_lower not in r["role"].lower():
                    continue
                results.append({
                    "industry": ind_key,
                    "subcategory": subcat_key,
                    **r,
                })
    return results


def build_reference_for_paths(candidate_context: str, paths: list[dict]) -> dict:
    """Build compensation reference table relevant to candidate's career paths.

    Args:
        candidate_context: e.g. "42歳、メガバンク法人営業部長、年収1400万"
        paths: path_designs.json の paths リスト

    Returns:
        dict with "current_context", "path_references", "all_relevant"
    """
    # Extract keywords from candidate context and paths
    all_keywords = set()
    for word in candidate_context.replace("、", " ").replace("・", " ").split():
        if len(word) >= 2:
            all_keywords.add(word)

    # keyword → industry/subcategory mapping for fuzzy matching
    keyword_map = {
        "銀行": ["金融"],
        "メガバンク": ["金融"],
        "みずほ": ["金融"],
        "三菱": ["金融"],
        "三井住友": ["金融"],
        "信託": ["金融"],
        "PE": ["金融"],
        "ファンド": ["金融"],
        "証券": ["金融"],
        "VC": ["金融"],
        "投資": ["金融"],
        "CFO": ["事業会社", "金融"],
        "CEO": ["事業会社", "テック"],
        "CTO": ["テック"],
        "COO": ["事業会社"],
        "役員": ["事業会社", "金融"],
        "取締役": ["事業会社", "金融"],
        "執行役員": ["事業会社", "金融"],
        "昇進": ["事業会社", "金融", "テック"],
        "コンサル": ["コンサル"],
        "顧問": ["コンサル"],
        "独立": ["コンサル", "テック"],
        "フリーランス": ["テック", "デザイン"],
        "スタートアップ": ["テック"],
        "テック": ["テック"],
        "エンジニア": ["テック"],
        "SaaS": ["テック"],
        "FinTech": ["テック", "金融"],
        "フィンテック": ["テック", "金融"],
        "デザイン": ["デザイン"],
        "PdM": ["デザイン", "テック"],
        "広告": ["広告/メディア"],
        "マーケティング": ["広告/メディア"],
        "D2C": ["広告/メディア"],
        "公務員": ["公務員/行政"],
        "自治体": ["公務員/行政"],
        "NPO": ["公務員/行政"],
        "製造": ["製造業"],
        "メーカー": ["製造業"],
    }

    path_refs = []
    for p in paths:
        label = p.get("label", "")
        direction = p.get("direction", "")
        pid = p.get("path_id", "")
        search_text = f"{label} {direction} {candidate_context}"

        # Find relevant industries via keyword matching
        relevant_industries = set()
        for kw, industries in keyword_map.items():
            if kw.lower() in search_text.lower() or kw in search_text:
                relevant_industries.update(industries)

        # Also match directly against industry/subcategory names
        for ind_key in BASELINE_TABLE:
            if ind_key.lower() in search_text.lower():
                relevant_industries.add(ind_key)

        # Collect matching compensation ranges
        matches = []
        for ind_key, subcats in BASELINE_TABLE.items():
            if ind_key not in relevant_industries:
                continue
            for subcat_key, roles in subcats.items():
                # Score relevance by how many keywords match
                combined = f"{ind_key} {subcat_key} {' '.join(r['role'] for r in roles)}"
                relevance = sum(1 for kw in keyword_map
                                if kw.lower() in search_text.lower()
                                and kw.lower() in combined.lower())
                for r in roles:
                    matches.append({
                        "industry": ind_key,
                        "subcategory": subcat_key,
                        "relevance": max(relevance, 1),
                        **r,
                    })

        # Sort by relevance, take top entries
        matches.sort(key=lambda x: (-x["relevance"], -x.get("p90", x.get("max", 0))))
        # Deduplicate
        seen = set()
        unique = []
        for m in matches:
            key = (m["industry"], m["subcategory"], m["role"])
            if key not in seen:
                seen.add(key)
                unique.append(m)

        path_refs.append({
            "path_id": pid,
            "label": label,
            "direction": direction,
            "compensation_ranges": unique[:12],
        })

    return {
        "candidate_context": candidate_context,
        "path_references": path_refs,
        "baseline_source": "MiroFish compensation baseline v1 (2025)",
    }


def format_as_prompt_context(ref: dict) -> str:
    """Format reference data as text for SubAgent prompt injection."""
    lines = ["## 報酬水準リファレンス（自動取得）\n"]
    lines.append(f"候補者: {ref['candidate_context']}\n")

    for pr in ref["path_references"]:
        if not pr["compensation_ranges"]:
            continue
        lines.append(f"### {pr['label']}")
        lines.append(f"方向性: {pr['direction']}\n")
        lines.append("| 業界 | サブカテゴリ | ポジション | P10 | P50 | P90 | 到達率 | 異常値帯 | 備考 |")
        lines.append("|------|------------|-----------|-----|-----|-----|--------|---------|------|")
        for r in pr["compensation_ranges"]:
            note = r.get("note", "")
            outlier = r.get("outlier", "")
            p10 = r.get("p10", r.get("min", ""))
            p50 = r.get("p50", r.get("typical", ""))
            p90 = r.get("p90", r.get("max", ""))
            p10_str = f"{p10:,}" if p10 else "-"
            p50_str = f"{p50:,}" if p50 else "-"
            p90_str = f"{p90:,}" if p90 else "-"
            rr = r.get("reach_rate")
            if rr is None:
                rr_str = "N/A"
            elif rr >= 10:
                rr_str = f"{rr:.0f}%"
            else:
                rr_str = f"{rr}%"
            lines.append(
                f"| {r['industry']} | {r['subcategory']} | {r['role']} "
                f"| {p10_str} | {p50_str} | {p90_str} | {rr_str} | {outlier} | {note} |"
            )
        lines.append("")

    lines.append(f"_Source: {ref['baseline_source']}_")
    return "\n".join(lines)


def try_tavily_augment(industry: str, role: str) -> list[dict]:
    """Attempt to augment baseline with Tavily web search.

    Returns additional compensation data points from web.
    Falls back gracefully if TAVILY_API_KEY is not set.
    """
    try:
        from app.services.external_data_fetcher import ExternalDataFetcher
        fetcher = ExternalDataFetcher()
        query = f"{industry} {role} 年収 報酬 2025"
        results = fetcher.search(query, max_results=3)
        return [{"source": r.get("url", ""), "snippet": r.get("content", "")[:200]}
                for r in results]
    except Exception:
        return []


def main():
    parser = argparse.ArgumentParser(
        description="Fetch compensation reference data"
    )
    parser.add_argument("--mode", choices=["lookup", "build", "update"],
                        default="lookup")
    parser.add_argument("--role", default="", help="Role to search")
    parser.add_argument("--industry", default="", help="Industry to search")
    parser.add_argument("--candidate-context", default="",
                        help="Candidate description for building path-specific refs")
    parser.add_argument("--paths-file",
                        help="path_designs.json for path-specific reference")
    parser.add_argument("--output-file", help="Write output to file")
    parser.add_argument("--format", choices=["json", "prompt"], default="json",
                        help="Output format: json or prompt-injectable text")

    args = parser.parse_args()

    if args.mode == "lookup":
        results = lookup(args.industry, args.role)
        if not results:
            print("No matches found", file=sys.stderr)
            sys.exit(1)
        output = json.dumps(results, ensure_ascii=False, indent=2)

    elif args.mode == "build":
        if not args.paths_file:
            parser.error("--paths-file required for build mode")
        with open(args.paths_file, "r", encoding="utf-8") as f:
            designs = json.load(f)
        paths = designs.get("paths", designs) if isinstance(designs, dict) else designs
        ref = build_reference_for_paths(args.candidate_context, paths)

        if args.format == "prompt":
            output = format_as_prompt_context(ref)
        else:
            output = json.dumps(ref, ensure_ascii=False, indent=2)

    elif args.mode == "update":
        # Tavily augmentation
        web_data = try_tavily_augment(args.industry, args.role)
        baseline = lookup(args.industry, args.role)
        result = {
            "baseline": baseline,
            "web_augmented": web_data,
            "note": "Web data is supplementary. Review before using.",
        }
        output = json.dumps(result, ensure_ascii=False, indent=2)

    if args.output_file:
        with open(args.output_file, "w", encoding="utf-8") as f:
            f.write(output)
        print(json.dumps({
            "status": "ok",
            "output_file": args.output_file,
        }), file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
