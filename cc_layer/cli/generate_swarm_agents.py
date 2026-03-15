#!/usr/bin/env python3
"""30人のSwarmエージェント定義を候補者データから動的生成

Usage:
    # 候補者データから動的生成
    python -m cc_layer.cli.generate_swarm_agents \
        --session-dir cc_layer/state/demo_session \
        --num-workers 6

    # パス数を指定（デフォルト5）
    python -m cc_layer.cli.generate_swarm_agents \
        --session-dir cc_layer/state/demo_session \
        --num-paths 3
"""
import argparse
import json
import os
import sys
from datetime import datetime


# === プリセットエージェント（候補者に依存しない固定枠） ===
PRESET_CONTRARIANS = [
    {"name": "安藤誠", "bio": "55歳労働経済学者。大学教授。雇用統計と労働市場の構造変化を研究。データで反論する。",
     "persona": "opposing", "activity_level": 0.65, "stance": "opposing", "role": "contrarian"},
    {"name": "森田美月", "bio": "37歳組織心理学者。バーンアウト研究が専門。「キャリアアップ＝幸福」に疑問を投げかける。",
     "persona": "opposing", "activity_level": 0.6, "stance": "opposing", "role": "contrarian"},
    {"name": "ケビン・パク", "bio": "42歳。元GAFA→現在セミリタイア。「成功」の定義を問い直す視点。ダウンシフト経験者。",
     "persona": "opposing", "activity_level": 0.55, "stance": "opposing", "role": "contrarian"},
]

PRESET_CAREER_COACHES = [
    {"name": "藤井健一", "bio": "52歳キャリアカウンセラー。公的機関で20年。ミドルシニアの転職・独立支援。地に足のついた助言。",
     "persona": "supportive", "activity_level": 0.55, "stance": "supportive", "role": "external_evaluator"},
]

PRESET_ANALYSTS = [
    {"name": "田村正和", "bio": "46歳人材業界アナリスト。リクルート出身。転職市場の需給バランスに最も詳しい。",
     "persona": "neutral", "activity_level": 0.6, "stance": "neutral", "role": "external_evaluator"},
]


def generate_path_copies(identity, state, paths):
    """パスコピーエージェントを各パスから生成"""
    copies = []
    name = identity.get("name", "候補者")
    age = identity.get("age_at_start", 30)

    for p in paths:
        pid = p["path_id"]
        label = p.get("label", pid)
        direction = p.get("direction", "")
        bio = f"{age}歳。{direction}。{label}ルート。"

        # パスの最終状態からペルソナを決定
        fs = p.get("final_state", {})
        score = fs.get("total_score", 0.5)
        stance = "supportive" if score > 0.75 else "neutral" if score > 0.65 else "opposing"

        copies.append({
            "name": f"{name} [{pid.replace('path_', 'Path ').upper().replace('PATH ', 'Path ')}]",
            "bio": bio,
            "persona": stance,
            "activity_level": round(0.6 + score * 0.3, 2),
            "stance": stance,
            "role": "copy_agent",
            "path_ref": pid,
        })
    return copies


def generate_family_agents(identity, state):
    """家族構成からエージェントを生成"""
    agents = []
    name = identity.get("name", "候補者")
    gender = identity.get("gender", "")
    family = state.get("family", [])

    for f in family:
        rel = f["relation"]
        age = f["age"]
        notes = f.get("notes", "")

        if rel == "spouse":
            # 配偶者
            spouse_name = f.get("name", f"{name.split()[0] if ' ' in name else name[0]}の配偶者")
            if gender == "女性":
                spouse_name = f"{name[0:2]}健二" if not f.get("name") else f.get("name")
            else:
                spouse_name = f"{name[0:2]}美穂" if not f.get("name") else f.get("name")
            bio = f"{age}歳。{name}の配偶者。{notes}。家計と育児の分担を真剣に考える。"
            agents.append({
                "name": spouse_name,
                "bio": bio,
                "persona": "supportive",
                "activity_level": 0.5,
                "stance": "supportive",
                "role": "external_evaluator",
                "category": "family",
            })
        elif rel == "child":
            # 子供が小さい場合はエージェント化しない（声を出せない）
            pass
        elif rel == "parent":
            parent_name = f.get("name", f"{name[0:2]}の親")
            if not f.get("name"):
                parent_name = f"{name[0:2]}洋子" if gender == "女性" else f"{name[0:2]}太郎"
            bio = f"{age}歳。{name}の親。{'健康' if '健康' in notes else notes}。子供のキャリアを応援しつつ、孫の成長を最優先してほしい。"
            agents.append({
                "name": parent_name,
                "bio": bio,
                "persona": "observer",
                "activity_level": 0.3,
                "stance": "observer",
                "role": "external_evaluator",
                "category": "family",
            })
    return agents


def generate_industry_agents(identity, state):
    """候補者の業界・職種に合わせた業界エージェントを生成"""
    agents = []
    industry = state.get("industry", "")
    role = state.get("role", "")
    career = identity.get("career_history_summary", "")

    # 業界別のエージェントプール
    if "SaaS" in industry or "IT" in industry:
        agents.extend([
            {"name": "高橋龍一", "bio": f"38歳スタートアップCEO。{industry}企業を経営。攻撃的な成長戦略。AIネイティブプロダクトを推進。",
             "persona": "opposing", "activity_level": 0.95, "stance": "opposing", "role": "external_evaluator", "category": "executive"},
            {"name": "山口彩", "bio": f"39歳テックアナリスト @ 野村総研。{industry}市場レポートの執筆者。数字で語る。",
             "persona": "neutral", "activity_level": 0.65, "stance": "neutral", "role": "external_evaluator", "category": "analyst"},
            {"name": "中村大輔", "bio": "50歳事業部長。大手IT企業。DX推進の現場を知る。採用する側の本音を持つ。",
             "persona": "observer", "activity_level": 0.4, "stance": "observer", "role": "external_evaluator", "category": "analyst"},
        ])

    # 職種に合わせたピア
    if "PdM" in role or "プロダクト" in role:
        agents.extend([
            {"name": "石川拓也", "bio": f"34歳シニアPdM。PdMキャリア8年。横のつながりで業界動向に詳しい。率直な意見。",
             "persona": "neutral", "activity_level": 0.75, "stance": "neutral", "role": "external_evaluator", "category": "peer"},
            {"name": "山本さくら", "bio": "26歳PdM2年目。メガベンチャー勤務。キャリアに不安を感じつつ先輩の選択を注視。",
             "persona": "supportive", "activity_level": 0.85, "stance": "supportive", "role": "external_evaluator", "category": "peer"},
            {"name": "木村拓也", "bio": f"44歳CPO @ 上場{industry}企業。PdMからCPOまで登り詰めた。組織設計と事業戦略の両面に精通。",
             "persona": "neutral", "activity_level": 0.6, "stance": "neutral", "role": "external_evaluator", "category": "executive"},
        ])

    # キャリア履歴に基づく関連エージェント
    if "コンサル" in career:
        agents.append({
            "name": "伊藤慎介", "bio": "42歳コンサルマネージャー。コンサル時代の先輩。独立3年目。率直な友人。",
            "persona": "neutral", "activity_level": 0.6, "stance": "neutral", "role": "external_evaluator", "category": "friend",
        })

    if "メルカリ" in career or "GAFA" in career.upper():
        agents.append({
            "name": "田中健太", "bio": "28歳バックエンドエンジニア。Go/Rust。テック企業での経験を共有。技術者視点で語る。",
            "persona": "neutral", "activity_level": 0.9, "stance": "neutral", "role": "external_evaluator", "category": "peer",
        })

    return agents


def generate_career_specific_agents(identity, state, paths):
    """パスの内容に合わせた専門エージェントを生成"""
    agents = []
    career = identity.get("career_history_summary", "")
    path_ids = [p["path_id"] for p in paths]

    # 起業パスがある場合 → VC/投資家を追加
    has_startup = any("起業" in p.get("direction", "") or "創業" in p.get("direction", "") for p in paths)
    if has_startup:
        agents.extend([
            {"name": "加藤裕太", "bio": "33歳VC投資家。SaaS特化ファンド運営。起業家メンタリングも行う。シード〜シリーズAに強い。",
             "persona": "opposing", "activity_level": 0.85, "stance": "opposing", "role": "external_evaluator", "category": "vc"},
            {"name": "松田亮介", "bio": "41歳CVC責任者。大手商社系ファンド。AI領域の投資判断20件以上。ROI重視。",
             "persona": "opposing", "activity_level": 0.7, "stance": "opposing", "role": "external_evaluator", "category": "vc"},
            {"name": "井上裕子", "bio": "40歳連続起業家。2社目をIPO。現在はエンジェル投資家。起業家のロールモデル。",
             "persona": "supportive", "activity_level": 0.7, "stance": "supportive", "role": "external_evaluator", "category": "executive"},
        ])

    # 外資パスがある場合 → グローバル視点のエージェント
    has_foreign = any("外資" in p.get("direction", "") or "GAFA" in p.get("label", "") for p in paths)
    if has_foreign:
        agents.append({
            "name": "リサ・チェン", "bio": "36歳。シリコンバレーVC。日本市場のクロスボーダー投資を担当。グローバル視点で辛口評価。",
            "persona": "opposing", "activity_level": 0.75, "stance": "opposing", "role": "external_evaluator", "category": "vc",
        })

    # 転職パスがある場合 → HR/ヘッドハンター
    has_job_change = any("転職" in p.get("direction", "") for p in paths)
    if has_job_change:
        agents.extend([
            {"name": "鈴木花子", "bio": "45歳HR部長。大手メーカー人事20年。リスキリング制度設計のエキスパート。候補者を冷静に評価。",
             "persona": "observer", "activity_level": 0.5, "stance": "observer", "role": "external_evaluator", "category": "hr"},
            {"name": "吉田恵理", "bio": "38歳HRBP。外資IT企業。ハイパフォーマーの離職防止が専門。キャリアパス設計に詳しい。",
             "persona": "observer", "activity_level": 0.6, "stance": "observer", "role": "external_evaluator", "category": "hr"},
            {"name": "佐々木大地", "bio": "43歳ヘッドハンター。エグゼクティブ転職専門。CxOクラスの人材市場を熟知。年収相場に明るい。",
             "persona": "neutral", "activity_level": 0.65, "stance": "neutral", "role": "external_evaluator", "category": "hr"},
        ])

    # 独立/フリーランスパスがある場合 → キャリアコーチ追加
    has_freelance = any("独立" in p.get("direction", "") or "フリー" in p.get("direction", "") for p in paths)
    if has_freelance:
        agents.extend([
            {"name": "小林真理", "bio": "35歳キャリアコーチ。元UXデザイナー。キャリアチェンジ支援が専門。共感力が高い。",
             "persona": "supportive", "activity_level": 0.8, "stance": "supportive", "role": "external_evaluator", "category": "coach"},
            {"name": "中島理恵", "bio": "48歳エグゼクティブコーチ。ICF PCC保持。リーダーのキャリア開発に特化。",
             "persona": "supportive", "activity_level": 0.7, "stance": "supportive", "role": "external_evaluator", "category": "coach"},
        ])

    # データ系スキルがある場合
    skills = state.get("skills", [])
    if any("データ" in s or "分析" in s for s in skills):
        agents.append({
            "name": "渡辺由美", "bio": "30歳データサイエンティスト。MLエンジニアへの転向検討中。AI人材市場のリアルを知る。",
            "persona": "supportive", "activity_level": 0.7, "stance": "supportive", "role": "external_evaluator", "category": "peer",
        })

    return agents


def build_agents(session_dir, num_paths=5):
    """候補者データから30人のエージェントを動的生成"""
    # Load candidate data
    agent_state_path = os.path.join(session_dir, "agent_state.json")
    if not os.path.exists(agent_state_path):
        print(f"Error: {agent_state_path} not found", file=sys.stderr)
        sys.exit(1)

    with open(agent_state_path, "r", encoding="utf-8") as f:
        candidate = json.load(f)

    identity = candidate.get("identity", {})
    state = candidate.get("state", {})

    # Load paths
    result_path = os.path.join(session_dir, "multipath_result.json")
    if os.path.exists(result_path):
        with open(result_path, "r", encoding="utf-8") as f:
            result = json.load(f)
        paths = result.get("paths", [])[:num_paths]
    else:
        paths = []

    all_agents = []

    # 1. パスコピー（パス数分）
    all_agents.extend(generate_path_copies(identity, state, paths))

    # 2. 家族エージェント（候補者データから動的生成）
    all_agents.extend(generate_family_agents(identity, state))

    # 3. 業界・職種に合わせたエージェント
    all_agents.extend(generate_industry_agents(identity, state))

    # 4. パス内容に合わせた専門エージェント
    all_agents.extend(generate_career_specific_agents(identity, state, paths))

    # 5. プリセット（学者・コントラリアン・汎用コーチ・アナリスト）
    all_agents.extend(PRESET_CONTRARIANS)
    all_agents.extend(PRESET_CAREER_COACHES)
    all_agents.extend(PRESET_ANALYSTS)

    # 重複排除（名前ベース）
    seen = set()
    unique = []
    for a in all_agents:
        if a["name"] not in seen:
            seen.add(a["name"])
            unique.append(a)
    all_agents = unique

    # agent_id付与
    for i, a in enumerate(all_agents):
        a["agent_id"] = i

    # カテゴリ集計
    composition = {}
    for a in all_agents:
        cat = a.get("category", a.get("role", "other"))
        composition[cat] = composition.get(cat, 0) + 1

    return all_agents, composition


def distribute_agents(agents, num_workers):
    """エージェントをワーカーに均等分配"""
    workers = [[] for _ in range(num_workers)]
    for i, agent in enumerate(agents):
        workers[i % num_workers].append(agent)
    return workers


def main():
    parser = argparse.ArgumentParser(description="Swarmエージェント動的生成")
    parser.add_argument("--session-dir", required=True)
    parser.add_argument("--num-workers", type=int, default=6)
    parser.add_argument("--num-paths", type=int, default=5)
    args = parser.parse_args()

    swarm_dir = os.path.join(args.session_dir, "swarm")
    os.makedirs(swarm_dir, exist_ok=True)

    agents, composition = build_agents(args.session_dir, args.num_paths)
    workers = distribute_agents(agents, args.num_workers)

    # Write master agent list
    master_path = os.path.join(args.session_dir, "swarm_agents.json")
    with open(master_path, "w", encoding="utf-8") as f:
        json.dump(agents, f, ensure_ascii=False, indent=2)
    print(f"Master agents: {master_path} ({len(agents)} agents)")

    # Write per-worker agent files
    agents_per_worker = []
    for i, worker_agents in enumerate(workers):
        worker_path = os.path.join(swarm_dir, f"worker_{i}_agents.json")
        with open(worker_path, "w", encoding="utf-8") as f:
            json.dump(worker_agents, f, ensure_ascii=False, indent=2)
        agents_per_worker.append(len(worker_agents))
        names = ", ".join(a["name"] for a in worker_agents)
        print(f"  Worker {i}: {len(worker_agents)} agents — {names}")

    # Write swarm config
    config = {
        "num_workers": args.num_workers,
        "total_agents": len(agents),
        "agents_per_worker": agents_per_worker,
        "agent_composition": composition,
        "source": "dynamic",
        "candidate_name": agents[0]["name"].split(" [")[0] if agents else "unknown",
        "created_at": datetime.now().isoformat(),
    }
    config_path = os.path.join(swarm_dir, "swarm_config.json")
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    print(f"\nConfig: {config_path}")
    print(f"\nComposition:")
    for cat, count in sorted(composition.items()):
        print(f"  {cat}: {count}")
    print(f"\nTotal: {len(agents)} agents across {args.num_workers} workers")


if __name__ == "__main__":
    main()
