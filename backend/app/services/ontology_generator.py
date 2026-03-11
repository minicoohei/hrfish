"""
オントロジー生成サービス
インターフェース1：テキスト内容を分析し、キャリアシミュレーションに適したエンティティと関係タイプを定義
"""

import json
from typing import Dict, Any, List, Optional
from ..utils.llm_client import LLMClient


# オントロジー生成のシステムプロンプト
ONTOLOGY_SYSTEM_PROMPT = """あなたはプロフェッショナルな知識グラフのオントロジー設計専門家です。与えられたテキスト内容とシミュレーション要件を分析し、**HRキャリアシミュレーション**に適したエンティティタイプと関係タイプを設計してください。

**重要：有効なJSON形式のデータのみを出力してください。それ以外の内容は出力しないでください。**

## コアタスクの背景

私たちは**HRキャリアシミュレーションシステム**を構築しています。このシステムでは：
- 各エンティティは、求職者のキャリアに関与するステークホルダーです
- エンティティ間で評価、助言、意思決定を行います
- 求職者の履歴書・職務経歴書を基に、各ステークホルダーがどのように反応するかをシミュレーションします

したがって、**エンティティは現実に存在し、キャリアに関する評価・助言・意思決定を行える主体**でなければなりません：

**可能なもの（以下から必ず選定すること）**：

【転職エージェント側】
- キャリアアドバイザー（転職エージェントの求職者担当。求職者のキャリア相談・求人提案・面接対策を行う）
- リクルーティングアドバイザー（転職エージェントの企業担当。企業の採用ニーズをヒアリングし候補者を推薦する）
- ヘッドハンター（エグゼクティブサーチ専門。ハイクラス・管理職の転職スカウト）

【企業側 — 採用プロセスの各段階に関わる人物】
- 採用担当者（企業の人事部で書類選考・面接調整を行う。一次スクリーニングの実務者）
- 人事マネージャー（人事部の管理職。採用方針の決定、オファー条件の策定、CHRO含む）
- 現場マネージャー（配属先の上司候補。技術力・チームフィット・即戦力度を評価）
- 事業部長・VP（事業責任者。部門戦略に合う人材かを判断。採用の最終意思決定者の場合も）
- CEO・社長（経営トップ。会社のビジョン・カルチャーとの整合性を最終判断）
- CTO・技術役員（技術系採用の場合の最終面接官。技術力・アーキテクチャ思考を評価）
- 取締役・ボードメンバー（経営幹部採用の場合に関与。ガバナンス・経営適性を判断）

【同業・同職種・類似キャリア】
- 同職種の現役社員（同じ職種で働いている人間。市場価値の相場感、スキルの過不足を客観評価）
- 類似キャリアの先輩（同じ職種・業界で5-10年先を行く成功者。キャリアパスの実例、転職判断の教訓）
- 類似キャリアの転職成功者（同じようなバックグラウンドから転職に成功した人間。何が決め手だったか、どう準備したか）
- 類似キャリアの転職失敗者（同じようなバックグラウンドから転職に失敗した人間。何が足りなかったか、ミスマッチの原因）
- 元同僚・元上司（過去の職場関係者。リファレンスチェック、実績の裏付け）

【外部専門家・コンサルタント】
- 人材コンサルタント（組織人事コンサル、タレントマネジメント、報酬制度の専門家）
- キャリアコーチ（キャリアカウンセラー、ライフコーチ、メンター）

【同職種の権威・Tier1層】
- 同職種の業界権威（トップランナー、著名実務家、カンファレンス登壇者、書籍著者。業界最高水準との比較評価）
- 同職種のTier1企業社員（GAFA・外資コンサル等のトップ企業で同職種に就く人物。ハイレベルな採用基準からの評価）

【学術・ジャーナリズム・社会科学】
- 雇用ジャーナリスト（雇用問題・労働市場・転職トレンドを取材する記者。マクロな雇用動向からキャリア選択を分析）
- 社会学者（労働社会学、組織社会学の専門家。雇用構造の変化、バイアス、社会的流動性の観点から評価）
- 労働経済学者（賃金格差、人的資本理論、労働市場の需給分析。候補者の市場価値を経済学的に分析）
- 人事系大学教授（HRM、組織行動学、キャリア論の研究者。理論フレームワークからキャリア戦略を評価）
- 業界アナリスト（業界動向・市場規模・成長性・給与水準の専門家）

**不可なもの**：
- 抽象概念（市場価値、キャリアパス、年収トレンド等）
- テーマ・トピック（DX推進、働き方改革等）
- 態度・観点（賛成派、反対派等）

## 出力形式

JSON形式で出力してください。以下の構造を含みます：

```json
{
    "entity_types": [
        {
            "name": "エンティティタイプ名（英語、PascalCase）",
            "description": "簡潔な説明（英語、100文字以内）",
            "attributes": [
                {
                    "name": "属性名（英語、snake_case）",
                    "type": "text",
                    "description": "属性の説明"
                }
            ],
            "examples": ["例1", "例2"]
        }
    ],
    "edge_types": [
        {
            "name": "関係タイプ名（英語、UPPER_SNAKE_CASE）",
            "description": "簡潔な説明（英語、100文字以内）",
            "source_targets": [
                {"source": "ソースエンティティタイプ", "target": "ターゲットエンティティタイプ"}
            ],
            "attributes": []
        }
    ],
    "analysis_summary": "テキスト内容の簡潔な分析説明（日本語）"
}
```

## 設計ガイドライン（極めて重要！）

### 1. エンティティタイプ設計 - 厳格に遵守すること

**数量要件：ちょうど10個のエンティティタイプ**

**階層構造要件（具体タイプとフォールバックタイプの両方を含むこと）**：

10個のエンティティタイプは以下の階層を含む必要があります：

A. **フォールバックタイプ（必須、リストの最後2つ）**：
   - `Person`: すべての自然人のフォールバック。他の具体的な人物タイプに該当しない場合に使用。
   - `Organization`: すべての組織のフォールバック。他の具体的な組織タイプに該当しない場合に使用。

B. **具体タイプ（8個、テキスト内容に基づいて設計）**：
   - テキストに登場する主要な関係者に対し、より具体的なタイプを設計
   - 例：キャリア関連では `Recruiter`, `HRManager`, `TeamMember`, `Executive`
   - 例：評価関連では `CareerCoach`, `IndustryAnalyst`, `FormerColleague`

**フォールバックタイプが必要な理由**：
- テキストにはさまざまな人物が登場する可能性がある
- 専用タイプに該当しない場合は `Person` に分類
- 同様に、小規模な組織は `Organization` に分類

**具体タイプの設計原則**：
- テキストから高頻度または重要な役割タイプを特定
- 各具体タイプは明確な境界を持ち、重複を避ける
- descriptionにフォールバックタイプとの違いを明確に記述

### 2. 関係タイプ設計

- 数量：6-10個
- 関係はキャリア評価・採用プロセスにおける実際の関係を反映
- 関係の source_targets が定義したエンティティタイプを網羅すること

### 3. 属性設計

- 各エンティティタイプに1-3個の主要属性
- **注意**：属性名に `name`、`uuid`、`group_id`、`created_at`、`summary` は使用不可（システム予約語）
- 推奨：`full_name`, `title`, `role`, `position`, `specialty`, `description` 等

## エンティティタイプ参考

**個人（具体）— 以下から8つを選定すること**：

【転職エージェント側】
- CareerAdvisor: キャリアアドバイザー（求職者担当。キャリア相談・求人提案・面接対策）
- RecruitingAdvisor: リクルーティングアドバイザー（企業担当。企業の採用ニーズに候補者を推薦）
- Headhunter: ヘッドハンター（エグゼクティブサーチ、ハイクラス転職スカウト）

【企業側】
- CorporateRecruiter: 採用担当者（人事部の実務者。書類選考・面接調整・一次スクリーニング）
- HRManager: 人事マネージャー（採用方針の決定、オファー条件策定、CHRO含む）
- HiringManager: 現場マネージャー（配属先の上司候補。技術力・チームフィット評価）
- DivisionHead: 事業部長・VP（部門戦略に合う人材か判断。採用の最終意思決定者）
- CEO: CEO・社長（経営トップ。ビジョン・カルチャーとの整合性を最終判断）
- CTO: CTO・技術役員（技術系採用の最終面接官。技術力・アーキテクチャ思考評価）
- BoardMember: 取締役（経営幹部採用時。ガバナンス・経営適性を判断）

【同業・同職種・類似キャリア】
- PeerProfessional: 同職種の現役社員（市場価値の相場感、スキル過不足の客観評価）
- CareerSuccessor: 類似キャリアの先輩・転職成功者（キャリアパスの実例、成功の決め手）
- CareerCautionary: 類似キャリアの転職失敗者（ミスマッチの原因、失敗の教訓）
- FormerColleague: 元同僚・元上司（リファレンスチェック、実績の裏付け）

【外部専門家・コンサルタント】
- TalentConsultant: 人材コンサルタント（組織人事コンサル、報酬制度専門）
- CareerCoach: キャリアコーチ（キャリアカウンセラー、メンター）

【同職種の権威・Tier1層】
- IndustryAuthority: 同職種の業界権威（トップランナー、著名実務家、登壇者、書籍著者）
- Tier1Professional: Tier1企業の同職種社員（GAFA・外資コンサル等のハイレベル採用基準での評価）

【学術・ジャーナリズム・社会科学】
- EmploymentJournalist: 雇用ジャーナリスト（雇用問題・労働市場・転職トレンドの取材記者）
- Sociologist: 社会学者（労働社会学、雇用構造変化、バイアス、社会的流動性）
- LaborEconomist: 労働経済学者（賃金格差、人的資本理論、労働市場の需給分析）
- HRProfessor: 人事系大学教授（HRM、組織行動学、キャリア論の研究者）
- IndustryAnalyst: 業界アナリスト（業界動向、市場規模、給与水準）

**個人（フォールバック）**：
- Person: 上記の具体タイプに該当しない自然人

**組織（具体）**：
- Company: 企業
- RecruitmentAgency: 人材紹介会社・ヘッドハンティングファーム
- IndustryAssociation: 業界団体・HR系学会
- TrainingInstitute: 研修・教育機関・ビジネススクール

**組織（フォールバック）**：
- Organization: 上記の具体タイプに該当しない組織

## 関係タイプ参考

- SCREENS: 書類選考・一次スクリーニング（採用担当→候補者）
- INTERVIEWS: 面接・評価（現場マネージャー/役員→候補者）
- RECOMMENDS: 候補者推薦（エージェント→企業）
- ADVISES: キャリア助言（キャリアアドバイザー/コーチ→候補者）
- EVALUATES: スキル・適性評価（同職種/専門家→候補者）
- REFERS: リファレンス提供（元同僚→採用企業）
- MANAGES: マネジメント関係（マネージャー→チーム）
- WORKS_FOR: 所属先（個人→組織）
- COMPETES_WITH: 人材獲得競合（企業→企業）
- RESEARCHES: 調査・分析（アナリスト/教授→業界/人材市場）
"""


class OntologyGenerator:
    """
    オントロジー生成器
    テキスト内容を分析し、エンティティと関係タイプの定義を生成
    """

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm_client = llm_client or LLMClient()

    def generate(
        self,
        document_texts: List[str],
        simulation_requirement: str,
        additional_context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        オントロジー定義を生成

        Args:
            document_texts: ドキュメントテキストリスト
            simulation_requirement: シミュレーション要件の説明
            additional_context: 追加コンテキスト

        Returns:
            オントロジー定義（entity_types, edge_types等）
        """
        # ユーザーメッセージを構築
        user_message = self._build_user_message(
            document_texts,
            simulation_requirement,
            additional_context
        )

        messages = [
            {"role": "system", "content": ONTOLOGY_SYSTEM_PROMPT},
            {"role": "user", "content": user_message}
        ]

        # LLM呼び出し
        result = self.llm_client.chat_json(
            messages=messages,
            temperature=0.3,
            max_tokens=16384
        )

        # 検証と後処理
        result = self._validate_and_process(result)

        return result

    # LLMに渡すテキストの最大長（5万字）
    MAX_TEXT_LENGTH_FOR_LLM = 50000

    def _build_user_message(
        self,
        document_texts: List[str],
        simulation_requirement: str,
        additional_context: Optional[str]
    ) -> str:
        """ユーザーメッセージを構築"""

        # テキストを結合
        combined_text = "\n\n---\n\n".join(document_texts)
        original_length = len(combined_text)

        # テキストが5万字を超える場合、截断（LLMに渡す内容のみ影響、グラフ構築には影響なし）
        if len(combined_text) > self.MAX_TEXT_LENGTH_FOR_LLM:
            combined_text = combined_text[:self.MAX_TEXT_LENGTH_FOR_LLM]
            combined_text += f"\n\n...(原文{original_length}字のうち、先頭{self.MAX_TEXT_LENGTH_FOR_LLM}字をオントロジー分析に使用)..."

        message = f"""## シミュレーション要件

{simulation_requirement}

## ドキュメント内容

{combined_text}
"""

        if additional_context:
            message += f"""
## 追加説明

{additional_context}
"""

        message += """
上記の内容に基づき、HRキャリアシミュレーションに適したエンティティタイプと関係タイプを設計してください。

**必須ルール**：
1. ちょうど10個のエンティティタイプを出力すること
2. 最後の2つはフォールバックタイプ：Person（個人フォールバック）と Organization（組織フォールバック）
3. 最初の8個はテキスト内容に基づいた具体タイプ
4. すべてのエンティティタイプは現実にキャリア評価・助言を行える主体であること。抽象概念は不可
5. 属性名に name、uuid、group_id 等の予約語は使用不可。full_name、org_name 等を使用
"""

        return message

    def _validate_and_process(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """結果の検証と後処理"""

        # 必要なフィールドの存在を確認
        if "entity_types" not in result:
            result["entity_types"] = []
        if "edge_types" not in result:
            result["edge_types"] = []
        if "analysis_summary" not in result:
            result["analysis_summary"] = ""

        # エンティティタイプの検証
        for entity in result["entity_types"]:
            if "attributes" not in entity:
                entity["attributes"] = []
            if "examples" not in entity:
                entity["examples"] = []
            # descriptionが100文字以内であることを確認
            if len(entity.get("description", "")) > 100:
                entity["description"] = entity["description"][:97] + "..."

        # 関係タイプの検証
        for edge in result["edge_types"]:
            if "source_targets" not in edge:
                edge["source_targets"] = []
            if "attributes" not in edge:
                edge["attributes"] = []
            if len(edge.get("description", "")) > 100:
                edge["description"] = edge["description"][:97] + "..."

        # Zep API制限：最大10個のカスタムエンティティタイプ、最大10個のカスタムエッジタイプ
        MAX_ENTITY_TYPES = 10
        MAX_EDGE_TYPES = 10

        # フォールバックタイプ定義
        person_fallback = {
            "name": "Person",
            "description": "Any individual person not fitting other specific person types.",
            "attributes": [
                {"name": "full_name", "type": "text", "description": "Full name of the person"},
                {"name": "role", "type": "text", "description": "Role or occupation"}
            ],
            "examples": ["ordinary citizen", "anonymous netizen"]
        }

        organization_fallback = {
            "name": "Organization",
            "description": "Any organization not fitting other specific organization types.",
            "attributes": [
                {"name": "org_name", "type": "text", "description": "Name of the organization"},
                {"name": "org_type", "type": "text", "description": "Type of organization"}
            ],
            "examples": ["small business", "community group"]
        }

        # フォールバックタイプの有無を確認
        entity_names = {e["name"] for e in result["entity_types"]}
        has_person = "Person" in entity_names
        has_organization = "Organization" in entity_names

        # 追加が必要なフォールバックタイプ
        fallbacks_to_add = []
        if not has_person:
            fallbacks_to_add.append(person_fallback)
        if not has_organization:
            fallbacks_to_add.append(organization_fallback)

        if fallbacks_to_add:
            current_count = len(result["entity_types"])
            needed_slots = len(fallbacks_to_add)

            # 追加後に10個を超える場合、既存タイプを削除
            if current_count + needed_slots > MAX_ENTITY_TYPES:
                to_remove = current_count + needed_slots - MAX_ENTITY_TYPES
                result["entity_types"] = result["entity_types"][:-to_remove]

            # フォールバックタイプを追加
            result["entity_types"].extend(fallbacks_to_add)

        # 最終的に制限を超えないことを確認（防御的プログラミング）
        if len(result["entity_types"]) > MAX_ENTITY_TYPES:
            result["entity_types"] = result["entity_types"][:MAX_ENTITY_TYPES]

        if len(result["edge_types"]) > MAX_EDGE_TYPES:
            result["edge_types"] = result["edge_types"][:MAX_EDGE_TYPES]

        return result

    def generate_python_code(self, ontology: Dict[str, Any]) -> str:
        """
        オントロジー定義をPythonコードに変換（ontology.py相当）

        Args:
            ontology: オントロジー定義

        Returns:
            Pythonコード文字列
        """
        code_lines = [
            '"""',
            'カスタムエンティティタイプ定義',
            'MiroFishにより自動生成、HRキャリアシミュレーション用',
            '"""',
            '',
            'from pydantic import Field',
            'from zep_cloud.external_clients.ontology import EntityModel, EntityText, EdgeModel',
            '',
            '',
            '# ============== エンティティタイプ定義 ==============',
            '',
        ]

        # エンティティタイプを生成
        for entity in ontology.get("entity_types", []):
            name = entity["name"]
            desc = entity.get("description", f"A {name} entity.")

            code_lines.append(f'class {name}(EntityModel):')
            code_lines.append(f'    """{desc}"""')

            attrs = entity.get("attributes", [])
            if attrs:
                for attr in attrs:
                    attr_name = attr["name"]
                    attr_desc = attr.get("description", attr_name)
                    code_lines.append(f'    {attr_name}: EntityText = Field(')
                    code_lines.append(f'        description="{attr_desc}",')
                    code_lines.append(f'        default=None')
                    code_lines.append(f'    )')
            else:
                code_lines.append('    pass')

            code_lines.append('')
            code_lines.append('')

        code_lines.append('# ============== 関係タイプ定義 ==============')
        code_lines.append('')

        # 関係タイプを生成
        for edge in ontology.get("edge_types", []):
            name = edge["name"]
            # PascalCaseクラス名に変換
            class_name = ''.join(word.capitalize() for word in name.split('_'))
            desc = edge.get("description", f"A {name} relationship.")

            code_lines.append(f'class {class_name}(EdgeModel):')
            code_lines.append(f'    """{desc}"""')

            attrs = edge.get("attributes", [])
            if attrs:
                for attr in attrs:
                    attr_name = attr["name"]
                    attr_desc = attr.get("description", attr_name)
                    code_lines.append(f'    {attr_name}: EntityText = Field(')
                    code_lines.append(f'        description="{attr_desc}",')
                    code_lines.append(f'        default=None')
                    code_lines.append(f'    )')
            else:
                code_lines.append('    pass')

            code_lines.append('')
            code_lines.append('')

        # タイプ辞書を生成
        code_lines.append('# ============== タイプ設定 ==============')
        code_lines.append('')
        code_lines.append('ENTITY_TYPES = {')
        for entity in ontology.get("entity_types", []):
            name = entity["name"]
            code_lines.append(f'    "{name}": {name},')
        code_lines.append('}')
        code_lines.append('')
        code_lines.append('EDGE_TYPES = {')
        for edge in ontology.get("edge_types", []):
            name = edge["name"]
            class_name = ''.join(word.capitalize() for word in name.split('_'))
            code_lines.append(f'    "{name}": {class_name},')
        code_lines.append('}')
        code_lines.append('')

        # エッジのsource_targetsマッピングを生成
        code_lines.append('EDGE_SOURCE_TARGETS = {')
        for edge in ontology.get("edge_types", []):
            name = edge["name"]
            source_targets = edge.get("source_targets", [])
            if source_targets:
                st_list = ', '.join([
                    f'{{"source": "{st.get("source", "Entity")}", "target": "{st.get("target", "Entity")}"}}'
                    for st in source_targets
                ])
                code_lines.append(f'    "{name}": [{st_list}],')
        code_lines.append('}')

        return '\n'.join(code_lines)
