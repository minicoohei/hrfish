#!/usr/bin/env python3
"""MiroFish Swarm-in-the-Loop レポートHTML生成

Usage:
    python -m cc_layer.cli.report_html \
        --session-dir cc_layer/state/demo_session \
        --output report.html
    open report.html
"""
import argparse
import json
import html
import os
import sys
from pathlib import Path


def _pct(v) -> int:
    """None-safe percentage: 0.0-1.0 の値を 0-100 の int に変換。None/文字列は 0。"""
    if v is None:
        return 0
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0
    return int(f * 100) if f <= 1.0 else int(f)


def _num(v, default=0):
    """None-safe numeric: None/文字列は default。HTML埋め込み用に安全な値を返す。"""
    if v is None:
        return default
    try:
        return type(default)(v)
    except (TypeError, ValueError):
        return default


def safe_json_embed(obj) -> str:
    """JSON を <script> 内に安全に埋め込む。

    </script> や <!-- を含むデータがあると script 文脈を脱出して XSS になるため、
    危険なシーケンスをエスケープする。
    """
    s = json.dumps(obj, ensure_ascii=True)
    s = s.replace("</", r"<\/").replace("<!--", r"<\!--")
    return s


def load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_jsonl(path: str):
    items = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


def load_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def collect_agents(session_dir: str):
    agents = {}
    # マスターリストがあればそれを使う
    master = os.path.join(session_dir, "swarm_agents.json")
    if os.path.exists(master):
        for a in load_json(master):
            agents[a.get("agent_id", "")] = a
        return agents
    # フォールバック: ワーカーファイルを全て読む
    swarm_dir = os.path.join(session_dir, "swarm")
    if os.path.isdir(swarm_dir):
        for fname in sorted(os.listdir(swarm_dir)):
            if fname.startswith("worker_") and fname.endswith("_agents.json"):
                for a in load_json(os.path.join(swarm_dir, fname)):
                    agents[a.get("agent_id", "")] = a
    return agents


def collect_swarm_actions(session_dir: str):
    swarm_dir = os.path.join(session_dir, "swarm")
    actions = []
    if not os.path.isdir(swarm_dir):
        return actions
    for fname in sorted(os.listdir(swarm_dir)):
        if fname.startswith("all_actions_round_") and fname.endswith(".jsonl"):
            actions.extend(load_jsonl(os.path.join(swarm_dir, fname)))
    return actions


_path_keywords_cache = {}

def init_path_keywords(paths: list):
    """パスデータからキーワードマップを動的生成"""
    global _path_keywords_cache
    _path_keywords_cache = {}
    for p in paths:
        pid = p.get("path_id", "")
        label = p.get("label", p.get("path_label", ""))
        kws = [pid, pid.replace("_", " ")]
        if pid:
            kws += [f"Path {pid[-1].upper()}", f"パス{pid[-1].upper()}"]
        # ラベルからキーワード抽出
        if label:
            kws.append(label)
            # ラベルの主要単語を追加（2文字以上）
            for word in label.replace("（", " ").replace("）", " ").replace("/", " ").split():
                if len(word) >= 2:
                    kws.append(word)
        # シナリオラベルからもキーワード追加
        for s in p.get("scenarios", []):
            sl = s.get("label", "")
            if sl:
                for word in sl.replace("（", " ").replace("）", " ").split():
                    if len(word) >= 2:
                        kws.append(word)
        _path_keywords_cache[pid] = list(set(kws))

def detect_path_refs(content: str) -> list:
    """コメント内容からパス参照を推定"""
    refs = []
    for path_id, kws in _path_keywords_cache.items():
        if any(kw in content for kw in kws):
            refs.append(path_id)
    return refs


def classify_comments(actions, agents):
    positive_keywords = [
        "ワクワク", "成長", "成功", "チャンス", "可能性", "注目", "面白い",
        "前進", "最高", "楽しい", "安定", "充実", "改善", "獲得", "拡大",
        "投資したい", "転用可能", "知見", "実績", "評価", "強み", "期待",
        "適性", "フィット", "活かせる", "武器", "希少", "有利",
    ]
    negative_keywords = [
        "不安", "焦る", "限界", "リスク", "ディスラプト", "険しい", "悩ましい",
        "身に沁みる", "自信が持てない", "ストレス", "燃え尽き", "競争激化",
        "Red Ocean", "犠牲", "困難", "失敗", "厳しい", "現実", "甘い",
        "過大評価", "ギャップ", "壁", "ボトルネック", "弱み",
    ]
    results = []
    for a in actions:
        content = ""
        if a.get("action_type", "") == "CREATE_POST":
            content = a.get("action_args", a).get("content", "") if isinstance(a.get("action_args"), dict) else a.get("content", "")
        elif a.get("action_type", "") == "CREATE_COMMENT":
            content = a.get("action_args", a).get("content", "") if isinstance(a.get("action_args"), dict) else a.get("content", "")
        else:
            continue
        if not content:
            continue

        pos_score = sum(1 for kw in positive_keywords if kw in content)
        neg_score = sum(1 for kw in negative_keywords if kw in content)
        sentiment = "positive" if pos_score >= neg_score else "negative"
        if pos_score == 0 and neg_score == 0:
            sentiment = "neutral"

        agent_info = agents.get(a.get("agent_id", ""), {})
        # パス参照を推定: エージェントのpath_ref or コンテンツから推定
        path_refs = detect_path_refs(content)
        agent_path = agent_info.get("path_ref", "")
        if agent_path and agent_path not in path_refs:
            path_refs.append(agent_path)

        results.append({
            "agent_name": a.get("agent_name", ""),
            "agent_bio": agent_info.get("bio", agent_info.get("background", agent_info.get("personality", ""))),
            "agent_role": agent_info.get("role", ""),
            "agent_personality": agent_info.get("personality", ""),
            "agent_speaking_style": agent_info.get("speaking_style", ""),
            "agent_background": agent_info.get("background", ""),
            "agent_category": agent_info.get("category", ""),
            "stance": agent_info.get("stance", agent_info.get("stance_default", "unknown")),
            "role": agent_info.get("role", ""),
            "content": content,
            "sentiment": sentiment,
            "round": a.get("round_num", a.get("round", 0)),
            "path_refs": path_refs,
        })
    return results


def analyze_candidate(identity, state, paths):
    """候補者の強み・弱み・人材タイプをデータから動的に分析"""
    career_history = identity.get("career_history_summary", "")
    skills = state.get("skills", [])
    traits = identity.get("stable_traits", [])
    certs = identity.get("certifications", [])
    role = state.get("role", "")
    industry = state.get("industry", "")
    name = identity.get("name", "候補者")
    years = state.get("years_in_role", 0)

    strengths = []
    weaknesses = []

    # --- 強み: キャリア・スキル・特性から動的に導出 ---
    # 業界経験
    if years >= 10:
        strengths.append({"label": f"{industry}の深い業界知識", "detail": f"{industry}業界で{years}年以上の経験。業界構造・主要プレイヤーを熟知", "icon": "strategy"})
    elif years >= 5:
        strengths.append({"label": f"{industry}での実務経験", "detail": f"{industry}業界で{years}年の経験を積み、実務レベルの専門性を保有", "icon": "strategy"})

    # 現在のロールから強み推定
    role_lower = role.lower()
    if any(k in role_lower for k in ["代表", "ceo", "cto", "vp", "部長", "事業部長", "取締役"]):
        strengths.append({"label": "経営・マネジメント力", "detail": f"{role}として組織運営・意思決定の経験を保有", "icon": "team"})
    elif any(k in role_lower for k in ["リード", "マネージャー", "主任", "課長"]):
        strengths.append({"label": "チームマネジメント", "detail": f"{role}としてチーム運営・プロジェクト推進の経験あり", "icon": "team"})

    # スキルベースの強み
    skill_text = " ".join(skills)
    if any(k in skill_text for k in ["Python", "SQL", "データ分析", "機械学習", "AI"]):
        strengths.append({"label": "テクニカルスキル", "detail": f"技術スキル: {', '.join(s for s in skills if any(k in s for k in ['Python','SQL','データ','機械','AI','エンジニア']))[:60]}", "icon": "data"})
    if any(k in skill_text for k in ["戦略", "コンサル", "企画", "マーケティング"]):
        strengths.append({"label": "戦略・企画力", "detail": f"戦略立案・企画の実務スキルを保有", "icon": "strategy"})
    if any(k in skill_text for k in ["デザイン", "UI", "UX", "クリエイティブ"]):
        strengths.append({"label": "デザイン・クリエイティブ", "detail": f"UI/UXデザインやクリエイティブ制作の専門性", "icon": "product"})
    if any(k in skill_text for k in ["英語", "TOEIC", "グローバル", "海外"]):
        strengths.append({"label": "グローバル対応力", "detail": "英語力・国際経験を活かしたグローバル展開が可能", "icon": "scale"})

    # 特性ベースの強み
    if traits:
        trait_text = "、".join(traits[:3])
        strengths.append({"label": "パーソナリティ", "detail": f"特性: {trait_text}", "icon": "team"})

    # 資格があれば
    if certs:
        cert_text = "、".join(certs[:3])
        strengths.append({"label": "専門資格", "detail": f"保有資格: {cert_text}", "icon": "product"})

    # 最低1つは保証
    if not strengths:
        strengths.append({"label": f"{role}の実務経験", "detail": f"{industry}業界の{role}として活躍中", "icon": "product"})

    # 最大4つに絞る
    strengths = strengths[:4]

    # --- 弱み: パスデータから動的に導出 ---
    # 高ストレスパスの検出
    for p in paths:
        for s in p.get("scenarios", []):
            fs = s.get("final_state", {})
            if fs.get("stress", 0) > 0.75:
                weaknesses.append({"label": f"高ストレスリスク（{p.get('label', '')[:15]}）",
                                   "detail": f"{s.get('label', '')}シナリオではストレスが{_pct(fs.get('stress', 0))}%に達する可能性"})
                break
        if weaknesses:
            break

    # 低WLBパスの検出
    for p in paths:
        for s in p.get("scenarios", []):
            fs = s.get("final_state", {})
            if fs.get("work_life_balance", 1) < 0.35:
                weaknesses.append({"label": f"WLB低下リスク（{p.get('label', '')[:15]}）",
                                   "detail": f"{s.get('label', '')}シナリオではWLBが{_pct(fs.get('work_life_balance', 0))}%まで低下"})
                break
        if len(weaknesses) >= 2:
            break

    # baseシナリオの年収低下リスク
    current_salary = state.get("salary_annual", 0)
    for p in paths:
        for s in p.get("scenarios", []):
            if s.get("scenario_id") == "base":
                fs = s.get("final_state", {})
                base_income = fs.get("annual_income", 0)
                if base_income < current_salary * 0.8 and base_income > 0:
                    weaknesses.append({"label": f"年収低下リスク（{p['label'][:15]}）",
                                       "detail": f"Baseシナリオでは年収が現在の{current_salary}万円から{int(base_income)}万円に低下する可能性"})
                    break
        if len(weaknesses) >= 3:
            break

    if not weaknesses:
        weaknesses.append({"label": "不確実性", "detail": "キャリアチェンジには常にリスクが伴い、想定外の事態への対応力が試される"})

    weaknesses = weaknesses[:3]

    # --- 人材タイプ: ロール・業界・スキルから動的生成 ---
    # パスの方向性を集約
    path_labels = [p.get("label", "") for p in paths[:3]]
    path_directions = [p.get("direction", "") for p in paths if p.get("direction")]

    if any(k in role_lower for k in ["代表", "ceo", "cto", "創業"]):
        talent_type = f"{industry}の経営者・起業家人材"
    elif any(k in role_lower for k in ["vp", "部長", "事業部長", "ディレクター"]):
        talent_type = f"{industry}のシニアリーダー人材"
    elif any(k in role_lower for k in ["マネージャー", "リード", "主任", "課長"]):
        talent_type = f"{industry}の中核マネジメント人材"
    elif any(k in skill_text for k in ["デザイン", "UI", "クリエイティブ"]):
        talent_type = f"{industry}のクリエイティブ専門人材"
    elif any(k in skill_text for k in ["エンジニア", "開発", "プログラミング"]):
        talent_type = f"{industry}のテクニカル専門人材"
    else:
        talent_type = f"{industry}の専門人材"

    # 人材説明文をデータから生成
    career_parts = [p.strip() for p in career_history.split("→") if p.strip()]
    if len(career_parts) >= 2:
        career_summary = f"{'→'.join(career_parts[:3])}の経歴を持ち、"
    elif career_parts:
        career_summary = f"{career_parts[0]}での経験を持ち、"
    else:
        career_summary = f"{industry}業界での経験を持ち、"

    skill_summary = f"主要スキルは{', '.join(skills[:3])}。" if skills else ""
    path_summary = f"キャリアの選択肢として「{'」「'.join(p[:15] for p in path_labels[:3])}」等が想定される。" if path_labels else ""

    talent_desc = f"{career_summary}{skill_summary}{path_summary}"

    return {
        "talent_type": talent_type,
        "talent_desc": talent_desc,
        "strengths": strengths,
        "weaknesses": weaknesses,
    }


def _derive_reskilling(paths, state, identity):
    """パスデータと候補者情報からリスキリング提案を動的生成"""
    current_skills = set(state.get("skills", []))
    role = state.get("role", "")
    reskill = []

    # パスのナラティブ・ラベルからキーワードを抽出し、現在スキルにないものを提案
    path_skill_hints = {
        "マネジメント": {"skill": "組織マネジメント", "reason": "リーダーポジションを目指すパスで必須。チーム運営・評価制度の設計能力", "timeframe": "1〜3年"},
        "経営": {"skill": "経営・ファイナンス", "reason": "経営層ポジションや起業パスでPL管理・資金調達の知識が必要", "timeframe": "2〜3年"},
        "起業": {"skill": "起業・事業立ち上げ", "reason": "事業計画策定、資金調達、MVPローンチの実務スキル", "timeframe": "1〜2年"},
        "グローバル": {"skill": "英語・グローバルコミュニケーション", "reason": "海外展開やグローバルポジションで必須", "timeframe": "1〜2年"},
        "AI": {"skill": "AI/ML リテラシー", "reason": "テクノロジー活用による競争優位の確保", "timeframe": "今すぐ〜1年"},
        "DX": {"skill": "DX推進・デジタル変革", "reason": "組織のデジタルトランスフォーメーションを主導する能力", "timeframe": "1〜2年"},
        "コンサル": {"skill": "コンサルティングスキル", "reason": "問題解決フレームワーク、クライアントマネジメント", "timeframe": "1〜2年"},
        "独立": {"skill": "セルフブランディング", "reason": "フリーランス・独立路線でクライアント獲得に必須", "timeframe": "1〜3年"},
        "IPO": {"skill": "コーポレートガバナンス", "reason": "上場準備・IR・内部統制の実務知識", "timeframe": "2〜3年"},
        "M&A": {"skill": "M&A・企業再編", "reason": "デューデリジェンス、PMI（統合後マネジメント）の知識", "timeframe": "2〜3年"},
        "CTO": {"skill": "技術経営（MOT）", "reason": "技術戦略と事業戦略を接続する能力", "timeframe": "1〜3年"},
        "デザイン": {"skill": "デザイン思考・UXリサーチ", "reason": "ユーザー中心設計とプロダクト開発のリーダーシップ", "timeframe": "1〜2年"},
        "NPO": {"skill": "ソーシャルインパクト設計", "reason": "社会課題解決型事業の設計・資金調達スキル", "timeframe": "1〜2年"},
        "地方": {"skill": "地域連携・コミュニティ構築", "reason": "地方創生・まちづくりにおけるステークホルダー調整力", "timeframe": "1〜2年"},
    }

    # 全パスのラベル・ナラティブを結合してキーワード検出
    all_text = " ".join(p.get("label", "") + " " + p.get("direction", "") for p in paths)
    for s in paths:
        for sc in s.get("scenarios", []):
            all_text += " " + sc.get("label", "")
            for period in sc.get("periods", []):
                all_text += " " + period.get("narrative", "")[:200]

    seen_skills = set()
    for keyword, hint in path_skill_hints.items():
        if keyword in all_text and hint["skill"] not in seen_skills:
            # 既に保有しているスキルは除外
            if not any(hint["skill"][:4] in s for s in current_skills):
                relevant_paths = [chr(65+i) for i, p in enumerate(paths) if keyword in (p.get("label","") + " " + p.get("direction",""))]
                if not relevant_paths:
                    relevant_paths = [chr(65+i) for i in range(min(len(paths), 5))]
                reskill.append({
                    "skill": hint["skill"],
                    "reason": hint["reason"],
                    "priority": "高" if len(relevant_paths) >= 3 else "中" if len(relevant_paths) >= 2 else "低",
                    "timeframe": hint["timeframe"],
                    "paths": " ".join(relevant_paths[:5]),
                })
                seen_skills.add(hint["skill"])

    # 最低3つ、最大5つ
    if len(reskill) < 3:
        defaults = [
            {"skill": "デジタルリテラシー強化", "reason": "全パスで技術変化への適応力が競争優位に直結", "priority": "中", "timeframe": "今すぐ〜1年", "paths": "A B C D E"},
            {"skill": "ネットワーキング・人脈構築", "reason": "キャリアチェンジにおいて情報収集と機会創出の基盤", "priority": "中", "timeframe": "継続的", "paths": "A B C D E"},
            {"skill": "ファイナンシャルプランニング", "reason": "キャリア転換期の生活設計・リスク管理に必須", "priority": "低", "timeframe": "1〜2年", "paths": "A B C D E"},
        ]
        for d in defaults:
            if d["skill"] not in seen_skills and len(reskill) < 5:
                reskill.append(d)
                seen_skills.add(d["skill"])

    return reskill[:5]


def build_html(session_dir: str) -> str:
    # Load data
    result = load_json(os.path.join(session_dir, "multipath_result.json"))
    paths = result.get("paths", [])
    if not paths:
        print("Error: no paths in multipath_result.json", file=sys.stderr)
        sys.exit(1)
    ranking = result.get("ranking", result.get("rankings", {}))
    agents = collect_agents(session_dir)
    actions = collect_swarm_actions(session_dir)
    init_path_keywords(paths)
    comments = classify_comments(actions, agents)

    # Load candidate info
    agent_state_path = os.path.join(session_dir, "agent_state.json")
    candidate = load_json(agent_state_path) if os.path.exists(agent_state_path) else {}
    identity = candidate.get("identity", {})
    state = candidate.get("state", {})
    candidate_name = identity.get("name", "候補者")
    _gender_map = {"female": "女性", "male": "男性"}
    gender_label = _gender_map.get(identity.get("gender", ""), identity.get("gender", ""))

    # Load resume
    resume_path = os.path.join(session_dir, "resume.txt")
    resume_text = load_text(resume_path) if os.path.exists(resume_path) else ""

    # Load fact-check results if available
    fc_path = os.path.join(session_dir, "fact_check_result.json")
    fact_checks = load_json(fc_path) if os.path.exists(fc_path) else None

    # Analyze candidate
    analysis = analyze_candidate(identity, state, paths)

    # Helper: extract all periods for a path (common + likely scenario)
    def get_all_periods(p):
        """Get full period list: common_periods + likely scenario periods"""
        common = p.get("common_periods", [])
        scenarios = p.get("scenarios", [])
        # Fall back to old-style periods if no scenarios
        if not scenarios:
            return p.get("periods", [])
        # Use likely scenario, or first scenario
        likely = next((s for s in scenarios if s.get("scenario_id", "") == "likely"), scenarios[0])
        return common + likely.get("periods", [])

    def get_likely_final(p):
        """Get likely scenario final state, or path-level final_state"""
        scenarios = p.get("scenarios", [])
        if scenarios:
            likely = next((s for s in scenarios if s.get("scenario_id", "") == "likely"), scenarios[0])
            return likely.get("final_state", p.get("final_state", {}))
        return p.get("final_state", {})

    # Chart data
    path_colors = ["#818cf8", "#fbbf24", "#34d399", "#f87171", "#a78bfa"]
    # Derive period labels from actual data
    max_data_len = max(len(p.get("snapshots", get_all_periods(p))) for p in paths) if paths else 4
    if max_data_len > 4:
        period_labels = [f"Y{i}" for i in range(max_data_len)]
    else:
        period_labels = ["Year 1-2", "Year 3-5", "Year 6-8", "Year 9-10"]

    def get_chart_data_from_snapshots(p, field):
        """Extract chart data from snapshots or periods"""
        snapshots = p.get("snapshots", [])
        if snapshots:
            return [s.get(field, 0) for s in snapshots]
        all_periods = get_all_periods(p)
        return [period.get("snapshot", {}).get(field, 0) for period in all_periods]

    income_datasets = []
    for i, p in enumerate(paths):
        data = get_chart_data_from_snapshots(p, "salary")
        if not any(data):
            data = get_chart_data_from_snapshots(p, "annual_income")
        income_datasets.append({
            "label": p.get("label", p.get("path_label", f"Path {i+1}")),
            "data": data,
            "borderColor": path_colors[i % len(path_colors)],
            "backgroundColor": path_colors[i % len(path_colors)] + "20",
            "tension": 0.4, "fill": True, "pointRadius": 5,
            "pointHoverRadius": 8, "borderWidth": 3,
        })

    radar_labels = ["年収", "満足度", "WLB", "ストレス耐性"]
    radar_datasets = []
    for i, p in enumerate(paths):
        fs = get_likely_final(p)
        # Fallback to path-level final_ fields if no final_state
        salary_val = fs.get("annual_income", fs.get("salary", p.get("final_salary", 0)))
        sat_val = fs.get("satisfaction", p.get("final_satisfaction", 0))
        wlb_val = fs.get("work_life_balance", p.get("final_wlb", 0))
        stress_val = fs.get("stress", p.get("final_stress", 0))
        radar_datasets.append({
            "label": p.get("label", p.get("path_label", f"Path {i+1}")),
            "data": [
                min(salary_val / 2500 * 100, 100),
                sat_val * 100,
                wlb_val * 100,
                (1 - stress_val) * 100,
            ],
            "borderColor": path_colors[i % len(path_colors)],
            "backgroundColor": path_colors[i % len(path_colors)] + "15",
            "pointBackgroundColor": path_colors[i % len(path_colors)],
            "borderWidth": 2,
        })

    # Satisfaction over time datasets (using likely scenario)
    sat_datasets = []
    for i, p in enumerate(paths):
        sat_data = get_chart_data_from_snapshots(p, "satisfaction")
        sat_data = [_pct(v) for v in sat_data]
        sat_datasets.append({
            "label": p.get("label", p.get("path_label", f"Path {i+1}")), "data": sat_data,
            "borderColor": path_colors[i % len(path_colors)], "backgroundColor": path_colors[i % len(path_colors)] + "15",
            "tension": 0.4, "fill": False, "borderWidth": 2, "pointRadius": 4,
        })

    # Strengths HTML
    strength_icons = {
        "strategy": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>',
        "scale": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 003 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z"/></svg>',
        "product": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>',
        "data": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 20V10M12 20V4M6 20v-6"/></svg>',
        "team": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75"/></svg>',
    }

    strengths_html = ""
    for idx, s in enumerate(analysis["strengths"]):
        icon = strength_icons.get(s.get("icon", ""), strength_icons["product"])
        strengths_html += f'''
        <div class="strength-card anim-fade" style="animation-delay: {round(0.1*idx, 1)}s">
            <div class="strength-icon">{icon}</div>
            <div class="strength-body">
                <h4>{html.escape(s.get("label", ""))}</h4>
                <p>{html.escape(s["detail"])}</p>
            </div>
        </div>'''

    weaknesses_html = ""
    for idx, w in enumerate(analysis["weaknesses"]):
        weaknesses_html += f'''
        <div class="weakness-card anim-fade" style="animation-delay: {round(0.1*(idx+len(analysis["strengths"])), 1)}s">
            <h4>{html.escape(w["label"])}</h4>
            <p>{html.escape(w["detail"])}</p>
        </div>'''

    # Career timeline mini
    career_parts = identity.get("career_history_summary", "").split("→")
    career_timeline_html = ""
    career_colors = ["#f59e0b", "#8b5cf6", "#6366f1"]
    for idx, part in enumerate(career_parts):
        part = part.strip()
        color = career_colors[idx % len(career_colors)]
        career_timeline_html += f'''
        <div class="career-step anim-slide" style="animation-delay: {round(0.2*idx, 1)}s">
            <div class="career-dot" style="background: {color}"></div>
            <div class="career-label">{html.escape(part)}</div>
        </div>'''

    # Family situation
    family = state.get("family", [])
    family_html = ""
    for f in family:
        rel_labels = {"spouse": "配偶者", "child": "子供", "parent": "親",
                      "妻": "妻", "夫": "夫", "長男": "長男", "長女": "長女",
                      "次男": "次男", "次女": "次女", "母": "母", "父": "父"}
        label = rel_labels.get(f.get("relation", ""), f.get("relation", ""))
        notes = f.get("notes", "")
        family_html += f'<span class="family-tag">{label}({html.escape(str(f.get("age", 0)))}歳){" — " + html.escape(notes) if notes else ""}</span>'

    # Certifications
    certs_html = "".join(
        f'<span class="cert-tag">{html.escape(c)}</span>' for c in identity.get("certifications", [])
    )

    # Skills
    skills_html = "".join(
        f'<span class="skill-tag">{html.escape(s)}</span>' for s in state.get("skills", [])
    )

    # Helper: render a list of periods
    def render_periods(periods, color, start_idx=0):
        periods_html = ""
        for pi, period in enumerate(periods):
            ev_items = ""
            for ev in period.get("events", []):
                ev_prob = ev.get("probability")
                if ev_prob is not None:
                    ep = _pct(ev_prob)
                    ep_color = "#059669" if ep >= 40 else "#d97706" if ep >= 20 else "#dc2626"
                    ev_note = html.escape(ev.get("probability_note", ""))
                    ev_items += f'<span class="ev-tag ev-with-prob" title="{ev_note}">{html.escape(ev.get("description", ""))}<span class="ev-prob" style="background:{ep_color}">{ep}%</span></span>'
                else:
                    ev_items += f'<span class="ev-tag">{html.escape(ev.get("description", ""))}</span>'
            blocker_items = "".join(
                f'<span class="block-tag">{html.escape(b)}</span>'
                for b in period.get("blockers_active", [])
            )
            snap = period.get("snapshot", {})
            income_val = _num(snap.get("annual_income", snap.get("salary", 0)))
            narrative = period.get("narrative", "")
            if not narrative:
                # Auto-generate narrative from events
                narrative = "、".join(ev.get("description", "") for ev in period.get("events", []))
            sat_pct = _pct(snap.get("satisfaction", 0)) if snap else 0
            stress_pct = _pct(snap.get("stress", 0)) if snap else 0
            wlb_pct = _pct(snap.get("work_life_balance", 0)) if snap else 0

            income_display = f'&#165;{income_val}万' if income_val else ""
            bars_html = ""
            if snap:
                bars_html = f'''
                    <div class="period-bars">
                        <div class="mini-bar"><span class="mini-label">満足度</span><div class="mini-track"><div class="mini-fill" style="width:{sat_pct}%; background: var(--positive)"></div></div><span class="mini-val">{sat_pct}%</span></div>
                        <div class="mini-bar"><span class="mini-label">ストレス</span><div class="mini-track"><div class="mini-fill" style="width:{stress_pct}%; background: var(--negative)"></div></div><span class="mini-val">{stress_pct}%</span></div>
                        <div class="mini-bar"><span class="mini-label">WLB</span><div class="mini-track"><div class="mini-fill" style="width:{wlb_pct}%; background: var(--accent)"></div></div><span class="mini-val">{wlb_pct}%</span></div>
                    </div>'''

            periods_html += f'''
            <div class="period-row anim-fade" style="animation-delay: {round(0.05*(start_idx+pi), 2)}s">
                <div class="period-dot" style="background: {color}"></div>
                <div class="period-body">
                    <div class="period-head">
                        <span class="period-name">{html.escape(period.get("period_name", ""))}</span>
                        <span class="period-income">{income_display}</span>
                    </div>
                    <p class="period-text">{html.escape(narrative)}</p>
                    <div class="period-tags">{ev_items}{blocker_items}</div>
                    {bars_html}
                </div>
            </div>'''
        return periods_html

    # Path cards HTML
    scenario_colors = {"best": "#059669", "likely": "#6366f1", "base": "#d97706", "worst": "#dc2626"}
    scenario_icons = {"best": "★", "likely": "◎", "base": "△", "worst": "▼"}
    path_cards_html = ""
    for i, p in enumerate(paths):
        scenarios = p.get("scenarios", [])
        # Auto-generate upside/risk from best/base scenarios if missing
        raw_upside = p.get("upside", "")
        raw_risk = p.get("risk", "")
        if not raw_upside and scenarios:
            best = next((s for s in scenarios if s.get("scenario_id", "") == "best"), None)
            if best:
                best_inc = best.get("final_state", {}).get("annual_income", best.get("final_salary", "?"))
                raw_upside = f'{best.get("label", "Best")}: 年収{best_inc}万（確率{_pct(best.get("probability", 0))}%）'
        if not raw_risk and scenarios:
            base = next((s for s in scenarios if s.get("scenario_id", "") == "base"), None)
            if base:
                base_inc = base.get("final_state", {}).get("annual_income", base.get("final_salary", "?"))
                raw_risk = f'{base.get("label", "Base")}: 年収{base_inc}万（確率{_pct(base.get("probability", 0))}%）'
        risk = html.escape(raw_risk)
        upside = html.escape(raw_upside)
        common_periods = p.get("common_periods", [])
        branch_point = html.escape(p.get("branch_point", ""))
        has_scenarios = len(scenarios) > 0

        # Common periods
        common_html = render_periods(common_periods, path_colors[i]) if common_periods else ""

        # Scenario tabs
        scenarios_html = ""
        if has_scenarios:
            # Scenario summary bar: show all scenarios with probability
            scenario_bar = ""
            for s in scenarios:
                sp = _pct(s.get("probability", 0))
                sc = scenario_colors.get(s.get("scenario_id", ""), "#6366f1")
                si = scenario_icons.get(s.get("scenario_id", ""), "")
                fs = s.get("final_state", {})
                scenario_bar += f'''
                <div class="scenario-pill" style="border-color: {sc}">
                    <div class="scenario-pill-head">
                        <span class="scenario-icon" style="color: {sc}">{si}</span>
                        <strong>{html.escape(s.get("label", ""))}</strong>
                    </div>
                    <div class="scenario-pill-stats">
                        <span class="scenario-prob" style="background: {sc}">{sp}%</span>
                        <span class="scenario-income">&#165;{fs.get("annual_income", fs.get("salary", s.get("final_salary", 0)))}万</span>
                    </div>
                    <p class="scenario-pill-note">{html.escape(s.get("probability_note", ""))}</p>
                </div>'''

            scenarios_html += f'''
            <div class="branch-point anim-fade">
                <div class="branch-icon">&#x2194;</div>
                <div class="branch-text">{branch_point}</div>
            </div>
            <div class="scenario-bar">{scenario_bar}</div>'''

            # Each scenario's periods (collapsible)
            for si_idx, s in enumerate(scenarios):
                sc = scenario_colors.get(s.get("scenario_id", ""), "#6366f1")
                sp = _pct(s.get("probability", 0))
                s_periods = render_periods(s.get("periods", []), sc, start_idx=len(common_periods))
                fs = s.get("final_state", {})
                default_open = "open" if s.get("scenario_id", "") == "likely" else ""
                scenarios_html += f'''
                <details class="scenario-detail" style="border-left-color: {sc}" {default_open}>
                    <summary class="scenario-summary" style="color: {sc}">
                        <span class="scenario-icon">{scenario_icons.get(s.get("scenario_id", ""), "")}</span>
                        {html.escape(s.get("label", ""))}
                        <span class="scenario-prob-sm" style="background: {sc}">{sp}%</span>
                        <span class="scenario-final">→ &#165;{_num(fs.get("annual_income", fs.get("salary", s.get("final_salary", 0))))}万 / 満足度{_pct(fs.get("satisfaction", s.get("final_satisfaction", 0)))}%</span>
                    </summary>
                    <div class="path-timeline-wrap">
                        <div class="path-timeline-line" style="background: {sc}22"></div>
                        {s_periods}
                    </div>
                </details>'''
        else:
            # Old-style: no scenarios, just periods
            old_periods = p.get("periods", [])
            scenarios_html = render_periods(old_periods, path_colors[i])

        path_cards_html += f'''
        <div class="path-card anim-fade" id="path-{html.escape(p.get("path_id", ""))}">
            <div class="path-top" style="border-color: {path_colors[i]}">
                <div class="path-rank">#{i+1}</div>
                <div class="path-title-block">
                    <h3>{html.escape(p.get("label", ""))}</h3>
                    <span class="path-dir">{html.escape(p.get("direction", ""))}</span>
                </div>
                <div class="path-score" style="background: {path_colors[i]}">{p.get("score", 0):.2f}</div>
            </div>
            <div class="path-summary">
                <div class="path-pill upside-pill"><span class="pill-icon">+</span>{upside}</div>
                <div class="path-pill risk-pill"><span class="pill-icon">!</span>{risk}</div>
            </div>
            {"<div class='path-common-label'>共通フェーズ</div>" if common_html else ""}
            <div class="path-timeline-wrap">
                <div class="path-timeline-line" style="background: {path_colors[i]}22"></div>
                {common_html}
            </div>
            {scenarios_html}
            {{path_comments_placeholder_{p.get("path_id", "")}}}
        </div>'''

    # Build per-path comments
    def build_path_comment_mini(c):
        stance_map = {"supportive": ("var(--positive)", "+"), "opposing": ("var(--negative)", "-"),
                      "neutral": ("var(--warning)", "~"), "observer": ("var(--accent)", "?")}
        color, icon = stance_map.get(c["stance"], ("var(--text-dim)", ""))
        return f'''<div class="path-voice-item">
            <div class="path-voice-icon" style="color: {color}">{icon}</div>
            <div class="path-voice-body">
                <span class="path-voice-name">{html.escape(c["agent_name"])}</span>
                <span class="path-voice-bio">{html.escape(c["agent_bio"])}</span>
                <p class="path-voice-text">{html.escape(c["content"])}</p>
            </div>
            <span class="path-voice-round">R{c["round"]}</span>
        </div>'''

    for p in paths:
        pid = p.get("path_id", "")
        path_coms = [c for c in comments if pid in c.get("path_refs", [])]
        # Take up to 6 most relevant (mix of sentiments)
        pos_path = [c for c in path_coms if c["sentiment"] == "positive"][:3]
        neg_path = [c for c in path_coms if c["sentiment"] == "negative"][:3]
        neut_path = [c for c in path_coms if c["sentiment"] == "neutral"][:2]
        selected = (pos_path + neg_path + neut_path)[:8]
        if selected:
            voices_items = "".join(build_path_comment_mini(c) for c in selected)
            voices_section = f'''
            <div class="path-voices-section">
                <h4 class="path-voices-title">&#128172; エージェントの声 ({len(path_coms)}件中{len(selected)}件)</h4>
                {voices_items}
            </div>'''
        else:
            voices_section = ""
        placeholder = "{path_comments_placeholder_" + pid + "}"
        path_cards_html = path_cards_html.replace(placeholder, voices_section)

    # Comments HTML
    def build_comment_html(c):
        stance_map = {"supportive": ("var(--positive)", "Supportive"), "opposing": ("var(--negative)", "Opposing"),
                      "neutral": ("var(--warning)", "Neutral"), "observer": ("var(--accent)", "Observer")}
        color, label = stance_map.get(c["stance"], ("var(--muted)", ""))
        return f'''
        <div class="comment-bubble anim-fade">
            <div class="comment-avatar" style="border-color: {color}">{html.escape(c["agent_name"][0] if c.get("agent_name") else "?")}</div>
            <div class="comment-body">
                <div class="comment-meta">
                    <strong>{html.escape(c["agent_name"])}</strong>
                    <span class="comment-stance" style="color: {color}">{label}</span>
                    <span class="comment-round-tag">R{c["round"]}</span>
                </div>
                <p class="comment-bio-line">{html.escape(c["agent_bio"])}</p>
                <p class="comment-text">{html.escape(c["content"])}</p>
            </div>
        </div>'''

    pos_comments = [c for c in comments if c["sentiment"] == "positive"]
    neg_comments = [c for c in comments if c["sentiment"] == "negative"]
    neut_comments = [c for c in comments if c["sentiment"] == "neutral"]

    pos_html = "".join(build_comment_html(c) for c in pos_comments) or '<p class="empty-state">Positiveコメントなし</p>'
    neg_html = "".join(build_comment_html(c) for c in neg_comments) or '<p class="empty-state">Negativeコメントなし</p>'
    neut_html = "".join(build_comment_html(c) for c in neut_comments)

    # Split comments into mirror (copy_agent) vs external
    mirror_comments = [c for c in comments if c.get("role") == "copy_agent"]
    external_comments = [c for c in comments if c.get("role") != "copy_agent"]

    def build_agent_cards(comment_list):
        """Build agent voice cards from a list of comments"""
        cards_html = ""
        grouped = {}
        for c in comment_list:
            key = c["agent_name"]
            if key not in grouped:
                grouped[key] = {
                    "bio": c["agent_bio"], "stance": c["stance"],
                    "role": c.get("agent_role", ""), "personality": c.get("agent_personality", ""),
                    "speaking_style": c.get("agent_speaking_style", ""),
                    "background": c.get("agent_background", ""),
                    "category": c.get("agent_category", ""),
                    "positive": [], "negative": [], "neutral": [],
                }
            grouped[key][c["sentiment"]].append(c)

        category_labels = {
            "vc_investor": "VC/投資家", "vc": "VC/投資家",
            "tech_industry": "テック業界", "peer": "同僚・業界仲間",
            "hr_career": "HR/キャリア", "hr": "HR/キャリア",
            "business_strategy": "経営・戦略", "executive": "経営者",
            "private": "プライベート", "friend": "友人・知人",
            "copy_agent": "ミラー", "coach": "コーチ", "analyst": "アナリスト",
        }
        role_labels = {
            "external_evaluator": "外部評価者", "contrarian": "批判的論者",
            "copy_agent": "ミラーエージェント", "moderator": "モデレーター",
            "advisor": "アドバイザー", "mentor": "メンター",
            "critic": "批評家", "supporter": "支持者",
        }

        for aname, adata in grouped.items():
            stance_map = {"supportive": ("var(--positive)", "Supportive", "#ecfdf5"),
                          "opposing": ("var(--negative)", "Opposing", "#fef2f2"),
                          "neutral": ("var(--warning)", "Neutral", "#fffbeb"),
                          "observer": ("var(--accent)", "Observer", "#eef2ff")}
            color, slabel, bg = stance_map.get(adata["stance"], ("var(--text-dim)", "", "#f3f4f6"))
            pos_count = len(adata["positive"])
            neg_count = len(adata["negative"])
            pos_items = "".join(f'<div class="agent-quote pos-quote">{html.escape(c["content"])}<span class="q-round">R{c["round"]}</span></div>' for c in adata["positive"][:4])
            neg_items = "".join(f'<div class="agent-quote neg-quote">{html.escape(c["content"])}<span class="q-round">R{c["round"]}</span></div>' for c in adata["negative"][:4])
            neut_items = "".join(f'<div class="agent-quote neut-quote">{html.escape(c["content"])}<span class="q-round">R{c["round"]}</span></div>' for c in adata["neutral"][:2])
            all_quotes = pos_items + neg_items + neut_items
            if not all_quotes:
                continue

            # Agent profile section
            role_text = html.escape(role_labels.get(adata["role"], adata["role"])) if adata["role"] else ""
            cat_label = category_labels.get(adata["category"], adata["category"])
            profile_parts = []
            if adata["background"]:
                profile_parts.append(f'<span class="agent-profile-bg">{html.escape(adata["background"])}</span>')
            if adata["personality"]:
                profile_parts.append(f'<span class="agent-profile-personality">{html.escape(adata["personality"][:100])}</span>')
            if adata["speaking_style"]:
                profile_parts.append(f'<span class="agent-profile-style">口調: {html.escape(adata["speaking_style"][:60])}</span>')
            profile_html = "".join(profile_parts)

            # bio > background > role の優先順でペルソナ表示
            persona_text = html.escape(adata.get("bio", "") or adata["background"] or "")
            if not persona_text and role_text:
                persona_text = role_text

            cards_html += f'''
            <div class="agent-voice-card anim-fade" style="border-left-color: {color}">
                <div class="agent-voice-header" style="background: {bg}">
                    <div class="agent-voice-avatar" style="border-color: {color}">{html.escape(aname[0] if aname else "?")}</div>
                    <div class="agent-voice-info">
                        <strong>{html.escape(aname)}</strong>
                        {f'<span class="agent-voice-persona">{persona_text[:80]}</span>' if persona_text else ""}
                        {f'<span class="agent-voice-cat">{html.escape(cat_label)}</span>' if cat_label else ""}
                    </div>
                    <div class="agent-voice-tags">
                        <span class="stance-label" style="color: {color}">{slabel}</span>
                        {"<span class='sent-count pos-count'>+" + str(pos_count) + "</span>" if pos_count else ""}
                        {"<span class='sent-count neg-count'>-" + str(neg_count) + "</span>" if neg_count else ""}
                    </div>
                </div>
                {f'<div class="agent-profile-detail">{profile_html}</div>' if profile_html else ""}
                <div class="agent-voice-quotes">{all_quotes}</div>
            </div>'''
        return cards_html

    mirror_cards_html = build_agent_cards(mirror_comments)
    agent_comments_html = build_agent_cards(external_comments)

    # Macro trends section
    macro_path = os.path.join(session_dir, "macro_trends.json")
    macro_data = load_json(macro_path) if os.path.exists(macro_path) else None
    macro_trends_section = ""
    if macro_data:
        trends = macro_data.get("trends", [])
        salary_benchmarks = macro_data.get("salary_benchmarks", [])

        direction_icons = {"positive": "&#9650;", "negative": "&#9660;", "mixed": "&#9670;", "neutral": "&#8212;"}
        direction_colors = {"positive": "#22c55e", "negative": "#ef4444", "mixed": "#f59e0b", "neutral": "#94a3b8"}
        category_icons = {"technology": "&#128187;", "demographics": "&#128101;", "economy": "&#128200;",
                          "regulation": "&#128220;", "market": "&#128176;", "social": "&#127758;"}

        trend_cards = ""
        for t in trends:
            cat_icon = category_icons.get(t.get("category", ""), "&#128300;")
            impact_rows = ""
            for pid, impact in t.get("impact_by_path", {}).items():
                path_label = next((p.get("label", p.get("path_label", pid)) for p in paths if p.get("path_id", "") == pid), pid)
                d_icon = direction_icons.get(impact.get("direction", "neutral"), "&#8212;")
                d_color = direction_colors.get(impact.get("direction", "neutral"), "#94a3b8")
                mag = impact.get("magnitude", "medium")
                mag_dots = {"high": "&#9679;&#9679;&#9679;", "medium": "&#9679;&#9679;&#9675;", "low": "&#9679;&#9675;&#9675;"}.get(mag, "&#9679;&#9675;&#9675;")
                impact_rows += f'<div class="macro-impact-row"><span class="macro-path-label">{html.escape(path_label[:10])}</span><span style="color:{d_color}">{d_icon}</span><span class="macro-mag">{mag_dots}</span><span class="macro-detail">{html.escape(impact.get("detail", "")[:60])}</span></div>'

            sources_html = "".join(f'<span class="macro-src">{html.escape(s.get("title", "")[:40])}</span>' for s in t.get("sources", [])[:2])

            trend_cards += f'''
            <div class="glass anim-fade" style="padding: 20px 24px; margin-bottom: 12px;">
                <div style="display:flex; align-items:center; gap:10px; margin-bottom:8px;">
                    <span style="font-size:1.3rem">{cat_icon}</span>
                    <div>
                        <strong style="font-size:0.95rem">{html.escape(t.get("label", ""))}</strong>
                        <span style="font-size:0.75rem; color:var(--text-dim); margin-left:8px">{html.escape(t.get("timeframe", ""))}</span>
                        <span style="font-size:0.72rem; background:rgba(99,102,241,0.1); padding:1px 8px; border-radius:10px; margin-left:4px;">確率 {_pct(t.get("probability", 0))}%</span>
                    </div>
                </div>
                <p style="font-size:0.82rem; color:var(--text-muted); margin-bottom:10px; line-height:1.6">{html.escape(t.get("description", ""))}</p>
                <div class="macro-impacts">{impact_rows}</div>
                <div class="macro-sources">{sources_html}</div>
            </div>'''

        # Salary benchmarks table
        bench_rows = ""
        for b in salary_benchmarks:
            bench_rows += f'<tr><td>{html.escape(str(b.get("role", "")))}</td><td style="text-align:right; font-weight:600">&#165;{html.escape(str(b.get("range", "")))}</td><td style="font-size:0.78rem; color:var(--text-dim)">{html.escape(str(b.get("source", "")))}</td><td style="font-size:0.75rem; color:var(--text-dim)">{html.escape(str(b.get("note", "")))}</td></tr>'

        macro_trends_section = f'''
<div class="section" id="macro">
    <div class="section-header">
        <span class="section-num">09</span>
        <h2 class="section-title">マクロトレンド&社会リスク</h2>
    </div>
    <p class="section-subtitle">2026-2035年の主要トレンドと各パスへの影響度</p>
    {trend_cards}
    <div class="glass anim-fade" style="padding: 20px 24px; margin-top: 16px;">
        <h4 style="margin-bottom: 12px;">&#128176; 給与ベンチマーク（市場データ）</h4>
        <div style="overflow-x: auto;">
            <table class="sim-table">
                <thead><tr><th>ポジション</th><th style="text-align:right">年収レンジ</th><th>出典</th><th>備考</th></tr></thead>
                <tbody>{bench_rows}</tbody>
            </table>
        </div>
    </div>
</div>'''

    # Zep Knowledge Graph visualization section
    zep_graph_section = ""
    # Build a graph from resume + simulation data
    # Nodes: candidate, companies, skills, paths
    graph_nodes = []
    graph_edges = []
    node_id = 0

    # Central node: candidate
    graph_nodes.append({"id": "candidate", "label": candidate_name, "group": "person", "size": 30})

    # Companies from career history
    career_text = identity.get("career_history_summary", "")
    companies = []
    for segment in career_text.split("→"):
        segment = segment.strip()
        if "(" in segment:
            company = segment.split("(")[0].strip()
        else:
            company = segment.strip()
        if company and len(company) < 30:
            companies.append(company)
    for comp in companies:
        cid = f"comp_{node_id}"
        node_id += 1
        graph_nodes.append({"id": cid, "label": comp, "group": "company"})
        graph_edges.append({"from": "candidate", "to": cid, "label": "経歴"})

    # Skills
    for skill in state.get("skills", [])[:8]:
        sid = f"skill_{node_id}"
        node_id += 1
        graph_nodes.append({"id": sid, "label": skill, "group": "skill"})
        graph_edges.append({"from": "candidate", "to": sid, "label": "スキル"})

    # Paths
    path_id_set = set()
    for p in paths:
        pid = p.get("path_id", "")
        path_id_set.add(pid)
        plabel = p.get("label", p.get("path_label", pid))
        graph_nodes.append({"id": pid, "label": plabel, "group": "path"})
        graph_edges.append({"from": "candidate", "to": pid, "label": "キャリアパス"})
        # Add scenario nodes
        for s in p.get("scenarios", []):
            sc_id = f"{pid}_{s['scenario_id']}"
            graph_nodes.append({"id": sc_id, "label": f"{s.get('label', '')} ({_pct(s.get('probability',0))}%)", "group": f"scenario_{s.get('scenario_id', '')}"})
            graph_edges.append({"from": pid, "to": sc_id, "label": s.get("scenario_id", "")})

    # Swarm agents as nodes
    category_group_map = {
        "vc_investor": "agent_vc", "vc": "agent_vc",
        "tech_industry": "agent_tech", "peer": "agent_tech",
        "hr_career": "agent_hr", "hr": "agent_hr", "coach": "agent_hr",
        "business_strategy": "agent_biz", "executive": "agent_biz", "analyst": "agent_biz",
        "private": "agent_private", "friend": "agent_private",
        "copy_agent": "agent_mirror",
    }
    stance_labels = {"supportive": "支持", "opposing": "批判", "neutral": "中立"}
    for aid, ainfo in agents.items():
        is_copy = ainfo.get("is_copy_agent", ainfo.get("role") == "copy_agent")
        cat = ainfo.get("category", "")
        group = category_group_map.get(cat, "agent_mirror" if is_copy else "agent_tech")
        aname = ainfo.get("name", aid)
        arole = ainfo.get("role", "")
        graph_role_labels = {
            "external_evaluator": "外部評価者", "contrarian": "批判的論者",
            "copy_agent": "ミラーエージェント", "moderator": "モデレーター",
            "advisor": "アドバイザー", "mentor": "メンター",
        }
        graph_nodes.append({
            "id": aid, "label": aname, "group": group,
            "detail": graph_role_labels.get(arole, arole),
            "personality": ainfo.get("personality", "")[:80],
            "background": ainfo.get("background", "")[:80],
            "speaking_style": ainfo.get("speaking_style", "")[:60],
        })
        # Edge: agent → candidate (評価)
        stance = ainfo.get("stance_default", ainfo.get("stance", "neutral"))
        graph_edges.append({"from": aid, "to": "candidate", "label": stance_labels.get(stance, stance)})
        # Edge: agent → path (関心パス)
        path_ref = ainfo.get("path_ref", "")
        if path_ref and path_ref in path_id_set:
            graph_edges.append({"from": aid, "to": path_ref, "label": "注目"})

    graph_nodes_json = safe_json_embed(graph_nodes)
    graph_edges_json = safe_json_embed(graph_edges)

    zep_graph_section = f'''
<div class="section" id="graph">
    <div class="section-header">
        <span class="section-num">10</span>
        <h2 class="section-title">ナレッジグラフ</h2>
    </div>
    <p class="section-subtitle">候補者の経歴・スキル・キャリアパスの関係性マップ（ドラッグ＆ズーム対応）</p>
    <div class="glass anim-fade" style="padding: 0; position: relative; overflow: hidden; border-radius: 16px;">
        <svg id="graphSvg" style="width:100%; height:800px; background: #fafbfe;" role="img" aria-label="キャリアパス関係図"></svg>
        <div id="graphLegend" style="position:absolute; bottom:12px; left:16px; display:flex; gap:12px; flex-wrap:wrap; font-size:0.75rem; color:var(--text-dim);"></div>
        <div id="graphDetail" style="display:none; position:absolute; top:12px; right:12px; width:280px; background:var(--glass); backdrop-filter:blur(16px); border:1px solid var(--glass-border); border-radius:12px; padding:16px; box-shadow:var(--shadow-md); font-size:0.82rem;"></div>
    </div>
</div>'''

    # Reskilling: パスデータから動的に生成
    reskill_data = _derive_reskilling(paths, state, identity)
    reskill_html = ""
    for idx, r in enumerate(reskill_data):
        p_color = {"高": "#ef4444", "中": "#fbbf24", "低": "#34d399"}[r["priority"]]
        path_dots = "".join(f'<span class="path-dot-mini" style="background: {path_colors[ord(c)-65]}">{c}</span>' for c in r["paths"].split() if ord(c)-65 < 5)
        reskill_html += f'''
        <div class="reskill-row anim-fade" style="animation-delay: {round(0.08*idx, 2)}s">
            <div class="reskill-priority" style="background: {p_color}">{r["priority"]}</div>
            <div class="reskill-content">
                <h4>{html.escape(r["skill"])}</h4>
                <p>{html.escape(r["reason"])}</p>
                <div class="reskill-meta">
                    <span class="reskill-time">{html.escape(r["timeframe"])}</span>
                    <span class="reskill-paths">関連パス: {path_dots}</span>
                </div>
            </div>
        </div>'''

    # Build god's-eye narrative: expected value across all paths x scenarios
    expected_income = 0
    expected_satisfaction = 0
    total_weight = 0
    for p in paths:
        scenarios = p.get("scenarios", [])
        for s in scenarios:
            prob = s.get("probability", 0)
            fs = s.get("final_state", {})
            inc = fs.get("annual_income", fs.get("salary", s.get("final_salary", p.get("final_salary", 0))))
            sat = fs.get("satisfaction", s.get("final_satisfaction", p.get("final_satisfaction", 0)))
            expected_income += prob * inc
            expected_satisfaction += prob * sat
            total_weight += prob
    if total_weight > 0:
        expected_income = int(expected_income / total_weight)
        expected_satisfaction = int(expected_satisfaction / total_weight * 100)
    else:
        expected_income = 0
        expected_satisfaction = 0

    # Most likely outcomes per path
    likely_outcomes = []
    for p in paths:
        scenarios = p.get("scenarios", [])
        likely = next((s for s in scenarios if s.get("scenario_id", "") == "likely"), None)
        if likely:
            fs = likely.get("final_state", {})
            likely_outcomes.append({
                "label": p.get("label", ""),
                "scenario": likely.get("label", ""),
                "probability": _pct(likely.get("probability", 0)),
                "income": fs.get("annual_income", 0),
                "satisfaction": _pct(fs.get("satisfaction", 0)),
            })

    # 自己認知 vs 神の視点 — データから動的生成
    # 自己認知: 現在のロール・スキル・経歴から構築
    _self_skills_top = ", ".join(state.get("skills", [])[:3]) if state.get("skills") else "未記載"
    _self_career = identity.get("career_history_summary", "").replace("→", "、") if identity.get("career_history_summary") else ""
    _self_text = (
        f'{html.escape(candidate_name)}は現在{html.escape(state.get("employer", ""))}の'
        f'{html.escape(state.get("role", ""))}として活躍中。'
        f'{html.escape(state.get("industry", ""))}業界で{state.get("years_in_role", 0)}年の経験を持ち、'
        f'主要スキルとして{html.escape(_self_skills_top)}を強みと認識している。'
    )
    if _self_career:
        _self_text += f'キャリアパスは{html.escape(_self_career[:80])}。'

    # 神の視点: Bestパスとbaseパスの対比から動的生成
    best_path = max(paths, key=lambda p: max((s.get("final_state", {}).get("annual_income", 0) for s in p.get("scenarios", [{}])), default=0)) if paths else {}
    base_scenarios = [(p, s) for p in paths for s in p.get("scenarios", []) if s.get("scenario_id") == "base"]
    worst_base = min(base_scenarios, key=lambda x: x[1].get("final_state", {}).get("annual_income", float("inf"))) if base_scenarios else (None, None)

    _gods_text = (
        f'{len(agents)}人のSwarmエージェント分析による確率加重結果は'
        f'年収{expected_income}万円・満足度{expected_satisfaction}%。'
    )
    if best_path and best_path.get("scenarios"):
        best_sc = next((s for s in best_path.get("scenarios", []) if s.get("scenario_id", "") == "best"), best_path.get("scenarios", [{}])[0] if best_path.get("scenarios") else {})
        best_inc = best_sc.get("final_state", {}).get("annual_income", 0)
        _gods_text += f'最も上振れするのは「{html.escape(best_path.get("label", "")[:20])}」のBestシナリオ（年収{int(best_inc)}万円）だが、'
    if worst_base[0]:
        worst_inc = worst_base[1].get("final_state", {}).get("annual_income", 0)
        _gods_text += f'一方「{html.escape(worst_base[0].get("label", "")[:20])}」のBaseシナリオでは年収{int(worst_inc)}万円まで低下するリスクもある。'
    _gods_text += f'期待値ベースでの最適な選択肢を冷静に見極めることが重要。'

    self_vs_gods_html = f'''
    <div class="glass anim-fade" style="padding: 28px 32px;">
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 24px;">
            <div>
                <h4 style="margin-bottom: 12px; display: flex; align-items: center; gap: 8px;">
                    <span style="font-size: 1.3rem;">&#128100;</span> 自己認知
                </h4>
                <p style="font-size: 0.88rem; color: var(--text-muted); line-height: 1.8;">
                    {_self_text}
                </p>
            </div>
            <div>
                <h4 style="margin-bottom: 12px; display: flex; align-items: center; gap: 8px;">
                    <span style="font-size: 1.3rem;">&#128065;</span> 神の視点
                </h4>
                <p style="font-size: 0.88rem; color: var(--text-muted); line-height: 1.8;">
                    {_gods_text}
                </p>
            </div>
        </div>
    </div>'''

    # シミュレーション結果パネル — 各パス×シナリオの計算根拠を明示
    sim_sc_colors = {"best": "#22c55e", "likely": "#6366f1", "base": "#f59e0b"}
    sim_detail_rows = ""
    for p in paths:
        scenarios = p.get("scenarios", [])
        for s in scenarios:
            prob = _num(s.get("probability", 0), 0.0)
            fs = s.get("final_state", {})
            # Support both final_state.annual_income and direct final_salary
            inc = _num(fs.get("annual_income", fs.get("salary", s.get("final_salary", p.get("final_salary", 0)))))
            sat = _num(fs.get("satisfaction", s.get("final_satisfaction", p.get("final_satisfaction", 0))), 0.0)
            weighted_inc = int(prob * inc)
            weighted_sat = int(prob * sat * 100)
            sc = sim_sc_colors.get(s.get("scenario_id", ""), "#94a3b8")
            sim_detail_rows += f"""
            <tr>
                <td style="font-weight:500">{html.escape(p.get("label", p.get("path_label", ""))[:20])}</td>
                <td><span style="color:{sc}; font-weight:600">{html.escape(s.get("label", "")[:30])}</span></td>
                <td style="text-align:right">{_pct(prob)}%</td>
                <td style="text-align:right">&#165;{inc}万</td>
                <td style="text-align:right">{_pct(sat)}%</td>
                <td style="text-align:right; color:var(--accent); font-weight:600">&#165;{weighted_inc}万</td>
            </tr>"""

    gods_eye_html = f'''
    <div class="glass anim-fade" style="padding: 28px 32px; margin-bottom: 24px;">
        <h3 style="font-size: 1.2rem; margin-bottom: 6px;">
            シミュレーション結果 — 5パス×3シナリオの確率加重分析
        </h3>
        <p style="font-size: 0.8rem; color: var(--text-dim); margin-bottom: 20px;">
            各パスのBest/Likely/Baseシナリオの確率×年収で期待値を算出。{len(paths)}パス×{sum(len(p.get("scenarios",[])) for p in paths)}シナリオ、{sum(len(get_all_periods(p)) for p in paths)*10}年分のシミュレーションに基づく
        </p>

        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 24px;">
            <div class="stat-box">
                <div class="stat-num">{expected_income}<span style="font-size:0.8rem">万</span></div>
                <div class="stat-label">期待年収（確率加重平均）</div>
            </div>
            <div class="stat-box">
                <div class="stat-num">{expected_satisfaction}<span style="font-size:0.8rem">%</span></div>
                <div class="stat-label">期待満足度（確率加重平均）</div>
            </div>
        </div>

        <div style="overflow-x: auto;">
            <table class="sim-table">
                <thead>
                    <tr>
                        <th>パス</th>
                        <th>シナリオ</th>
                        <th style="text-align:right">確率</th>
                        <th style="text-align:right">年収</th>
                        <th style="text-align:right">満足度</th>
                        <th style="text-align:right">加重年収</th>
                    </tr>
                </thead>
                <tbody>
                    {sim_detail_rows}
                </tbody>
                <tfoot>
                    <tr style="border-top: 2px solid var(--accent); font-weight: 700;">
                        <td colspan="5">確率加重合計（期待値）</td>
                        <td style="text-align:right; color: var(--accent); font-size: 1.1rem;">&#165;{expected_income}万</td>
                    </tr>
                </tfoot>
            </table>
        </div>

        <p style="font-size: 0.78rem; color: var(--text-dim); margin-top: 12px; line-height: 1.6;">
            ※ 加重年収 = 確率 × 年収。期待値 = 全シナリオの加重年収の合計を確率合計で正規化。<br>
            ※ 確率はSubAgentによるキャリア遷移シミュレーションの推定値。{len(paths)}パス×{sum(len(p.get("scenarios",[])) for p in paths)}シナリオの分析に基づく。
        </p>
    </div>'''

    # Fact-check section
    fact_check_html = ""
    if fact_checks:
        fc_meta = fact_checks.get("fact_check_metadata", {})
        fc_checks = fact_checks.get("checks", [])
        fc_total = fc_meta.get("total_claims", len(fc_checks))
        fc_verified = fc_meta.get("verified", 0)
        fc_adjusted = fc_meta.get("adjusted", 0)
        fc_unverified = fc_meta.get("unverified", 0)
        fc_disputed = fc_meta.get("disputed", 0)

        # Status bar
        if fc_total > 0:
            pct_v = int(fc_verified / fc_total * 100)
            pct_a = int(fc_adjusted / fc_total * 100)
            pct_u = int(fc_unverified / fc_total * 100)
            pct_d = int(fc_disputed / fc_total * 100)
        else:
            pct_v = pct_a = pct_u = pct_d = 0

        # Detail rows for flagged items
        flagged_rows = ""
        for c in fc_checks:
            status = c.get("status", "unverified")
            if status == "verified":
                icon, color, bg = "&#10003;", "#22c55e", "#ecfdf5"
            elif status == "adjusted":
                icon, color, bg = "&#9888;", "#f59e0b", "#fffbeb"
            elif status == "disputed":
                icon, color, bg = "&#10007;", "#ef4444", "#fef2f2"
            else:
                icon, color, bg = "?", "#94a3b8", "#f8fafc"

            sources_html = ""
            for src in c.get("sources", [])[:2]:
                rel_badge = {"high": "#22c55e", "medium": "#f59e0b", "low": "#94a3b8"}.get(src.get("reliability", ""), "#94a3b8")
                sources_html += f'<span class="fc-source"><span class="fc-rel-dot" style="background:{rel_badge}"></span>{html.escape(src.get("title", "")[:40])}</span>'

            correction = ""
            if c.get("suggested_correction"):
                sc = c["suggested_correction"]
                correction = f'<div class="fc-correction">修正提案: {html.escape(str(sc.get("value", "")))} {html.escape(sc.get("note_addition", "")[:60])}</div>'

            flagged_rows += f'''
            <div class="fc-row" style="border-left-color: {color}">
                <div class="fc-icon" style="color: {color}">{icon}</div>
                <div class="fc-body">
                    <div class="fc-location">{html.escape(c.get("location", ""))}</div>
                    <div class="fc-values">
                        <span>元の値: <strong>{html.escape(str(c.get("original_value", "")))}</strong></span>
                        <span>検証値: <strong style="color:{color}">{html.escape(str(c.get("verified_value", "N/A")))}</strong></span>
                    </div>
                    <div class="fc-note">{html.escape(c.get("note", "")[:120])}</div>
                    {correction}
                    <div class="fc-sources">{sources_html}</div>
                </div>
            </div>'''

        fact_check_html = f'''
    <div class="glass anim-fade" style="padding: 24px 28px; margin-top: 20px;">
        <h4 style="margin-bottom: 12px; display: flex; align-items: center; gap: 8px;">
            <span style="font-size: 1.2rem;">&#128270;</span> ファクトチェック結果
        </h4>
        <p style="font-size: 0.8rem; color: var(--text-dim); margin-bottom: 16px;">
            {fc_total}件の確率・統計データをWeb検索で検証（{html.escape(fc_meta.get("checked_at", "")[:10])}）
        </p>

        <div class="fc-bar">
            <div class="fc-bar-seg" style="width:{pct_v}%; background:#22c55e" title="Verified {fc_verified}"></div>
            <div class="fc-bar-seg" style="width:{pct_a}%; background:#f59e0b" title="Adjusted {fc_adjusted}"></div>
            <div class="fc-bar-seg" style="width:{pct_u}%; background:#94a3b8" title="Unverified {fc_unverified}"></div>
            <div class="fc-bar-seg" style="width:{pct_d}%; background:#ef4444" title="Disputed {fc_disputed}"></div>
        </div>
        <div class="fc-legend">
            <span><span class="fc-dot" style="background:#22c55e"></span>検証済 {fc_verified}</span>
            <span><span class="fc-dot" style="background:#f59e0b"></span>要調整 {fc_adjusted}</span>
            <span><span class="fc-dot" style="background:#94a3b8"></span>未検証 {fc_unverified}</span>
            <span><span class="fc-dot" style="background:#ef4444"></span>要修正 {fc_disputed}</span>
        </div>

        <details style="margin-top: 16px;">
            <summary style="cursor: pointer; font-size: 0.85rem; font-weight: 600; color: var(--accent);">
                検証詳細を表示（{len(fc_checks)}件）
            </summary>
            <div class="fc-details" style="margin-top: 12px;">
                {flagged_rows}
            </div>
        </details>
    </div>'''

    # Core competencies section: extract skill/strength-related comments from agents
    skill_keywords = [
        "強み", "武器", "希少", "適性", "フィット", "活かせる", "実績", "知見",
        "転用可能", "スキル", "経験", "専門", "能力", "才能", "素質", "資質",
        "ポテンシャル", "コンピテンシー", "リーダーシップ", "戦略",
    ]
    # パス固有の未来シナリオを除外するキーワード
    future_exclude = [
        "CPO就任", "VP昇進", "起業", "転職", "独立", "シード", "シリーズA",
        "IPO", "GAFA", "freee", "LayerX", "Path A", "Path B", "Path C",
        "Path D", "Path E", "パスA", "パスB", "パスC", "パスD", "パスE",
        "path_a", "path_b", "path_c", "path_d", "path_e",
        "年収", "確率", "シナリオ", "ルート",
    ]
    core_quotes = []
    for c in comments:
        # 早期ラウンド（R1-R10）に限定し、パス固有の未来議論を除外
        if c["round"] > 10:
            continue
        if not any(kw in c["content"] for kw in skill_keywords):
            continue
        if sum(1 for kw in future_exclude if kw in c["content"]) >= 2:
            continue
        core_quotes.append(c)
    # Deduplicate by content, limit to 8
    seen_contents = set()
    unique_core = []
    for c in core_quotes:
        if c["content"] not in seen_contents:
            seen_contents.add(c["content"])
            unique_core.append(c)
    unique_core = unique_core[:8]

    core_quotes_html = ""
    for c in unique_core:
        stance_map = {"supportive": "#22c55e", "opposing": "#ef4444", "neutral": "#eab308", "observer": "#6366f1"}
        dot_color = stance_map.get(c["stance"], "#94a3b8")
        core_quotes_html += f'''
        <div class="core-quote-item anim-fade">
            <div class="core-quote-dot" style="background: {dot_color}"></div>
            <div class="core-quote-body">
                <p class="core-quote-text">{html.escape(c["content"])}</p>
                <span class="core-quote-attr">— {html.escape(c["agent_name"])}（{html.escape(c["agent_bio"][:30])}）R{c["round"]}</span>
            </div>
        </div>'''

    core_competencies_html = f'''
    <div class="glass anim-fade" style="padding: 28px 32px;">
        <h3 style="font-size: 1.1rem; margin-bottom: 8px;">
            &#127919; 30人のエージェントが語る「この人の本質」
        </h3>
        <p style="font-size: 0.82rem; color: var(--text-muted); margin-bottom: 20px;">
            Swarm {len(actions)}件の会話から、候補者のスキル・強みに言及した発言を抽出
        </p>
        <div class="core-quotes-grid">
            {core_quotes_html if core_quotes_html else '<p style="color: var(--text-dim); font-size: 0.85rem;">スキル・強みに関するエージェント発言はまだありません</p>'}
        </div>
    </div>'''

    # Conclusion section
    top_path = paths[0] if paths else {}
    top_label = top_path.get("label", "")
    top_score = top_path.get("score", 0)
    top_direction = top_path.get("direction", "")
    num_paths = len(paths)
    conclusion_risks = []
    for p in paths[:3]:
        r = p.get("risk", "")
        if r:
            conclusion_risks.append(f'{html.escape(p.get("label", ""))}: {html.escape(r)}')
    risks_html = "".join(f"<li>{r}</li>" for r in conclusion_risks) if conclusion_risks else "<li>特になし</li>"

    conclusion_section = f'''
<div class="section" id="conclusion">
    <div class="section-header">
        <span class="section-num">11</span>
        <h2 class="section-title">まとめ</h2>
    </div>
    <div class="glass anim-fade" style="padding: 28px 32px;">
        <h3 style="font-size: 1.05rem; margin-bottom: 16px;">シミュレーション総括</h3>
        <p style="font-size: 0.88rem; line-height: 1.8; margin-bottom: 16px;">
            {num_paths}つのキャリアパスを多角的に分析した結果、
            <strong>{html.escape(top_label)}</strong>（{html.escape(top_direction)}）が
            総合スコア {top_score:.2f} で最も高い評価となりました。
            ただし、スコアは年収・満足度・ストレス・WLBの加重平均であり、
            候補者の価値観によって最適なパスは異なります。
        </p>
        <p style="font-size: 0.88rem; line-height: 1.8; margin-bottom: 16px;">
            期待年収（全パス加重平均）: <strong>{expected_income}万円</strong>、
            期待満足度: <strong>{expected_satisfaction}%</strong>
        </p>
        <h4 style="font-size: 0.92rem; margin-bottom: 8px;">上位パスの主要リスク</h4>
        <ul style="font-size: 0.85rem; line-height: 1.8; padding-left: 20px; margin-bottom: 16px;">
            {risks_html}
        </ul>
        <div style="margin-top: 24px; padding: 24px 28px; background: linear-gradient(135deg, #eef2ff, #f5f3ff); border-radius: 14px; border: 1px solid #c7d2fe;">
            <h4 style="font-size: 0.95rem; font-weight: 700; margin-bottom: 16px; color: var(--accent);">
                推奨アクション
            </h4>
            <ol style="font-size: 0.88rem; line-height: 1.9; padding-left: 20px; color: var(--text-muted);">
                <li><strong>30日以内:</strong> 推奨パスの現職者にLinkedIn等でコンタクトし情報収集</li>
                <li><strong>90日以内:</strong> 不足スキルの学習を開始（オンライン講座・資格取得）</li>
                <li><strong>6ヶ月以内:</strong> 目標ポジションの求人を定期確認し、JD要件とのギャップを測定</li>
            </ol>
        </div>
        <p style="font-size: 0.82rem; color: var(--text-dim); margin-top: 16px;">
            本レポートはAIシミュレーションに基づく参考情報です。
            実際のキャリア選択は、個人の価値観・家庭事情・市場環境を総合的に判断してください。
        </p>
    </div>
</div>'''

    # Nav items
    nav_items = [
        ("profile", "プロフィール"), ("core", "根源的スキル"), ("overview", "神の視点"), ("salary", "年収推移"),
        ("paths", "キャリアパス"), ("reskill", "リスキリング"), ("mirror", "自分のミラー"), ("voices", "外部の声"),
        ("macro", "マクロトレンド"), ("graph", "ナレッジグラフ"), ("conclusion", "まとめ"),
    ]
    nav_html = "".join(f'<a href="#{nid}" class="nav-link">{nlabel}</a>' for nid, nlabel in nav_items)

    max_round = max((a.get("round_num", a.get("round", 0)) for a in actions), default=0)

    return f'''<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MiroFish Career Report — {html.escape(candidate_name)}</title>
<meta http-equiv="Content-Security-Policy" content="object-src 'none'; base-uri 'none';">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js" integrity="sha384-vsrfeLOOY6KuIYKDlmVH5UiBmgIdB1oEf7p01YgWHuqmOHfZr374+odEv96n9tNC" crossorigin="anonymous"></script>
<script src="https://cdn.jsdelivr.net/npm/d3@7.9.0/dist/d3.min.js" integrity="sha384-CjloA8y00+1SDAUkjs099PVfnY2KmDC2BZnws9kh8D/lX1s46w6EPhpXdqMfjK6i" crossorigin="anonymous"></script>
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=Noto+Sans+JP:wght@300;400;500;600;700&display=swap');
:root {{
    --bg: #f8f9fc; --bg2: #f0f2f8; --surface: #ffffff; --surface2: #f3f4f8;
    --glass: rgba(255,255,255,0.85); --glass-border: rgba(99,102,241,0.12);
    --text: #1a1d2e; --text-muted: #4b5268; --text-dim: #5a6278;
    --accent: #6366f1; --accent2: #4f46e5; --accent-glow: rgba(99,102,241,0.08);
    --positive: #059669; --negative: #dc2626; --warning: #d97706;
    --grad1: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    --grad2: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
    --grad3: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
    --shadow-sm: 0 1px 3px rgba(0,0,0,0.06);
    --shadow-md: 0 4px 16px rgba(0,0,0,0.06);
    --shadow-lg: 0 8px 30px rgba(0,0,0,0.08);
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
html {{ scroll-behavior: smooth; }}
body {{
    font-family: 'Inter', 'Noto Sans JP', sans-serif;
    background: var(--bg); color: var(--text); line-height: 1.7;
    overflow-x: hidden;
}}
::selection {{ background: rgba(99,102,241,0.15); }}

/* Animations */
@keyframes fadeUp {{ from {{ opacity: 0; transform: translateY(30px); }} to {{ opacity: 1; transform: translateY(0); }} }}
@keyframes slideIn {{ from {{ opacity: 0; transform: translateX(-20px); }} to {{ opacity: 1; transform: translateX(0); }} }}
@keyframes pulse {{ 0%,100% {{ opacity: 1; }} 50% {{ opacity: 0.5; }} }}
@keyframes shimmer {{ 0% {{ background-position: -200% 0; }} 100% {{ background-position: 200% 0; }} }}
@keyframes float {{ 0%,100% {{ transform: translateY(0px); }} 50% {{ transform: translateY(-8px); }} }}
@keyframes gradientShift {{ 0% {{ background-position: 0% 50%; }} 50% {{ background-position: 100% 50%; }} 100% {{ background-position: 0% 50%; }} }}

.anim-fade {{ opacity: 0; animation: fadeUp 0.6s ease-out forwards; }}
.anim-slide {{ opacity: 0; animation: slideIn 0.5s ease-out forwards; }}

/* Navigation */
.nav-bar {{
    position: fixed; top: 0; left: 0; right: 0; z-index: 100;
    background: rgba(255,255,255,0.9); backdrop-filter: blur(20px);
    border-bottom: 1px solid #e5e7eb;
    display: flex; align-items: center; justify-content: center;
    padding: 0 24px; height: 56px; gap: 4px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}}
.nav-link {{
    color: var(--text-muted); text-decoration: none; padding: 8px 16px;
    border-radius: 8px; font-size: 0.85rem; font-weight: 500;
    transition: all 0.3s;
}}
.nav-link:hover {{ color: var(--accent); background: var(--accent-glow); }}
.nav-logo {{ font-weight: 700; color: var(--accent); margin-right: 16px; font-size: 1rem; }}

/* Hero */
.hero {{
    padding: 120px 24px 60px; text-align: center; position: relative;
    background: linear-gradient(180deg, #eef0ff 0%, var(--bg) 100%);
}}
.hero::before {{
    content: ''; position: absolute; top: 0; left: 0; right: 0; bottom: 0;
    background: url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%236366f1' fill-opacity='0.04'%3E%3Cpath d='M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E");
    pointer-events: none;
}}
.hero-label {{
    display: inline-block; padding: 6px 20px; border-radius: 100px;
    background: var(--accent-glow); border: 1px solid var(--glass-border);
    font-size: 0.8rem; color: var(--accent); font-weight: 600; letter-spacing: 0.05em;
    margin-bottom: 20px; text-transform: uppercase;
}}
.hero h1 {{ font-size: 3rem; font-weight: 800; letter-spacing: -0.02em; margin-bottom: 8px; }}
.hero h1 span {{
    background: linear-gradient(135deg, #818cf8, #c084fc, #f472b6);
    background-size: 200% 200%; animation: gradientShift 4s ease infinite;
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
}}
.hero-sub {{ color: var(--text-muted); font-size: 1.1rem; margin-bottom: 32px; }}

/* Profile Section */
.container {{ max-width: 1120px; margin: 0 auto; padding: 0 24px; }}
.section {{ margin: 64px 0; scroll-margin-top: 72px; }}
:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 3px; border-radius: 4px; }}
.section-header {{
    display: flex; align-items: center; gap: 12px; margin-bottom: 32px;
}}
.section-num {{
    font-size: 0.75rem; font-weight: 700; color: var(--accent);
    border: 1px solid var(--accent); border-radius: 6px;
    padding: 4px 10px; letter-spacing: 0.1em;
}}
.section-title {{ font-size: 1.6rem; font-weight: 700; letter-spacing: -0.01em; }}
.section-subtitle {{ color: var(--text-muted); margin-top: -20px; margin-bottom: 28px; }}

/* Glass card */
.glass {{
    background: var(--glass); border: 1px solid var(--glass-border);
    border-radius: 16px; backdrop-filter: blur(12px);
}}

/* Profile card */
.profile-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }}
.profile-main {{ padding: 32px; }}
.profile-name {{ font-size: 1.8rem; font-weight: 700; margin-bottom: 4px; }}
.profile-role {{ color: var(--accent); font-size: 1rem; margin-bottom: 16px; }}
.profile-meta {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 16px; }}
.meta-chip {{
    background: var(--surface2); padding: 4px 12px; border-radius: 100px;
    font-size: 0.8rem; color: var(--text-muted);
}}
.profile-career {{ margin-top: 20px; }}
.career-flow {{ display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-top: 8px; }}
.career-step {{ display: flex; align-items: center; gap: 6px; }}
.career-dot {{ width: 10px; height: 10px; border-radius: 50%; }}
.career-label {{ font-size: 0.85rem; font-weight: 500; }}
.career-arrow {{ color: var(--text-dim); font-size: 1.2rem; }}

.profile-side {{ padding: 32px; border-left: 1px solid var(--glass-border); }}
.profile-stats {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
.stat-box {{ text-align: center; padding: 16px; background: var(--surface2); border-radius: 12px; }}
.stat-num {{ font-size: 1.8rem; font-weight: 700; color: var(--accent); }}
.stat-label {{ font-size: 0.75rem; color: var(--text-muted); margin-top: 2px; }}

.tag-row {{ display: flex; flex-wrap: wrap; gap: 6px; margin-top: 12px; }}
.cert-tag {{
    background: #eef2ff; border: 1px solid #c7d2fe;
    padding: 3px 10px; border-radius: 6px;
    font-size: 0.78rem; color: var(--accent); font-weight: 500;
}}
.skill-tag {{
    background: var(--surface2); padding: 3px 10px; border-radius: 6px;
    font-size: 0.78rem; color: var(--text-muted);
}}
.family-tag {{
    background: var(--surface2); padding: 3px 10px; border-radius: 6px;
    font-size: 0.78rem; color: var(--text-muted);
}}

/* Talent Assessment */
.talent-box {{
    margin-top: 24px; padding: 28px 32px; position: relative; overflow: hidden;
    background: linear-gradient(135deg, #eef2ff, #f5f3ff);
    border: 1px solid #c7d2fe;
}}
.talent-box::before {{
    content: ''; position: absolute; top: 0; left: 0; width: 4px; height: 100%;
    background: var(--grad1); border-radius: 4px 0 0 4px;
}}
.talent-type {{
    font-size: 1.3rem; font-weight: 700; margin-bottom: 8px;
    background: linear-gradient(135deg, #818cf8, #c084fc);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
}}
.talent-desc {{ color: var(--text-muted); font-size: 0.95rem; line-height: 1.8; }}

/* Strengths / Weaknesses */
.sw-grid {{ display: grid; grid-template-columns: 3fr 2fr; gap: 24px; margin-top: 24px; }}
.sw-col-title {{ font-size: 1rem; font-weight: 600; margin-bottom: 16px; display: flex; align-items: center; gap: 8px; }}
.strength-card {{
    display: flex; gap: 16px; padding: 16px; border-radius: 12px;
    background: var(--surface); border: 1px solid #e5e7eb;
    margin-bottom: 12px; transition: transform 0.2s, box-shadow 0.2s;
    box-shadow: var(--shadow-sm);
}}
.strength-card:hover {{ transform: translateY(-2px); box-shadow: var(--shadow-lg); }}
.strength-icon {{ width: 40px; height: 40px; color: var(--accent); flex-shrink: 0; }}
.strength-icon svg {{ width: 100%; height: 100%; }}
.strength-body h4 {{ font-size: 0.95rem; margin-bottom: 4px; }}
.strength-body p {{ font-size: 0.85rem; color: var(--text-muted); }}

.weakness-card {{
    padding: 14px 16px; border-radius: 10px; margin-bottom: 10px;
    background: #fef2f2; border: 1px solid #fecaca;
    transition: transform 0.2s;
}}
.weakness-card:hover {{ transform: translateX(4px); }}
.weakness-card h4 {{ font-size: 0.9rem; color: var(--negative); margin-bottom: 4px; }}
.weakness-card p {{ font-size: 0.83rem; color: var(--text-muted); }}

/* Charts */
.charts-row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }}
.chart-card {{ padding: 24px; }}
.chart-card h4 {{ font-size: 0.9rem; color: var(--text-muted); margin-bottom: 16px; font-weight: 500; }}
canvas {{ max-height: 320px; }}

/* Path cards */
.path-card {{
    margin-bottom: 24px; overflow: hidden;
    transition: transform 0.2s, box-shadow 0.3s;
    box-shadow: var(--shadow-md);
}}
.path-card:hover {{ transform: translateY(-3px); box-shadow: var(--shadow-lg); }}
.path-top {{
    display: flex; align-items: center; gap: 16px; padding: 20px 24px;
    border-bottom: 1px solid var(--glass-border); border-top: 3px solid;
}}
.path-rank {{
    font-size: 1.4rem; font-weight: 800; color: var(--text-dim);
    min-width: 40px;
}}
.path-title-block {{ flex: 1; }}
.path-title-block h3 {{ font-size: 1.15rem; font-weight: 700; }}
.path-dir {{ font-size: 0.85rem; color: var(--text-muted); }}
.path-score {{
    font-size: 1.1rem; font-weight: 700; color: white; padding: 6px 16px;
    border-radius: 10px;
}}
/* Scenario branch */
.path-common-label {{
    padding: 4px 24px 0; font-size: 0.75rem; font-weight: 600;
    color: var(--text-dim); letter-spacing: 0.05em; text-transform: uppercase;
}}
.branch-point {{
    display: flex; align-items: center; gap: 10px; padding: 14px 24px;
    margin: 8px 24px; border-radius: 10px;
    background: linear-gradient(135deg, #fef3c7, #fef9c3);
    border: 1px solid #fde68a;
}}
.branch-icon {{ font-size: 1.3rem; }}
.branch-text {{ font-size: 0.88rem; color: #92400e; font-weight: 600; }}
.scenario-bar {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
    gap: 12px; padding: 0 24px 12px;
}}
.scenario-pill {{
    border: 2px solid; border-radius: 12px; padding: 14px; background: var(--surface);
    transition: transform 0.2s, box-shadow 0.2s;
}}
.scenario-pill:hover {{ transform: translateY(-2px); box-shadow: var(--shadow-md); }}
.scenario-pill-head {{ display: flex; align-items: center; gap: 6px; margin-bottom: 6px; }}
.scenario-pill-head strong {{ font-size: 0.88rem; }}
.scenario-icon {{ font-size: 1rem; }}
.scenario-pill-stats {{ display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }}
.scenario-prob {{
    color: white; padding: 2px 10px; border-radius: 6px;
    font-size: 0.85rem; font-weight: 700;
}}
.scenario-income {{ font-weight: 700; font-size: 0.95rem; }}
.scenario-pill-note {{ font-size: 0.78rem; color: var(--text-dim); line-height: 1.5; }}
.scenario-detail {{
    margin: 6px 24px; border-radius: 12px; border: 1px solid #e5e7eb; border-left: 4px solid;
    overflow: hidden; background: var(--surface);
}}
.scenario-summary {{
    padding: 12px 18px; cursor: pointer; font-weight: 600; font-size: 0.9rem;
    display: flex; align-items: center; gap: 8px; list-style: none;
    transition: background 0.2s;
}}
.scenario-summary:hover {{ background: var(--surface2); }}
.scenario-summary::-webkit-details-marker {{ display: none; }}
.scenario-prob-sm {{
    color: white; padding: 1px 8px; border-radius: 4px;
    font-size: 0.75rem; font-weight: 700;
}}
.scenario-final {{
    margin-left: auto; font-size: 0.8rem; font-weight: 500; color: var(--text-muted);
}}
.ev-with-prob {{ position: relative; padding-right: 40px; }}
.ev-prob {{
    position: absolute; right: 3px; top: 50%; transform: translateY(-50%);
    font-size: 0.65rem; color: white; padding: 1px 5px; border-radius: 3px;
    font-weight: 700;
}}
.path-summary {{ display: flex; gap: 12px; padding: 16px 24px; flex-wrap: wrap; }}
.path-pill {{
    flex: 1; min-width: 200px; padding: 10px 14px; border-radius: 10px;
    font-size: 0.85rem; display: flex; align-items: flex-start; gap: 8px;
}}
.pill-icon {{
    width: 20px; height: 20px; border-radius: 50%; display: flex; align-items: center;
    justify-content: center; font-weight: 700; font-size: 0.8rem; flex-shrink: 0;
}}
.upside-pill {{ background: #ecfdf5; color: var(--positive); }}
.upside-pill .pill-icon {{ background: #d1fae5; }}
.risk-pill {{ background: #fef2f2; color: var(--negative); }}
.risk-pill .pill-icon {{ background: #fee2e2; }}

.path-timeline-wrap {{ position: relative; padding: 12px 24px 24px; }}
.path-timeline-line {{
    position: absolute; left: 42px; top: 12px; bottom: 24px; width: 2px; border-radius: 2px;
}}
.period-row {{ display: flex; gap: 16px; margin-bottom: 16px; position: relative; }}
.period-dot {{
    width: 12px; height: 12px; border-radius: 50%; margin-top: 6px; flex-shrink: 0;
    box-shadow: 0 0 10px rgba(99,102,241,0.3);
}}
.period-body {{ flex: 1; }}
.period-head {{ display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 4px; }}
.period-name {{ font-weight: 600; font-size: 0.9rem; color: var(--accent); }}
.period-income {{ font-weight: 700; font-size: 0.95rem; }}
.period-text {{
    font-size: 0.88rem; color: var(--text-muted); margin-bottom: 8px;
    display: -webkit-box;
    -webkit-line-clamp: 3;
    -webkit-box-orient: vertical;
    overflow: hidden;
    cursor: pointer;
    transition: all 0.3s;
}}
.period-text.expanded {{
    -webkit-line-clamp: unset;
}}
.period-tags {{ display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 8px; }}
.ev-tag {{
    background: #eef2ff; border: 1px solid #c7d2fe;
    color: var(--accent); padding: 2px 8px; border-radius: 4px; font-size: 0.75rem;
}}
.block-tag {{
    background: #fef2f2; border: 1px solid #fecaca;
    color: var(--negative); padding: 2px 8px; border-radius: 4px; font-size: 0.75rem;
}}
.period-bars {{ display: flex; gap: 12px; }}
.mini-bar {{ display: flex; align-items: center; gap: 4px; flex: 1; }}
.mini-label {{ font-size: 0.7rem; color: var(--text-dim); min-width: 48px; }}
.mini-track {{ flex: 1; height: 4px; background: var(--surface2); border-radius: 2px; overflow: hidden; }}
.mini-fill {{ height: 100%; border-radius: 2px; transition: width 0.8s ease; }}
.mini-val {{ font-size: 0.7rem; color: var(--text-dim); min-width: 28px; text-align: right; }}

/* Reskilling */
.reskill-row {{
    display: flex; gap: 16px; padding: 20px; margin-bottom: 12px;
    transition: transform 0.2s;
}}
.reskill-row:hover {{ transform: translateX(6px); }}
.reskill-priority {{
    width: 36px; height: 36px; border-radius: 10px; display: flex; align-items: center;
    justify-content: center; font-weight: 700; color: white; font-size: 0.85rem; flex-shrink: 0;
}}
.reskill-content {{ flex: 1; }}
.reskill-content h4 {{ font-size: 1rem; margin-bottom: 4px; }}
.reskill-content p {{ font-size: 0.85rem; color: var(--text-muted); margin-bottom: 8px; }}
.reskill-meta {{ display: flex; align-items: center; gap: 16px; }}
.reskill-time {{ font-size: 0.8rem; color: var(--text-dim); }}
.reskill-paths {{ display: flex; align-items: center; gap: 4px; font-size: 0.8rem; color: var(--text-dim); }}
.path-dot-mini {{
    width: 20px; height: 20px; border-radius: 4px; display: inline-flex;
    align-items: center; justify-content: center; font-size: 0.65rem;
    color: white; font-weight: 700;
}}

/* Comments */
.comments-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }}
.comments-section-title {{ font-size: 1.1rem; font-weight: 600; margin-bottom: 16px; display: flex; align-items: center; gap: 8px; }}
.comment-bubble {{
    display: flex; gap: 12px; padding: 16px; margin-bottom: 12px;
    background: var(--surface); border-radius: 12px; border: 1px solid #e5e7eb;
    transition: transform 0.2s; box-shadow: var(--shadow-sm);
}}
.comment-bubble:hover {{ transform: translateX(4px); }}
.comment-avatar {{
    width: 40px; height: 40px; border-radius: 50%; border: 2px solid;
    display: flex; align-items: center; justify-content: center;
    font-weight: 700; font-size: 1rem; flex-shrink: 0;
    background: var(--surface2);
}}
.comment-meta {{ display: flex; align-items: baseline; gap: 8px; margin-bottom: 2px; flex-wrap: wrap; }}
.comment-meta strong {{ font-size: 0.9rem; }}
.comment-stance {{ font-size: 0.75rem; font-weight: 600; }}
.comment-round-tag {{ font-size: 0.7rem; color: var(--text-dim); background: var(--surface2); padding: 1px 6px; border-radius: 4px; }}
.comment-bio-line {{ font-size: 0.78rem; color: var(--text-dim); margin-bottom: 4px; }}
.comment-text {{ font-size: 0.88rem; color: var(--text-muted); }}
.empty-state {{ color: var(--text-dim); font-style: italic; padding: 20px; }}

/* Per-agent voice cards */
.agent-voice-card {{
    border-radius: 14px; overflow: hidden; margin-bottom: 16px;
    border: 1px solid #e5e7eb; border-left: 4px solid;
    background: var(--surface); box-shadow: var(--shadow-sm);
    transition: transform 0.2s, box-shadow 0.2s;
}}
.agent-voice-card:hover {{ transform: translateY(-2px); box-shadow: var(--shadow-md); }}
.agent-voice-header {{
    display: flex; align-items: center; gap: 12px; padding: 14px 18px;
}}
.agent-voice-avatar {{
    width: 38px; height: 38px; border-radius: 50%; border: 2px solid;
    display: flex; align-items: center; justify-content: center;
    font-weight: 700; font-size: 0.95rem; background: white; flex-shrink: 0;
}}
.agent-voice-info {{ flex: 1; }}
.agent-voice-info strong {{ font-size: 0.9rem; display: block; }}
.agent-voice-bio {{ font-size: 0.78rem; color: var(--text-dim); }}
.agent-voice-role {{ font-size: 0.82rem; color: var(--accent); font-weight: 600; display: block; }}
.agent-voice-persona {{ font-size: 0.82rem; color: var(--text-dim); display: block; line-height: 1.4; }}
.agent-voice-cat {{ font-size: 0.7rem; color: var(--text-dim); background: rgba(99,102,241,0.08); padding: 1px 8px; border-radius: 10px; }}
.agent-profile-detail {{ padding: 8px 16px 4px; font-size: 0.78rem; color: var(--text-muted); line-height: 1.6; border-bottom: 1px solid rgba(0,0,0,0.04); display: flex; flex-wrap: wrap; gap: 4px 12px; }}
.agent-profile-bg {{ display: block; width: 100%; }}
.agent-profile-personality {{ display: block; width: 100%; font-style: italic; color: var(--text-dim); }}
.agent-profile-style {{ display: block; width: 100%; font-size: 0.72rem; color: var(--text-dim); opacity: 0.8; }}
.macro-impacts {{ display: flex; flex-direction: column; gap: 4px; }}
.macro-impact-row {{ display: flex; align-items: center; gap: 8px; font-size: 0.82rem; padding: 4px 0; border-bottom: 1px solid rgba(0,0,0,0.03); }}
.macro-path-label {{ font-weight: 600; min-width: 90px; font-size: 0.78rem; }}
.macro-mag {{ font-size: 0.7rem; color: var(--text-dim); }}
.macro-detail {{ font-size: 0.78rem; color: var(--text-muted); }}
.macro-sources {{ display: flex; gap: 8px; margin-top: 8px; flex-wrap: wrap; }}
.macro-src {{ font-size: 0.72rem; color: var(--text-dim); background: rgba(0,0,0,0.03); padding: 2px 8px; border-radius: 8px; }}
.agent-voice-tags {{ display: flex; gap: 6px; align-items: center; }}
.stance-label {{ font-size: 0.75rem; font-weight: 600; }}
.sent-count {{ font-size: 0.75rem; font-weight: 700; padding: 1px 7px; border-radius: 8px; }}
.pos-count {{ background: #ecfdf5; color: var(--positive); }}
.neg-count {{ background: #fef2f2; color: var(--negative); }}
.agent-voice-quotes {{ padding: 4px 18px 14px; }}
.agent-quote {{
    padding: 10px 14px; border-radius: 10px; margin-bottom: 8px;
    font-size: 0.88rem; position: relative; line-height: 1.6;
}}
.pos-quote {{ background: #ecfdf5; border-left: 3px solid var(--positive); color: #065f46; }}
.neg-quote {{ background: #fef2f2; border-left: 3px solid var(--negative); color: #991b1b; }}
.neut-quote {{ background: #fffbeb; border-left: 3px solid var(--warning); color: #92400e; }}
.q-round {{ font-size: 0.7rem; color: var(--text-dim); margin-left: 8px; }}

/* Core Competencies */
.core-quotes-grid {{ display: flex; flex-direction: column; gap: 12px; }}
.core-quote-item {{
    display: flex; gap: 12px; align-items: flex-start;
    padding: 14px 18px; background: var(--surface2); border-radius: 12px;
    transition: transform 0.2s;
}}
.core-quote-item:hover {{ transform: translateX(4px); }}
.core-quote-dot {{ width: 10px; height: 10px; border-radius: 50%; margin-top: 6px; flex-shrink: 0; }}
.core-quote-body {{ flex: 1; }}
.core-quote-text {{ font-size: 0.88rem; line-height: 1.7; margin: 0 0 4px; color: var(--text); }}
.core-quote-attr {{ font-size: 0.75rem; color: var(--text-dim); }}

/* Path-level voices */
.path-voices-section {{
    margin-top: 20px; padding: 20px 24px;
    background: var(--surface2); border-radius: 14px;
    border: 1px solid var(--glass-border);
}}
.path-voices-title {{
    font-size: 0.95rem; font-weight: 600; margin-bottom: 14px; color: var(--text);
}}
.path-voice-item {{
    display: flex; gap: 10px; align-items: flex-start;
    padding: 10px 0; border-bottom: 1px solid #e5e7eb;
}}
.path-voice-item:last-child {{ border-bottom: none; }}
.path-voice-icon {{
    font-weight: 800; font-size: 1rem; min-width: 20px; text-align: center; margin-top: 2px;
}}
.path-voice-body {{ flex: 1; }}
.path-voice-name {{ font-weight: 600; font-size: 0.82rem; margin-right: 6px; }}
.path-voice-bio {{ font-size: 0.72rem; color: var(--text-dim); }}
.path-voice-text {{ font-size: 0.85rem; line-height: 1.65; margin: 4px 0 0; color: var(--text-muted); }}
.path-voice-round {{ font-size: 0.7rem; color: var(--text-dim); white-space: nowrap; margin-top: 2px; }}

/* Fact-check */
.fc-bar {{ display: flex; height: 8px; border-radius: 4px; overflow: hidden; margin-bottom: 8px; background: #f0f2f8; }}
.fc-bar-seg {{ transition: width 0.6s; }}
.fc-legend {{ display: flex; gap: 16px; font-size: 0.78rem; color: var(--text-muted); margin-bottom: 4px; }}
.fc-dot {{ display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 4px; vertical-align: middle; }}
.fc-row {{
    display: flex; gap: 10px; padding: 12px 14px; margin-bottom: 8px;
    background: var(--surface); border-radius: 10px; border-left: 3px solid;
}}
.fc-icon {{ font-size: 1.1rem; font-weight: 700; min-width: 20px; text-align: center; margin-top: 2px; }}
.fc-body {{ flex: 1; }}
.fc-location {{ font-size: 0.75rem; color: var(--text-dim); margin-bottom: 4px; }}
.fc-values {{ font-size: 0.82rem; display: flex; gap: 16px; margin-bottom: 4px; }}
.fc-note {{ font-size: 0.82rem; color: var(--text-muted); line-height: 1.5; }}
.fc-correction {{ font-size: 0.8rem; color: var(--accent); margin-top: 4px; font-weight: 500; }}
.fc-sources {{ display: flex; gap: 8px; flex-wrap: wrap; margin-top: 6px; }}
.fc-source {{ font-size: 0.72rem; color: var(--text-dim); display: flex; align-items: center; gap: 3px; }}
.fc-rel-dot {{ width: 6px; height: 6px; border-radius: 50%; }}

/* Simulation table */
.sim-table {{
    width: 100%; border-collapse: collapse; font-size: 0.82rem;
}}
.sim-table th {{
    padding: 8px 10px; font-size: 0.75rem; text-transform: uppercase;
    color: var(--text-dim); border-bottom: 2px solid #e5e7eb; text-align: left;
}}
.sim-table td {{
    padding: 7px 10px; border-bottom: 1px solid #f0f2f8;
    max-width: 300px; overflow-wrap: break-word; word-break: break-word;
}}
.sim-table tbody tr:hover {{
    background: var(--accent-glow);
}}
.sim-table tfoot td {{
    padding: 10px;
}}

/* Mirror intro */
.mirror-intro {{
    padding: 20px 28px; margin-bottom: 20px; border-radius: 14px;
    border-left: 4px solid var(--accent);
}}

/* Footer */
.footer {{
    text-align: center; padding: 48px 24px; color: var(--text-dim); font-size: 0.8rem;
    border-top: 1px solid #e5e7eb; margin-top: 64px; background: #f0f2f8;
}}
.footer-brand {{ font-weight: 700; color: var(--accent); font-size: 1rem; margin-bottom: 4px; }}

@media (max-width: 768px) {{
    .profile-grid, .charts-row, .comments-grid, .sw-grid {{ grid-template-columns: 1fr; }}
    .profile-side {{ border-left: none; border-top: 1px solid var(--glass-border); }}
    .hero h1 {{ font-size: 2rem; }}
    .nav-bar {{
        overflow-x: auto;
        justify-content: flex-start;
        -webkit-overflow-scrolling: touch;
        scrollbar-width: none;
        mask-image: linear-gradient(to right, black 85%, transparent 100%);
        -webkit-mask-image: linear-gradient(to right, black 85%, transparent 100%);
    }}
    .nav-bar::-webkit-scrollbar {{ display: none; }}
    .nav-link {{ white-space: nowrap; font-size: 0.75rem; }}
}}

@media (prefers-reduced-motion: reduce) {{
    .hero h1 span {{ animation: none; background: var(--accent); -webkit-background-clip: text; }}
    .anim-fade, .anim-slide {{ animation: none !important; opacity: 1 !important; }}
}}
@media print {{
    .nav-bar {{ display: none; }}
    .anim-fade, .anim-slide {{ opacity: 1 !important; animation: none !important; }}
    .hero {{ padding-top: 40px; }}
    .hero::before {{ display: none; }}
    .glass {{ border: 1px solid #ccc; backdrop-filter: none; }}
    .path-card {{ break-inside: avoid; }}
    #graphSvg {{ height: 400px; }}
    canvas {{ max-height: 250px; }}
    * {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
}}
</style>
</head>
<body>

<!-- Navigation -->
<nav class="nav-bar" aria-label="セクションナビゲーション">
    <span class="nav-logo">MiroFish</span>
    {nav_html}
</nav>

<!-- Hero -->
<div class="hero">
    <div class="hero-label anim-fade">Swarm-in-the-Loop Analysis</div>
    <h1 class="anim-fade" style="animation-delay:0.1s"><span>{html.escape(candidate_name)}</span></h1>
    <p class="hero-sub anim-fade" style="animation-delay:0.2s">
        {f'{len(actions)} Swarm Actions &middot; {max_round} Rounds &middot; ' if len(actions) > 0 else ''}{len(paths)} Parallel Worlds &middot; {len(agents)} Agents
    </p>
</div>

<div class="container">

<!-- Section 0: Profile -->
<div class="section" id="profile">
    <div class="section-header">
        <span class="section-num">01</span>
        <h2 class="section-title">この人はどういう人材か</h2>
    </div>

    <div class="glass profile-grid anim-fade">
        <div class="profile-main">
            <div class="profile-name">{html.escape(candidate_name)}</div>
            <div class="profile-role">{html.escape(state.get("role", ""))} @ {html.escape(state.get("employer", ""))}</div>
            <div class="profile-meta">
                <span class="meta-chip">{html.escape(str(identity.get("age_at_start", "")))}歳 {html.escape(gender_label)}</span>
                <span class="meta-chip">{html.escape(identity.get("education", ""))}</span>
                <span class="meta-chip">{html.escape(identity.get("mbti", ""))}</span>
                <span class="meta-chip">{html.escape(state.get("industry", ""))}</span>
            </div>
            <div class="tag-row">{certs_html}</div>
            <div class="tag-row" style="margin-top: 8px">{skills_html}</div>
            <div class="profile-career">
                <div style="font-size: 0.8rem; color: var(--text-dim); margin-bottom: 4px;">CAREER PATH</div>
                <div class="career-flow">
                    {('<span class="career-arrow">→</span>').join(
                        f'<div class="career-step anim-slide" style="animation-delay:{round(0.2*i, 1)}s"><div class="career-dot" style="background:{career_colors[i%3]}"></div><div class="career-label">{html.escape(p.strip())}</div></div>'
                        for i, p in enumerate(career_parts)
                    )}
                </div>
            </div>
        </div>
        <div class="profile-side">
            <div class="profile-stats">
                <div class="stat-box">
                    <div class="stat-num">{_num(state.get("salary_annual", 0))}<span style="font-size:0.8rem">万</span></div>
                    <div class="stat-label">現在年収</div>
                </div>
                <div class="stat-box">
                    <div class="stat-num">{_num(state.get("years_in_role", 0))}<span style="font-size:0.8rem">年</span></div>
                    <div class="stat-label">業界経験</div>
                </div>
                <div class="stat-box">
                    <div class="stat-num">{_num(state.get("mortgage_remaining", 0))}<span style="font-size:0.8rem">万</span></div>
                    <div class="stat-label">住宅ローン残</div>
                </div>
                <div class="stat-box">
                    <div class="stat-num">{_num(state.get("cash_buffer", 0))}<span style="font-size:0.8rem">万</span></div>
                    <div class="stat-label">貯蓄</div>
                </div>
            </div>
            <div style="margin-top: 16px;">
                <div style="font-size: 0.8rem; color: var(--text-dim); margin-bottom: 6px;">FAMILY</div>
                <div class="tag-row">{family_html}</div>
            </div>
        </div>
    </div>

    <!-- Talent Assessment -->
    <div class="glass talent-box anim-fade" style="margin-top: 24px; border-radius: 16px;">
        <div class="talent-type">{html.escape(analysis["talent_type"])}</div>
        <div class="talent-desc">{html.escape(analysis["talent_desc"])}</div>
    </div>

    <!-- Strengths / Weaknesses -->
    <div class="sw-grid">
        <div>
            <div class="sw-col-title"><span style="color: var(--positive); font-size: 1.2rem;">&#9650;</span> 強み</div>
            {strengths_html}
        </div>
        <div>
            <div class="sw-col-title"><span style="color: var(--negative); font-size: 1.2rem;">&#9660;</span> 注意点・弱み</div>
            {weaknesses_html}
        </div>
    </div>

    <!-- Self vs God's Eye -->
    {self_vs_gods_html}
</div>

<!-- Section: Core Competencies -->
<div class="section" id="core">
    <div class="section-header">
        <span class="section-num">02</span>
        <h2 class="section-title">根源的スキル — エージェントが見た本質</h2>
    </div>
    <p class="section-subtitle">30人のSwarmエージェントの{len(actions)}件の会話から、候補者の根源的な強みを抽出</p>
    {core_competencies_html}
</div>

<!-- Section: God's Eye View -->
<div class="section" id="overview">
    <div class="section-header">
        <span class="section-num">03</span>
        <h2 class="section-title">神の視点 — 5つのパラレルワールド</h2>
    </div>
    <p class="section-subtitle">同じ人物が異なる選択をした場合の10年後を俯瞰する</p>

    <div class="charts-row">
        <div class="glass chart-card anim-fade">
            <h4>最終状態レーダー</h4>
            <canvas id="radarChart" role="img" aria-label="5パスの最終状態比較レーダーチャート"></canvas>
        </div>
        <div class="glass chart-card anim-fade" style="animation-delay:0.1s">
            <h4>満足度推移</h4>
            <canvas id="satChart" role="img" aria-label="満足度推移グラフ"></canvas>
        </div>
    </div>

    {gods_eye_html}
    {fact_check_html}
</div>

<!-- Section: Salary -->
<div class="section" id="salary">
    <div class="section-header">
        <span class="section-num">04</span>
        <h2 class="section-title">年収推移 — 10年シミュレーション</h2>
    </div>
    <div class="glass chart-card anim-fade">
        <canvas id="incomeChart" style="max-height: 380px;" role="img" aria-label="年収推移グラフ"></canvas>
    </div>
</div>

<!-- Section: Path Cards -->
<div class="section" id="paths">
    <div class="section-header">
        <span class="section-num">05</span>
        <h2 class="section-title">各パスのキャリアイメージ</h2>
    </div>
    <p class="section-subtitle">各パラレルワールドの10年間を詳細に追う — パスごとにエージェントの声も複眼的に掲載</p>
    {path_cards_html}
</div>

<!-- Section: Reskilling -->
<div class="section" id="reskill">
    <div class="section-header">
        <span class="section-num">06</span>
        <h2 class="section-title">リスキリングするなら</h2>
    </div>
    <p class="section-subtitle">どのパスを選んでも活きるスキルを優先度順に提案</p>
    {reskill_html}
</div>

<!-- Section: Mirror Agents -->
<div class="section" id="mirror">
    <div class="section-header">
        <span class="section-num">07</span>
        <h2 class="section-title">パラレルワールドの自分</h2>
    </div>
    <p class="section-subtitle">5つの世界線を生きた「もう一人の自分」が語る、それぞれの選択のリアル</p>
    <div class="mirror-intro glass anim-fade">
        <p style="font-size: 0.88rem; color: var(--text-muted); line-height: 1.7; margin: 0;">
            以下は候補者のコピーエージェント — 各パスを実際に歩んだ「自分自身」の声です。
            外部の評価者とは異なり、選択した道の<strong>実感</strong>と<strong>葛藤</strong>を語ります。
        </p>
    </div>
    {mirror_cards_html}
</div>

<!-- Section: Agent Comments -->
<div class="section" id="voices">
    <div class="section-header">
        <span class="section-num">08</span>
        <h2 class="section-title">外部エージェントの声</h2>
    </div>
    <p class="section-subtitle">{len(agents) - len([a for a in agents.values() if a.get("role") == "copy_agent" or a.get("is_copy_agent")])}人の外部エージェントが{max_round}ラウンドにわたり語った評価</p>
    {agent_comments_html}
</div>

{macro_trends_section}

{zep_graph_section}

{conclusion_section}

</div>

<!-- Footer -->
<div class="footer">
    <div class="footer-brand">MiroFish</div>
    Swarm-in-the-Loop Multi-Perspective Career Analysis<br>
    {len(actions)} actions &middot; {max_round} rounds &middot; {len(agents)} agents &middot; {len(paths)} parallel worlds
</div>

<script>
// Intersection Observer for scroll animations
const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
if (prefersReduced) {{
    document.querySelectorAll('.anim-fade, .anim-slide').forEach(el => {{
        el.style.opacity = '1';
        el.style.transform = 'none';
        el.style.animation = 'none';
    }});
}} else {{
    const observer = new IntersectionObserver((entries) => {{
        entries.forEach(entry => {{
            if (entry.isIntersecting) {{
                entry.target.style.animationPlayState = 'running';
                observer.unobserve(entry.target);
            }}
        }});
    }}, {{ threshold: 0.1 }});
    document.querySelectorAll('.anim-fade, .anim-slide').forEach(el => {{
        el.style.animationPlayState = 'paused';
        observer.observe(el);
    }});
}}

// Chart defaults
Chart.defaults.color = '#5a6078';
Chart.defaults.borderColor = '#e5e7eb';
Chart.defaults.font.family = "'Inter', 'Noto Sans JP', sans-serif";

// Radar
new Chart(document.getElementById('radarChart'), {{
    type: 'radar',
    data: {{ labels: {safe_json_embed(radar_labels)}, datasets: {safe_json_embed(radar_datasets)} }},
    options: {{
        responsive: true,
        scales: {{ r: {{ beginAtZero: true, max: 100, ticks: {{ display: false }}, grid: {{ color: '#e5e7eb88' }}, pointLabels: {{ color: '#1a1d2e', font: {{ size: 12 }} }}, angleLines: {{ color: '#e5e7eb66' }} }} }},
        plugins: {{ legend: {{ position: 'bottom', labels: {{ boxWidth: 12, padding: 12, usePointStyle: true }} }} }},
        animation: {{ duration: 1500, easing: 'easeOutQuart' }}
    }}
}});

// Satisfaction
new Chart(document.getElementById('satChart'), {{
    type: 'line',
    data: {{ labels: {safe_json_embed(period_labels)}, datasets: {safe_json_embed(sat_datasets)} }},
    options: {{
        responsive: true,
        scales: {{
            y: {{ min: 0, max: 100, title: {{ display: true, text: '満足度 (%)' }}, grid: {{ color: '#e5e7eb44' }} }},
            x: {{ grid: {{ color: '#e5e7eb44' }} }}
        }},
        plugins: {{ legend: {{
            position: 'bottom',
            labels: {{
                boxWidth: 12, padding: 12, usePointStyle: true,
                generateLabels: function(chart) {{
                    return chart.data.datasets.map(function(ds, i) {{
                        return {{
                            text: ds.label.length > 12 ? ds.label.substring(0, 12) + '...' : ds.label,
                            fillStyle: ds.borderColor,
                            strokeStyle: ds.borderColor,
                            lineWidth: 2,
                            datasetIndex: i,
                            hidden: !chart.isDatasetVisible(i)
                        }};
                    }});
                }}
            }}
        }} }},
        animation: {{ duration: 1500 }}
    }}
}});

// Income
new Chart(document.getElementById('incomeChart'), {{
    type: 'line',
    data: {{ labels: {safe_json_embed(period_labels)}, datasets: {safe_json_embed(income_datasets)} }},
    options: {{
        responsive: true,
        scales: {{
            y: {{ title: {{ display: true, text: '年収（万円）' }}, grid: {{ color: '#e5e7eb44' }} }},
            x: {{ grid: {{ color: '#e5e7eb44' }} }}
        }},
        plugins: {{
            legend: {{
                position: 'bottom',
                labels: {{
                    boxWidth: 12, padding: 12, usePointStyle: true,
                    generateLabels: function(chart) {{
                        return chart.data.datasets.map(function(ds, i) {{
                            return {{
                                text: ds.label.length > 12 ? ds.label.substring(0, 12) + '...' : ds.label,
                                fillStyle: ds.borderColor,
                                strokeStyle: ds.borderColor,
                                lineWidth: 2,
                                datasetIndex: i,
                                hidden: !chart.isDatasetVisible(i)
                            }};
                        }});
                    }}
                }}
            }},
            tooltip: {{ callbacks: {{ label: function(ctx) {{ return ctx.dataset.label + ': ' + ctx.parsed.y + '万円'; }} }} }}
        }},
        interaction: {{ mode: 'index', intersect: false }},
        animation: {{ duration: 2000, easing: 'easeOutQuart' }}
    }}
}});

// Smooth nav scroll highlight
const navLinks = document.querySelectorAll('.nav-link');
const sections = document.querySelectorAll('.section[id]');
window.addEventListener('scroll', () => {{
    let current = '';
    sections.forEach(s => {{ if (window.scrollY >= s.offsetTop - 100) current = s.id; }});
    navLinks.forEach(link => {{
        link.style.color = link.getAttribute('href') === '#' + current ? '#818cf8' : '';
        link.style.background = link.getAttribute('href') === '#' + current ? 'rgba(99,102,241,0.1)' : '';
    }});
}});

// Knowledge Graph — D3.js SVG (MiroFish GraphPanel.vue style)
(function() {{
    const svgEl = document.getElementById('graphSvg');
    if (!svgEl || typeof d3 === 'undefined') return;

    const rawNodes = {graph_nodes_json};
    const rawEdges = {graph_edges_json};

    const W = svgEl.clientWidth || 1000, H = svgEl.clientHeight || 650;
    const svg = d3.select(svgEl).attr('viewBox', `0 0 ${{W}} ${{H}}`);
    svg.selectAll('*').remove();

    const groupColors = {{
        person: '#6366f1', company: '#FF6B35', skill: '#1A936F',
        path: '#C5283D', scenario_best: '#27ae60', scenario_likely: '#3498db', scenario_base: '#f39c12',
        agent_vc: '#9b59b6', agent_tech: '#3498db', agent_hr: '#e67e22',
        agent_biz: '#2c3e50', agent_private: '#e74c3c', agent_mirror: '#1abc9c'
    }};
    const groupRadius = {{
        person: 20, company: 12, skill: 10, path: 16, scenario_best: 8, scenario_likely: 8, scenario_base: 8,
        agent_vc: 9, agent_tech: 9, agent_hr: 9, agent_biz: 9, agent_private: 9, agent_mirror: 9
    }};
    const getColor = g => groupColors[g] || '#999';
    const getRadius = g => groupRadius[g] || 10;

    // Prep D3 data
    const nodes = rawNodes.map(n => ({{ ...n }}));
    const edges = rawEdges.map(e => ({{ source: e.from, target: e.to, label: e.label }}));

    // Force simulation (GraphPanel.vue style, tuned for 50+ nodes)
    const simulation = d3.forceSimulation(nodes)
        .force('link', d3.forceLink(edges).id(d => d.id).distance(d => {{
            // Agents closer to their targets
            const isAgent = d.source.group?.startsWith('agent_') || d.target.group?.startsWith('agent_');
            return isAgent ? 100 : 150;
        }}))
        .force('charge', d3.forceManyBody().strength(-300))
        .force('center', d3.forceCenter(W / 2, H / 2))
        .force('collide', d3.forceCollide(35))
        .force('x', d3.forceX(W / 2).strength(0.03))
        .force('y', d3.forceY(H / 2).strength(0.03));

    const g = svg.append('g');

    // Zoom (same as GraphPanel.vue)
    svg.call(d3.zoom().scaleExtent([0.2, 4]).on('zoom', e => g.attr('transform', e.transform)));

    // Defs for arrow markers
    svg.append('defs').selectAll('marker')
        .data(['arrow']).enter().append('marker')
        .attr('id', 'arrow').attr('viewBox', '0 -5 10 10')
        .attr('refX', 20).attr('refY', 0)
        .attr('markerWidth', 6).attr('markerHeight', 6).attr('orient', 'auto')
        .append('path').attr('d', 'M0,-5L10,0L0,5').attr('fill', '#C0C0C0');

    // Links
    const link = g.append('g').selectAll('line')
        .data(edges).enter().append('line')
        .attr('stroke', '#C0C0C0').attr('stroke-width', 1.5)
        .attr('marker-end', 'url(#arrow)');

    // Edge labels
    const edgeLabels = g.append('g').selectAll('text')
        .data(edges).enter().append('text')
        .text(d => d.label || '')
        .attr('font-size', '9px').attr('fill', '#999')
        .attr('text-anchor', 'middle').attr('dominant-baseline', 'middle')
        .style('font-family', "'Inter', system-ui, sans-serif")
        .style('pointer-events', 'none');

    // Node groups
    const nodeGroup = g.append('g').selectAll('g')
        .data(nodes).enter().append('g')
        .style('cursor', 'pointer')
        .call(d3.drag()
            .on('start', (e, d) => {{ if (!e.active) simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; }})
            .on('drag', (e, d) => {{ d.fx = e.x; d.fy = e.y; }})
            .on('end', (e, d) => {{ if (!e.active) simulation.alphaTarget(0); d.fx = null; d.fy = null; }})
        )
        .on('click', (e, d) => {{
            e.stopPropagation();
            // Highlight connected edges
            link.attr('stroke', l => (l.source.id === d.id || l.target.id === d.id) ? '#E91E63' : '#C0C0C0')
                .attr('stroke-width', l => (l.source.id === d.id || l.target.id === d.id) ? 2.5 : 1.5);
            nodeGroup.selectAll('circle').attr('stroke', '#fff').attr('stroke-width', 2);
            d3.select(e.currentTarget).select('circle').attr('stroke', '#E91E63').attr('stroke-width', 3.5);
            // Detail panel
            const detail = document.getElementById('graphDetail');
            detail.style.display = 'block';
            function esc(s) {{ if (!s) return ''; const el = document.createElement('div'); el.textContent = s; return el.innerHTML; }}
            const groupLabels = {{
                person: '候補者', company: '経歴', skill: 'スキル', path: 'キャリアパス',
                scenario_best: 'Best', scenario_likely: 'Likely', scenario_base: 'Base',
                agent_vc: 'VC/投資家', agent_tech: 'テック業界', agent_hr: 'HR/キャリア',
                agent_biz: '経営・戦略', agent_private: 'プライベート', agent_mirror: 'ミラー'
            }};
            const isAgent = d.group.startsWith('agent_');
            let detailBody = '';
            if (isAgent) {{
                detailBody = `
                    ${{d.detail ? `<div style="font-weight:600;color:var(--accent);margin-bottom:4px">${{esc(d.detail)}}</div>` : ''}}
                    ${{d.background ? `<div style="margin-bottom:4px">${{esc(d.background)}}</div>` : ''}}
                    ${{d.personality ? `<div style="font-style:italic;color:#7c8298">${{esc(d.personality)}}</div>` : ''}}
                    ${{d.speaking_style ? `<div style="font-size:0.72rem;color:#9098b0;margin-top:4px">口調: ${{esc(d.speaking_style)}}</div>` : ''}}
                `;
            }} else {{
                detailBody = `${{d.group === 'person' ? 'シミュレーション対象の候補者' : d.group === 'company' ? '経歴に含まれる企業/組織' : d.group === 'skill' ? '保有スキル/専門領域' : d.group === 'path' ? 'シミュレートされたキャリアパス' : d.group.startsWith('scenario') ? 'シナリオ分岐（確率付き）' : ''}}`;
            }}
            detail.innerHTML = `<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
                <strong>${{esc(d.label)}}</strong>
                <span style="font-size:0.7rem;padding:2px 8px;border-radius:8px;background:${{getColor(d.group)}};color:#fff">${{groupLabels[d.group] || esc(d.group)}}</span>
            </div>
            <div style="font-size:0.78rem;color:#5a6078;line-height:1.6">${{detailBody}}</div>`;
        }});

    // Node circles
    nodeGroup.append('circle')
        .attr('r', d => getRadius(d.group))
        .attr('fill', d => getColor(d.group))
        .attr('stroke', '#fff').attr('stroke-width', 2);

    // Node labels
    nodeGroup.append('text')
        .text(d => d.label.length > 12 ? d.label.substring(0, 12) + '…' : d.label)
        .attr('font-size', d => d.group === 'person' ? '13px' : '10px')
        .attr('font-weight', d => d.group === 'person' ? '600' : '500')
        .attr('fill', '#333').attr('dx', d => getRadius(d.group) + 4).attr('dy', 4)
        .style('pointer-events', 'none')
        .style('font-family', "'Inter', 'Noto Sans JP', system-ui, sans-serif");

    // Click empty space to dismiss
    svg.on('click', () => {{ document.getElementById('graphDetail').style.display = 'none'; }});

    // Tick
    simulation.on('tick', () => {{
        link.attr('x1', d => d.source.x).attr('y1', d => d.source.y)
            .attr('x2', d => d.target.x).attr('y2', d => d.target.y);
        edgeLabels.attr('x', d => (d.source.x + d.target.x) / 2).attr('y', d => (d.source.y + d.target.y) / 2);
        nodeGroup.attr('transform', d => `translate(${{d.x}},${{d.y}})`);
    }});

    // Legend
    const legendData = [['候補者', 'person'], ['経歴', 'company'], ['スキル', 'skill'], ['パス', 'path'],
        ['VC', 'agent_vc'], ['テック', 'agent_tech'], ['HR', 'agent_hr'], ['経営', 'agent_biz'], ['私的', 'agent_private'], ['ミラー', 'agent_mirror']];
    const legendEl = document.getElementById('graphLegend');
    legendData.forEach(([label, group]) => {{
        legendEl.innerHTML += `<span style="display:flex;align-items:center;gap:4px"><span style="width:10px;height:10px;border-radius:50%;background:${{getColor(group)}}"></span>${{label}}</span>`;
    }});
}})();

// Hide empty sections (02: core-quotes, 07: parallel-world, 08: agent-voices)
(function() {{
    const checks = [
        {{ sectionId: 'core', selectors: ['.core-quotes-grid'] }},
        {{ sectionId: 'mirror', selectors: ['.comment-bubble'] }},
        {{ sectionId: 'voices', selectors: ['.agent-voice-card'] }},
        {{ sectionId: 'macro', selectors: ['.macro-impact-row'] }}
    ];
    checks.forEach(function(c) {{
        const section = document.getElementById(c.sectionId);
        if (!section) return;
        let hasContent = false;
        c.selectors.forEach(function(sel) {{
            const els = section.querySelectorAll(sel);
            els.forEach(function(el) {{
                if (el.textContent && el.textContent.trim().length >= 20) {{
                    hasContent = true;
                }}
            }});
        }});
        if (!hasContent) {{
            section.style.display = 'none';
            const navLinks = document.querySelectorAll('.nav-bar a[href="#' + c.sectionId + '"]');
            navLinks.forEach(function(link) {{ link.style.display = 'none'; }});
        }}
    }});
}})();

// Period text collapse/expand toggle
document.querySelectorAll('.period-text').forEach(el => {{
    el.addEventListener('click', () => el.classList.toggle('expanded'));
}});
</script>

<button id="scrollTop" aria-label="ページ先頭に戻る" onclick="window.scrollTo({{top:0,behavior:'smooth'}})"
  style="position:fixed; bottom:24px; right:24px; width:48px; height:48px;
  border-radius:50%; background:var(--accent); color:white; border:none;
  font-size:1.2rem; cursor:pointer; z-index:99; display:none;
  box-shadow:var(--shadow-md);">&#8593;</button>
<script>
window.addEventListener('scroll', () => {{
  document.getElementById('scrollTop').style.display =
    window.scrollY > 600 ? 'block' : 'none';
}});
</script>
</body>
</html>'''


def main():
    parser = argparse.ArgumentParser(description="MiroFish レポートHTML生成")
    parser.add_argument("--session-dir", required=True, help="セッションディレクトリ")
    parser.add_argument("--output", default="report.html", help="出力HTMLファイル")
    args = parser.parse_args()

    if not os.path.isdir(args.session_dir):
        print(f"Error: {args.session_dir} not found", file=sys.stderr)
        sys.exit(1)

    html_content = build_html(args.session_dir)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"Report generated: {args.output}")


if __name__ == "__main__":
    main()
