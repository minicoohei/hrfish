"""
OASIS Agent Profile Generator
Converts Zep graph entities into OASIS simulation platform Agent Profile format

Improvements:
1. Uses Zep retrieval to enrich node info
2. Optimized prompts for detailed persona generation
3. Distinguishes personal entities from abstract group entities
"""

import json
import random
import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime

from openai import OpenAI
from zep_cloud.client import Zep

from ..config import Config
from ..utils.logger import get_logger
from .zep_entity_reader import EntityNode, ZepEntityReader
from .knowledge_loader import KnowledgeLoader

logger = get_logger('mirofish.oasis_profile')


@dataclass
class OasisAgentProfile:
    """OASIS Agent Profile data structure"""
    # Common fields
    user_id: int
    user_name: str
    name: str
    bio: str
    persona: str
    
    # Optional fields - Reddit style
    karma: int = 1000
    
    # Optional fields - Twitter style
    friend_count: int = 100
    follower_count: int = 150
    statuses_count: int = 500
    
    # Additional persona info
    age: Optional[int] = None
    gender: Optional[str] = None
    mbti: Optional[str] = None
    country: Optional[str] = None
    profession: Optional[str] = None
    interested_topics: List[str] = field(default_factory=list)
    
    # Source entity info
    source_entity_uuid: Optional[str] = None
    source_entity_type: Optional[str] = None

    # HR role category (gatekeeper/agent/researcher)
    role_category: Optional[str] = None
    
    created_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    
    def to_reddit_format(self) -> Dict[str, Any]:
        """Convert to Reddit platform format"""
        profile = {
            "user_id": self.user_id,
            "username": self.user_name,  # OASIS library requires field name 'username' (no underscore)
            "name": self.name,
            "bio": self.bio,
            "persona": self.persona,
            "karma": self.karma,
            "created_at": self.created_at,
        }
        
        # Add additional persona info if available
        if self.age:
            profile["age"] = self.age
        if self.gender:
            profile["gender"] = self.gender
        if self.mbti:
            profile["mbti"] = self.mbti
        if self.country:
            profile["country"] = self.country
        if self.profession:
            profile["profession"] = self.profession
        if self.interested_topics:
            profile["interested_topics"] = self.interested_topics
        
        return profile
    
    def to_twitter_format(self) -> Dict[str, Any]:
        """Convert to Twitter platform format"""
        profile = {
            "user_id": self.user_id,
            "username": self.user_name,  # OASIS library requires field name 'username' (no underscore)
            "name": self.name,
            "bio": self.bio,
            "persona": self.persona,
            "friend_count": self.friend_count,
            "follower_count": self.follower_count,
            "statuses_count": self.statuses_count,
            "created_at": self.created_at,
        }
        
        # Add extra persona info
        if self.age:
            profile["age"] = self.age
        if self.gender:
            profile["gender"] = self.gender
        if self.mbti:
            profile["mbti"] = self.mbti
        if self.country:
            profile["country"] = self.country
        if self.profession:
            profile["profession"] = self.profession
        if self.interested_topics:
            profile["interested_topics"] = self.interested_topics
        
        return profile
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to full dict format"""
        return {
            "user_id": self.user_id,
            "user_name": self.user_name,
            "name": self.name,
            "bio": self.bio,
            "persona": self.persona,
            "karma": self.karma,
            "friend_count": self.friend_count,
            "follower_count": self.follower_count,
            "statuses_count": self.statuses_count,
            "age": self.age,
            "gender": self.gender,
            "mbti": self.mbti,
            "country": self.country,
            "profession": self.profession,
            "interested_topics": self.interested_topics,
            "source_entity_uuid": self.source_entity_uuid,
            "source_entity_type": self.source_entity_type,
            "created_at": self.created_at,
        }


class OasisProfileGenerator:
    """
    OASIS Profile Generator
    
    Convert entities from Zep graph to OASIS simulation Agent Profiles
    
    Optimization features:
    1. Call Zep graph search for richer context
    2. Generate detailed profiles (basic info, career history, personality traits, social media behavior, etc.)
    3. Distinguish individual entities from abstract group entities
    """
    
    # MBTI type list
    MBTI_TYPES = [
        "INTJ", "INTP", "ENTJ", "ENTP",
        "INFJ", "INFP", "ENFJ", "ENFP",
        "ISTJ", "ISFJ", "ESTJ", "ESFJ",
        "ISTP", "ISFP", "ESTP", "ESFP"
    ]
    
    # Common country list
    COUNTRIES = [
        "China", "US", "UK", "Japan", "Germany", "France", 
        "Canada", "Australia", "Brazil", "India", "South Korea"
    ]
    
    # Individual entity types (need specific profiles)
    INDIVIDUAL_ENTITY_TYPES = [
        "student", "alumni", "professor", "person", "publicfigure", 
        "expert", "faculty", "official", "journalist", "activist"
    ]
    
    # Group/organization type entities (need to generate group representative personas)
    GROUP_ENTITY_TYPES = [
        "university", "governmentagency", "organization", "ngo", 
        "mediaoutlet", "company", "institution", "group", "community"
    ]
    
    def __init__(
        self, 
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        zep_api_key: Optional[str] = None,
        graph_id: Optional[str] = None
    ):
        self.api_key = api_key or Config.LLM_API_KEY
        self.base_url = base_url or Config.LLM_BASE_URL
        # プロフィール生成はエージェント品質を決める重要処理 → チャットモデル（gpt-5.4）を使用
        self.model_name = model_name or getattr(Config, 'LLM_CHAT_MODEL_NAME', None) or Config.LLM_MODEL_NAME

        self._client = None  # 遅延初期化: use_llm=False時にOpenAI不要
        
        # Zep client for retrieving rich context
        self.zep_api_key = zep_api_key or Config.ZEP_API_KEY
        self.zep_client = None
        self.graph_id = graph_id
        
        if self.zep_api_key:
            try:
                self.zep_client = Zep(api_key=self.zep_api_key)
            except Exception as e:
                logger.warning(f"Zep client initialization failed: {e}")
    
    @property
    def client(self):
        """OpenAIクライアントの遅延初期化。LLM使用時のみインスタンス化される。"""
        if self._client is None:
            if not self.api_key:
                raise ValueError("LLM_API_KEY not configured")
            self._client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url
            )
        return self._client

    def generate_profile_from_entity(
        self, 
        entity: EntityNode, 
        user_id: int,
        use_llm: bool = True
    ) -> OasisAgentProfile:
        """
        Generate OASIS Agent Profile from Zep entity
        
        Args:
            entity: Zep entity node
            user_id: User ID (for OASIS)
            use_llm: Whether to use LLM to generate detailed personas
            
        Returns:
            OasisAgentProfile
        """
        entity_type = entity.get_entity_type() or "Entity"
        
        # Basic info
        name = entity.name
        user_name = self._generate_username(name)
        
        # Build context info
        context = self._build_entity_context(entity)
        
        if use_llm:
            # Use LLM to generate detailed profile
            profile_data = self._generate_profile_with_llm(
                entity_name=name,
                entity_type=entity_type,
                entity_summary=entity.summary,
                entity_attributes=entity.attributes,
                context=context
            )
        else:
            # Generate base persona using rules
            profile_data = self._generate_profile_rule_based(
                entity_name=name,
                entity_type=entity_type,
                entity_summary=entity.summary,
                entity_attributes=entity.attributes
            )
        
        return OasisAgentProfile(
            user_id=user_id,
            user_name=user_name,
            name=name,
            bio=profile_data.get("bio", f"{entity_type}: {name}"),
            persona=profile_data.get("persona", entity.summary or f"A {entity_type} named {name}."),
            karma=profile_data.get("karma", random.randint(500, 5000)),
            friend_count=profile_data.get("friend_count", random.randint(50, 500)),
            follower_count=profile_data.get("follower_count", random.randint(100, 1000)),
            statuses_count=profile_data.get("statuses_count", random.randint(100, 2000)),
            age=profile_data.get("age"),
            gender=profile_data.get("gender"),
            mbti=profile_data.get("mbti"),
            country=profile_data.get("country"),
            profession=profile_data.get("profession"),
            interested_topics=profile_data.get("interested_topics", []),
            source_entity_uuid=entity.uuid,
            source_entity_type=entity_type,
        )
    
    def _generate_username(self, name: str) -> str:
        """Generate username"""
        # Remove special characters, convert to lowercase
        username = name.lower().replace(" ", "_")
        username = ''.join(c for c in username if c.isalnum() or c == '_')
        
        # Add random suffix to avoid duplicates
        suffix = random.randint(100, 999)
        return f"{username}_{suffix}"
    
    def _search_zep_for_entity(self, entity: EntityNode) -> Dict[str, Any]:
        """
        Use Zep graph hybrid search to get rich entity-related information
        
        Zep has no built-in hybrid search API; search edges and nodes separately then merge results.
        Use parallel requests for improved efficiency.
        
        Args:
            entity: Entity node object
            
        Returns:
            Dict containing facts, node_summaries, context
        """
        import concurrent.futures
        
        if not self.zep_client:
            return {"facts": [], "node_summaries": [], "context": ""}
        
        entity_name = entity.name
        
        results = {
            "facts": [],
            "node_summaries": [],
            "context": ""
        }
        
        # Must have graph_id for search
        if not self.graph_id:
            logger.debug(f"Skipping Zep retrieval: graph_id not set")
            return results
        
        comprehensive_query = f"All information, activities, events, relationships and background about {entity_name}"
        
        def search_edges():
            """Search edges (facts/relationships) - with retry"""
            max_retries = 3
            last_exception = None
            delay = 2.0
            
            for attempt in range(max_retries):
                try:
                    return self.zep_client.graph.search(
                        query=comprehensive_query,
                        graph_id=self.graph_id,
                        limit=30,
                        scope="edges",
                        reranker="rrf"
                    )
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        logger.debug(f"Zep edge search attempt {attempt + 1}  failed: {str(e)[:80]}, retrying...")
                        time.sleep(delay)
                        delay *= 2
                    else:
                        logger.debug(f"Zep edge search failed after {max_retries} attempts: {e}")
            return None
        
        def search_nodes():
            """Search nodes (entity summaries) - with retry"""
            max_retries = 3
            last_exception = None
            delay = 2.0
            
            for attempt in range(max_retries):
                try:
                    return self.zep_client.graph.search(
                        query=comprehensive_query,
                        graph_id=self.graph_id,
                        limit=20,
                        scope="nodes",
                        reranker="rrf"
                    )
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        logger.debug(f"Zep node search attempt {attempt + 1}  failed: {str(e)[:80]}, retrying...")
                        time.sleep(delay)
                        delay *= 2
                    else:
                        logger.debug(f"Zep node search still failed after {max_retries} attempts: {e}")
            return None
        
        try:
            # Execute edges and nodes search in parallel
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                edge_future = executor.submit(search_edges)
                node_future = executor.submit(search_nodes)
                
                # Get results
                edge_result = edge_future.result(timeout=30)
                node_result = node_future.result(timeout=30)
            
            # Process edge search results
            all_facts = set()
            if edge_result and hasattr(edge_result, 'edges') and edge_result.edges:
                for edge in edge_result.edges:
                    if hasattr(edge, 'fact') and edge.fact:
                        all_facts.add(edge.fact)
            results["facts"] = list(all_facts)
            
            # Process node search results
            all_summaries = set()
            if node_result and hasattr(node_result, 'nodes') and node_result.nodes:
                for node in node_result.nodes:
                    if hasattr(node, 'summary') and node.summary:
                        all_summaries.add(node.summary)
                    if hasattr(node, 'name') and node.name and node.name != entity_name:
                        all_summaries.add(f"Related entity: {node.name}")
            results["node_summaries"] = list(all_summaries)
            
            # Build comprehensive context
            context_parts = []
            if results["facts"]:
                context_parts.append("Factual info:\n" + "\n".join(f"- {f}" for f in results["facts"][:20]))
            if results["node_summaries"]:
                context_parts.append("Related entity:\n" + "\n".join(f"- {s}" for s in results["node_summaries"][:10]))
            results["context"] = "\n\n".join(context_parts)
            
            logger.info(f"ZepHybrid search complete: {entity_name}, Retrieved {len(results['facts'])} facts, {len(results['node_summaries'])} related nodes")
            
        except concurrent.futures.TimeoutError:
            logger.warning(f"Zep retrieval timeout ({entity_name})")
        except Exception as e:
            logger.warning(f"Zep retrieval failed ({entity_name}): {e}")
        
        return results
    
    def _build_entity_context(self, entity: EntityNode) -> str:
        """
        Build complete context info for entity
        
        Including:
        1. Entity edge info (facts)
        2. Related node details
        3. ZepRich info from hybrid search
        """
        context_parts = []
        
        # 1. Add entity attribute info
        if entity.attributes:
            attrs = []
            for key, value in entity.attributes.items():
                if value and str(value).strip():
                    attrs.append(f"- {key}: {value}")
            if attrs:
                context_parts.append("### Entity attributes\n" + "\n".join(attrs))
        
        # 2. Add related edge info (facts/relationships)
        existing_facts = set()
        if entity.related_edges:
            relationships = []
            for edge in entity.related_edges:  # No limit on count
                fact = edge.get("fact", "")
                edge_name = edge.get("edge_name", "")
                direction = edge.get("direction", "")
                
                if fact:
                    relationships.append(f"- {fact}")
                    existing_facts.add(fact)
                elif edge_name:
                    if direction == "outgoing":
                        relationships.append(f"- {entity.name} --[{edge_name}]--> (related entity)")
                    else:
                        relationships.append(f"- (related entity) --[{edge_name}]--> {entity.name}")
            
            if relationships:
                context_parts.append("### Related facts and relationships\n" + "\n".join(relationships))
        
        # 3. Add related node details
        if entity.related_nodes:
            related_info = []
            for node in entity.related_nodes:  # No limit on count
                node_name = node.get("name", "")
                node_labels = node.get("labels", [])
                node_summary = node.get("summary", "")
                
                # Filter out default labels
                custom_labels = [l for l in node_labels if l not in ["Entity", "Node"]]
                label_str = f" ({', '.join(custom_labels)})" if custom_labels else ""
                
                if node_summary:
                    related_info.append(f"- **{node_name}**{label_str}: {node_summary}")
                else:
                    related_info.append(f"- **{node_name}**{label_str}")
            
            if related_info:
                context_parts.append("### Related entity info\n" + "\n".join(related_info))
        
        # 4. Use Zep hybrid retrieval for richer info
        zep_results = self._search_zep_for_entity(entity)
        
        if zep_results.get("facts"):
            # Deduplicate: exclude existing facts
            new_facts = [f for f in zep_results["facts"] if f not in existing_facts]
            if new_facts:
                context_parts.append("### Facts Retrieved from Zep\n" + "\n".join(f"- {f}" for f in new_facts[:15]))
        
        if zep_results.get("node_summaries"):
            context_parts.append("### Related Nodes Retrieved from Zep\n" + "\n".join(f"- {s}" for s in zep_results["node_summaries"][:10]))
        
        return "\n\n".join(context_parts)
    
    def _is_individual_entity(self, entity_type: str) -> bool:
        """Check if entity is a personal type"""
        return entity_type.lower() in self.INDIVIDUAL_ENTITY_TYPES
    
    def _is_group_entity(self, entity_type: str) -> bool:
        """Check if entity is a group/organization type"""
        return entity_type.lower() in self.GROUP_ENTITY_TYPES
    
    def _generate_profile_with_llm(
        self,
        entity_name: str,
        entity_type: str,
        entity_summary: str,
        entity_attributes: Dict[str, Any],
        context: str
    ) -> Dict[str, Any]:
        """
        Use LLM to generate very detailed persona
        
        Differentiate by entity type:
        - Personal entity: generate specific character settings
        - Group/organization entities: Generate representative account settings
        """
        
        is_individual = self._is_individual_entity(entity_type)
        
        if is_individual:
            prompt = self._build_individual_persona_prompt(
                entity_name, entity_type, entity_summary, entity_attributes, context
            )
        else:
            prompt = self._build_group_persona_prompt(
                entity_name, entity_type, entity_summary, entity_attributes, context
            )

        # Try multiple times until success or max retries
        max_attempts = 3
        last_error = None
        
        for attempt in range(max_attempts):
            try:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": self._get_system_prompt(is_individual)},
                        {"role": "user", "content": prompt}
                    ],
                    response_format={"type": "json_object"},
                    # gpt-5-mini does not support custom temperature
                )
                
                content = response.choices[0].message.content
                
                # Check if truncated (finish_reason is not 'stop')
                finish_reason = response.choices[0].finish_reason
                if finish_reason == 'length':
                    logger.warning(f"LLM output truncated (attempt {attempt+1}), attempting fix...")
                    content = self._fix_truncated_json(content)
                
                # Try to parse JSON
                try:
                    result = json.loads(content)
                    
                    # Validate required fields
                    if "bio" not in result or not result["bio"]:
                        result["bio"] = entity_summary[:200] if entity_summary else f"{entity_type}: {entity_name}"
                    if "persona" not in result or not result["persona"]:
                        result["persona"] = entity_summary or f"{entity_name} is a/an {entity_type}。"
                    
                    return result
                    
                except json.JSONDecodeError as je:
                    logger.warning(f"JSON parse failed (attempt {attempt+1}): {str(je)[:80]}")
                    
                    # Try to fix JSON
                    result = self._try_fix_json(content, entity_name, entity_type, entity_summary)
                    if result.get("_fixed"):
                        del result["_fixed"]
                        return result
                    
                    last_error = je
                    
            except Exception as e:
                logger.warning(f"LLM call failed (attempt {attempt+1}): {str(e)[:80]}")
                last_error = e
                import time
                time.sleep(1 * (attempt + 1))  # exponential backoff
        
        logger.warning(f"LLM profile generation failed（{max_attempts} attempts）: {last_error}, using rule-based generation")
        return self._generate_profile_rule_based(
            entity_name, entity_type, entity_summary, entity_attributes
        )
    
    def _fix_truncated_json(self, content: str) -> str:
        """Fix truncated JSON (output truncated by max_tokens limit)"""
        import re
        
        # If JSON is truncated, try to close it
        content = content.strip()
        
        # Count unclosed brackets
        open_braces = content.count('{') - content.count('}')
        open_brackets = content.count('[') - content.count(']')
        
        # Check for unclosed strings
        # Simple check: if no comma or closing bracket after last quote, string may be truncated
        if content and content[-1] not in '",}]':
            # Try to close string
            content += '"'
        
        # Close brackets
        content += ']' * open_brackets
        content += '}' * open_braces
        
        return content
    
    def _try_fix_json(self, content: str, entity_name: str, entity_type: str, entity_summary: str = "") -> Dict[str, Any]:
        """Try to fix broken JSON"""
        import re
        
        # 1. First try to fix truncation
        content = self._fix_truncated_json(content)
        
        # 2. Try to extract JSON part
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            json_str = json_match.group()
            
            # 3. Handle newline issues in strings
            # Find all string values and replace newlines in them
            def fix_string_newlines(match):
                s = match.group(0)
                # Replace actual newlines in strings with spaces
                s = s.replace('\n', ' ').replace('\r', ' ')
                # Replace extra spaces
                s = re.sub(r'\s+', ' ', s)
                return s
            
            # Match JSON string values
            json_str = re.sub(r'"[^"\\]*(?:\\.[^"\\]*)*"', fix_string_newlines, json_str)
            
            # 4. Try to parse
            try:
                result = json.loads(json_str)
                result["_fixed"] = True
                return result
            except json.JSONDecodeError as e:
                # 5. If still failing, try more aggressive fix
                try:
                    # Remove all control characters
                    json_str = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', json_str)
                    # Replace all consecutive whitespace
                    json_str = re.sub(r'\s+', ' ', json_str)
                    result = json.loads(json_str)
                    result["_fixed"] = True
                    return result
                except:
                    pass
        
        # 6. Try to extract partial info from content
        bio_match = re.search(r'"bio"\s*:\s*"([^"]*)"', content)
        persona_match = re.search(r'"persona"\s*:\s*"([^"]*)', content)  # May be truncated
        
        bio = bio_match.group(1) if bio_match else (entity_summary[:200] if entity_summary else f"{entity_type}: {entity_name}")
        persona = persona_match.group(1) if persona_match else (entity_summary or f"{entity_name} is a/an {entity_type}。")
        
        # If meaningful content was extracted, mark as fixed
        if bio_match or persona_match:
            logger.info(f"Extracted partial info from corrupted JSON")
            return {
                "bio": bio,
                "persona": persona,
                "_fixed": True
            }
        
        # 7. Complete failure, return base structure
        logger.warning(f"JSON fix failed, return base structure")
        return {
            "bio": entity_summary[:200] if entity_summary else f"{entity_type}: {entity_name}",
            "persona": entity_summary or f"{entity_name} is a/an {entity_type}。"
        }
    
    def _get_system_prompt(self, is_individual: bool) -> str:
        """Get system prompt"""
        base_prompt = """あなたはキャリアシミュレーション人物像生成の専門家です。求職者の履歴書を多角的に評価する関係者のペルソナを生成してください。詳細かつリアルな人物設定を生成し、既知の現実情報を最大限反映してください。有効なJSON形式で返し、文字列値にエスケープされていない改行を含めないでください。日本語で出力してください。

重要：エンティティ名とタイプから、以下3カテゴリのいずれかに分類し、そのカテゴリに応じた行動パターン・評価視点を持つペルソナを生成してください。

【カテゴリA: 選考・採用する側（ゲートキーパー）】
候補者を「採るか採らないか」を判断する立場。スクリーニング・面接・合否判定が行動の中心。
- 採用担当者: 書類選考、一次面接、候補者の基本要件チェック
- 人事マネージャー: 組織適合性、給与交渉、オファー判断
- 現場マネージャー: 実務能力の見極め、チーム適合性、即戦力判定
- 事業部長・VP: 部門戦略との整合性、将来のリーダーシップポテンシャル
- CEO・社長: カルチャーフィット、経営ビジョンとの一致
- CTO・技術役員: 技術力の深さ、アーキテクチャ設計力、技術的リーダーシップ
- 取締役: ガバナンス観点、経営人材としてのポテンシャル

【カテゴリB: 仲介・助言する側（エージェント/コーチ）】
候補者のキャリアを支援・仲介する立場。マッチング、市場価値の見立て、キャリア戦略の助言が行動の中心。
- キャリアアドバイザー: 求職者の強み分析、求人マッチング、面接対策
- リクルーティングアドバイザー: 企業要件との適合度分析、年収相場の提示
- ヘッドハンター: エグゼクティブ市場での価値評価、非公開ポジションとの適合
- 人材コンサルタント: 組織開発観点からの人材要件定義
- キャリアコーチ: 自己分析支援、キャリアビジョンの明確化

【カテゴリC: 観察・分析する側（リサーチャー/ピア）】
候補者を直接採用しないが、労働市場・業界・同職種の観点から評価・分析する立場。
- 同職種の現役社員: 同業者としてのスキルレベル評価、業界内での相対的位置づけ
- 業界権威・Tier1企業社員: ハイレベル人材としての水準判定
- 類似キャリアの転職成功者: 自身の経験と照らし合わせた実践的助言
- 転職失敗者: 失敗パターンとの類似性指摘、注意喚起
- 雇用ジャーナリスト: 労働市場トレンドの文脈での分析
- 社会学者: 雇用構造・社会変動の観点からの考察
- 労働経済学者: 賃金動態・労働市場需給の定量分析
- 人事系大学教授: 人材マネジメント理論に基づく評価
- 業界アナリスト: 業界動向と人材需要の予測

【カテゴリD: 私的関係者（友人・同僚・家族）】
候補者の人間的側面を知る立場。公式な評価ではなく、日常的な付き合いから見えるリアルな人物像を提供。
- 現職の同僚: 日常業務での協働経験、チームワーク、職場での人柄
- 元同僚・元上司: 実際の業務パフォーマンスに基づく評価、成長の軌跡
- 大学時代の友人: 学生時代からの変化、本来の性格、長期的な価値観
- 趣味・コミュニティの仲間: 仕事以外の側面、ストレス発散、人間関係構築力
- 同業種の友人: 業界情報交換、転職相談相手、キャリア比較の参照点
- 異業種の友人: 異なる視点からのキャリア観、多角的なアドバイス
- メンター: 長期的なキャリア指導、人生経験に基づく助言

エンティティ名が「Person」や一般的な人名の場合でも、コンテキスト情報からキャリア評価に最も関連する上記の役割を1つ割り当て、そのカテゴリの行動パターンに沿った専門家として詳細なペルソナを生成してください。
エンティティの関係性が明確でない場合は、カテゴリA〜Dをバランスよく配分し、特にカテゴリDの友人・同僚ロールも積極的に割り当ててください。"""
        return base_prompt
    
    def _build_individual_persona_prompt(
        self,
        entity_name: str,
        entity_type: str,
        entity_summary: str,
        entity_attributes: Dict[str, Any],
        context: str
    ) -> str:
        """Build detailed persona prompt for individual entity"""
        
        attrs_str = json.dumps(entity_attributes, ensure_ascii=False) if entity_attributes else "なし"
        context_str = context[:3000] if context else "No additional context"

        return f"""エンティティに対して、キャリアシミュレーションにおける関係者の詳細なペルソナを生成してください。既知の現実情報を最大限反映してください。

エンティティ名: {entity_name}
エンティティタイプ: {entity_type}
エンティティ概要: {entity_summary}
エンティティ属性: {attrs_str}

コンテキスト情報:
{context_str}

以下のフィールドを含むJSONを生成してください:

1. bio: 職務概要（200字）。この人物がキャリア評価においてどのような立場にあるかを簡潔に記述
2. persona: キャリア観点での詳細設定（2000字の純テキスト）。以下を含むこと:
   - 基本情報（年齢、職業、教育背景、所在地）
   - 職務背景（重要な経歴、求職者との関係性、業界での立ち位置）
   - 役割カテゴリ（A:選考する側 / B:仲介・助言する側 / C:観察・分析する側 / D:私的関係者 のいずれか）
   - カテゴリ別の行動パターン:
     * カテゴリA（選考側）: 面接での質問傾向、合否判断基準、重視する経験・スキル、オファー条件の考え方
     * カテゴリB（仲介側）: マッチング基準、候補者への助言スタイル、市場価値の見立て方、推薦時のポイント
     * カテゴリC（観察側）: 分析の切り口、同業者としての評価軸、研究テーマとの関連、客観的な所見の出し方
     * カテゴリD（私的関係者）: 日常の人柄、仕事以外の側面、人間関係から見たキャリア適性、率直なアドバイス
   - 評価基準（この人物が人材を評価する際に重視するポイント）
   - 性格特徴（MBTI類型、コアとなる性格、コミュニケーションスタイル）
   - 立場・観点（キャリアに対する価値観、重視する経験・資格）
   - 個人の記憶（過去の採用・評価・研究における具体的な判断エピソード）
   - 【必須】会話テーマ指示: このキャラクターは他のエージェントとの対話で以下のテーマについて積極的に議論すること:
     * 候補者のキャリアの可能性と将来性（「この経験があれば○○方面に進める」「△△業界で需要が高まっている」）
     * 業界の未来予測（「今後3-5年で○○スキルの需要が激変する」「この業界はAI/DXでこう変わる」）
     * キャリアパスの分岐シナリオ（「マネジメントに進むならこのタイミング」「専門特化なら○○の深掘りが必要」）
     * 他のエージェントの意見への反応と議論（「○○さんの指摘に同意だが、△△の観点も重要」）
     * 候補者が次に経験すべきこと（「次の転職先では○○を経験すべき」「足りないのは□□の実戦経験」）
3. age: 年齢（整数）
4. gender: 性別、英語で: "male" または "female"
5. mbti: MBTIタイプ（例：INTJ、ENFP等）
6. country: 国名（日本語、例："日本"）
7. profession: 職業
8. role_category: 役割カテゴリ（"gatekeeper" / "agent" / "researcher" / "friend" のいずれか）
9. interested_topics: 関心トピック配列

重要:
- すべてのフィールド値は文字列または数値。改行文字を使用しないこと
- personaは一つの連続したテキストであること
- 日本語で記述（genderフィールドのみ英語でmale/female）
- 内容はエンティティ情報と一貫性を保つこと
- ageは有効な整数、genderは"male"または"female"であること
- professionには具体的な役割を設定すること（例：キャリアアドバイザー、ヘッドハンター、採用担当者、人事マネージャー、現場マネージャー、事業部長、CTO、同職種エンジニア、労働経済学者、雇用ジャーナリスト、元同僚、大学時代の友人等）。「Person」のような汎用ラベルは使用不可
- role_categoryは必ず "gatekeeper"（選考する側）/ "agent"（仲介・助言する側）/ "researcher"（観察・分析する側）/ "friend"（私的関係者）のいずれかを設定
- エンティティタイプがPersonやOrganizationでも、コンテキストからキャリア評価における最適な専門家ロールとカテゴリを判断して割り当てること
- エンティティの関係性が不明確な一般的人名の場合、友人・同僚（カテゴリD）の割り当ても積極的に検討すること
"""

    def _build_group_persona_prompt(
        self,
        entity_name: str,
        entity_type: str,
        entity_summary: str,
        entity_attributes: Dict[str, Any],
        context: str
    ) -> str:
        """Build detailed persona prompt for organization entity"""

        attrs_str = json.dumps(entity_attributes, ensure_ascii=False) if entity_attributes else "なし"
        context_str = context[:3000] if context else "No additional context"

        # Inject industry knowledge
        knowledge_context = KnowledgeLoader.get_relevant_knowledge(
            context_str, injection_point="group_persona"
        )
        knowledge_section = f"""

## 業界・市場データ（参考情報）
{knowledge_context}
""" if knowledge_context else ""

        return f"""企業・組織エンティティに対して、候補者と業務上の関係があった人物のペルソナを生成してください。
この企業は候補者が過去に在籍していた企業、またはクライアント企業（候補者がサービスを提供した相手）です。

## 関係性の自動判定ルール
コンテキスト情報を分析し、{entity_name}と候補者の関係を以下のどちらかに判定してください:
- **元勤務先**: 候補者が{entity_name}に社員として在籍していた場合 → 「元同僚」「元上司」の視点
- **クライアント**: 候補者が{entity_name}に対してサービス提供・コンサル・開発等を行っていた場合 → 「クライアント担当者」の視点（発注側として候補者の仕事ぶりを評価）

エンティティ名: {entity_name}
エンティティタイプ: {entity_type}
エンティティ概要: {entity_summary}
エンティティ属性: {attrs_str}

コンテキスト情報:
{context_str}

以下のフィールドを含むJSONを生成してください:

1. bio: この人物の概要（200字）。候補者との関係性と、現在の立場を簡潔に記述
2. persona: 詳細設定（2000字の純テキスト）。関係性に応じて以下を含むこと:

   【元勤務先の場合（元同僚・元上司）】
   - 基本情報（この人物の名前、年齢、現在の職業、{entity_name}での当時の役職）
   - 候補者との関係性（同じチームだった/プロジェクトで協業した/上司だった等）
   - 候補者の業務実態の証言（「○○プロジェクトでこういう仕事をしていた」等）
   - 候補者の強み・弱みの所見（一緒に働いた経験に基づく具体的な評価）
   - 候補者の働き方・コミュニケーションスタイルの所見
   - {entity_name}の組織文化と候補者のフィット度合い

   【クライアントの場合（発注側担当者）】
   - 基本情報（この人物の名前、年齢、{entity_name}での役職・部門）
   - 候補者への発注内容（どんなプロジェクトを依頼したか）
   - 候補者の成果物・デリバリーの品質評価（期待以上/期待通り/期待以下）
   - 候補者のコミュニケーション・レスポンス・提案力の評価
   - リピート発注したか/したいか、その理由
   - 他社ベンダーと比較した際の候補者の位置づけ

   共通:
   - カテゴリC（観察・分析する側）またはカテゴリD（私的関係者：元同僚として友人的な関係にもなり得る）としての評価スタンス
   - 【必須】会話テーマ指示: 他のエージェントとの対話で以下について積極的に議論すること:
     * 候補者のキャリアの将来性（「この経歴があれば○○方面に進める」「市場での需要変化を考えると...」）
     * 業界の未来予測（「この業界は今後○○の方向に変わる」「必要スキルが△△にシフトしつつある」）
     * 候補者の成長シナリオ（「あと2-3年○○を経験すれば一段上のレベルに行ける」）
     * 他のエージェントの評価への反応（同意・反論・別角度からの補足）

3. age: この人物の年齢（整数、25〜55の範囲）
4. gender: 性別、英語で: "male" または "female"
5. mbti: MBTIタイプ（例：ISTJ、ENFP等）
6. country: 国名（日本語、例："日本"）
7. profession: この人物の現在の職業（「{entity_name}の元同僚」「{entity_name}の元上司」「{entity_name}のクライアント担当者」等）
8. role_category: "researcher"（観察・分析する側）または "friend"（元同僚として私的関係が強い場合）
9. interested_topics: 関心領域配列

重要:
- すべてのフィールド値は文字列または数値。null値は不可
- personaは一つの連続したテキストであること。改行文字を使用しないこと
- 日本語で記述（genderフィールドのみ英語でmale/female）
- この人物は「組織」ではなく、その組織に所属していた/している「個人」として生成すること
- 候補者との業務経験に基づく具体的な証言・評価を含めること
- 「一緒に働きましょう」等の勧誘は不可。あくまで過去の業務実態の証言・評価に留めること
{knowledge_section}"""
    
    def _generate_profile_rule_based(
        self,
        entity_name: str,
        entity_type: str,
        entity_summary: str,
        entity_attributes: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate base persona using rules"""
        
        # Generate different personas based on entity type
        entity_type_lower = entity_type.lower()
        
        if entity_type_lower in ["student", "alumni"]:
            return {
                "bio": f"{entity_type} with interests in academics and social issues.",
                "persona": f"{entity_name} is a {entity_type.lower()} who is actively engaged in academic and social discussions. They enjoy sharing perspectives and connecting with peers.",
                "age": random.randint(18, 30),
                "gender": random.choice(["male", "female"]),
                "mbti": random.choice(self.MBTI_TYPES),
                "country": random.choice(self.COUNTRIES),
                "profession": "Student",
                "interested_topics": ["Education", "Social Issues", "Technology"],
            }
        
        elif entity_type_lower in ["publicfigure", "expert", "faculty"]:
            return {
                "bio": f"Expert and thought leader in their field.",
                "persona": f"{entity_name} is a recognized {entity_type.lower()} who shares insights and opinions on important matters. They are known for their expertise and influence in public discourse.",
                "age": random.randint(35, 60),
                "gender": random.choice(["male", "female"]),
                "mbti": random.choice(["ENTJ", "INTJ", "ENTP", "INTP"]),
                "country": random.choice(self.COUNTRIES),
                "profession": entity_attributes.get("occupation", "Expert"),
                "interested_topics": ["Politics", "Economics", "Culture & Society"],
            }
        
        elif entity_type_lower in ["mediaoutlet", "socialmediaplatform"]:
            return {
                "bio": f"Official account for {entity_name}. News and updates.",
                "persona": f"{entity_name} is a media entity that reports news and facilitates public discourse. The account shares timely updates and engages with the audience on current events.",
                "age": 30,  # Organization virtual age
                "gender": "other",  # Organizations use other
                "mbti": "ISTJ",  # Organization style: rigorous and conservative
                "country": "China",
                "profession": "Media",
                "interested_topics": ["General News", "Current Events", "Public Affairs"],
            }
        
        elif entity_type_lower in ["university", "governmentagency", "ngo", "organization"]:
            return {
                "bio": f"Official account of {entity_name}.",
                "persona": f"{entity_name} is an institutional entity that communicates official positions, announcements, and engages with stakeholders on relevant matters.",
                "age": 30,  # Organization virtual age
                "gender": "other",  # Organizations use other
                "mbti": "ISTJ",  # Organization style: rigorous and conservative
                "country": "China",
                "profession": entity_type,
                "interested_topics": ["Public Policy", "Community", "Official Announcements"],
            }
        
        else:
            # Default persona
            return {
                "bio": entity_summary[:150] if entity_summary else f"{entity_type}: {entity_name}",
                "persona": entity_summary or f"{entity_name} is a {entity_type.lower()} participating in social discussions.",
                "age": random.randint(25, 50),
                "gender": random.choice(["male", "female"]),
                "mbti": random.choice(self.MBTI_TYPES),
                "country": random.choice(self.COUNTRIES),
                "profession": entity_type,
                "interested_topics": ["General", "Social Issues"],
            }
    
    def set_graph_id(self, graph_id: str):
        """Set graph ID for Zep retrieval"""
        self.graph_id = graph_id
    
    def generate_profiles_from_entities(
        self,
        entities: List[EntityNode],
        use_llm: bool = True,
        progress_callback: Optional[callable] = None,
        graph_id: Optional[str] = None,
        parallel_count: int = 5,
        realtime_output_path: Optional[str] = None,
        output_platform: str = "reddit"
    ) -> List[OasisAgentProfile]:
        """
        Batch generate agent profiles from entities (with parallel generation support)
        
        Args:
            entities: Entity list
            use_llm: Whether to use LLM to generate detailed personas
            progress_callback: Progress callback function (current, total, message)
            graph_id: Graph ID for richer context retrieval via Zep
            parallel_count: Parallel generation count, default 5
            realtime_output_path: Realtime write file path (if provided, write after each generation)
            output_platform: Output platform format ("reddit" or "twitter")
            
        Returns:
            Agent profile list
        """
        import concurrent.futures
        from threading import Lock
        
        # Set graph_id for Zep retrieval
        if graph_id:
            self.graph_id = graph_id
        
        total = len(entities)
        profiles = [None] * total  # Pre-allocate list to maintain order
        completed_count = [0]  # Use list for modification in closure
        lock = Lock()
        
        # Helper function for realtime file writing
        def save_profiles_realtime():
            """Save generated profiles to file in realtime"""
            if not realtime_output_path:
                return
            
            with lock:
                # Filter out already generated profiles
                existing_profiles = [p for p in profiles if p is not None]
                if not existing_profiles:
                    return
                
                try:
                    if output_platform == "reddit":
                        # Reddit JSON format
                        profiles_data = [p.to_reddit_format() for p in existing_profiles]
                        with open(realtime_output_path, 'w', encoding='utf-8') as f:
                            json.dump(profiles_data, f, ensure_ascii=False, indent=2)
                    else:
                        # Twitter CSV format
                        import csv
                        profiles_data = [p.to_twitter_format() for p in existing_profiles]
                        if profiles_data:
                            fieldnames = list(profiles_data[0].keys())
                            with open(realtime_output_path, 'w', encoding='utf-8', newline='') as f:
                                writer = csv.DictWriter(f, fieldnames=fieldnames)
                                writer.writeheader()
                                writer.writerows(profiles_data)
                except Exception as e:
                    logger.warning(f"Failed to save profiles in realtime: {e}")
        
        def generate_single_profile(idx: int, entity: EntityNode) -> tuple:
            """Worker function for generating a single profile"""
            entity_type = entity.get_entity_type() or "Entity"
            
            try:
                profile = self.generate_profile_from_entity(
                    entity=entity,
                    user_id=idx,
                    use_llm=use_llm
                )
                
                # Output generated persona to console and log in realtime
                self._print_generated_profile(entity.name, entity_type, profile)
                
                return idx, profile, None
                
            except Exception as e:
                logger.error(f"Generating entity {entity.name}  profile failed: {str(e)}")
                # Create a base profile
                fallback_profile = OasisAgentProfile(
                    user_id=idx,
                    user_name=self._generate_username(entity.name),
                    name=entity.name,
                    bio=f"{entity_type}: {entity.name}",
                    persona=entity.summary or f"A participant in social discussions.",
                    source_entity_uuid=entity.uuid,
                    source_entity_type=entity_type,
                )
                return idx, fallback_profile, str(e)
        
        logger.info(f"Starting parallel generation of {total}  agent profiles (parallel count: {parallel_count}）...")
        print(f"\n{'='*60}")
        print(f"Starting agent profile generation - total {total}  entities, parallel count: {parallel_count}")
        print(f"{'='*60}\n")
        
        # Execute in parallel using thread pool
        with concurrent.futures.ThreadPoolExecutor(max_workers=parallel_count) as executor:
            # Submit all tasks
            future_to_entity = {
                executor.submit(generate_single_profile, idx, entity): (idx, entity)
                for idx, entity in enumerate(entities)
            }
            
            # Collect results
            for future in concurrent.futures.as_completed(future_to_entity):
                idx, entity = future_to_entity[future]
                entity_type = entity.get_entity_type() or "Entity"
                
                try:
                    result_idx, profile, error = future.result()
                    profiles[result_idx] = profile
                    
                    with lock:
                        completed_count[0] += 1
                        current = completed_count[0]
                    
                    # Write to file in realtime
                    save_profiles_realtime()
                    
                    if progress_callback:
                        progress_callback(
                            current, 
                            total, 
                            f"Completed {current}/{total}: {entity.name}（{entity_type}）"
                        )
                    
                    if error:
                        logger.warning(f"[{current}/{total}] {entity.name} Using fallback persona: {error}")
                    else:
                        logger.info(f"[{current}/{total}] Successfully generated persona: {entity.name} ({entity_type})")
                        
                except Exception as e:
                    logger.error(f"Processing entity {entity.name}  exception occurred: {str(e)}")
                    with lock:
                        completed_count[0] += 1
                    profiles[idx] = OasisAgentProfile(
                        user_id=idx,
                        user_name=self._generate_username(entity.name),
                        name=entity.name,
                        bio=f"{entity_type}: {entity.name}",
                        persona=entity.summary or "A participant in social discussions.",
                        source_entity_uuid=entity.uuid,
                        source_entity_type=entity_type,
                    )
                    # Write to file in realtime (even for fallback personas)
                    save_profiles_realtime()
        
        print(f"\n{'='*60}")
        print(f"Profile generation complete! Generated {len([p for p in profiles if p])}  agents")
        print(f"{'='*60}\n")
        
        return profiles
    
    # ========== HR Simulation Agent Generation (New Architecture) ==========
    # Graph = 候補者の事実DB。Agent = 候補者を評価する関係者群 + 候補者ミラー。
    # Graph Entity→Agent直接変換ではなく、Graphを参照しながらLLMで評価者を独立生成。

    def generate_candidate_mirror(
        self,
        entities: List[EntityNode],
        candidate_context: str,
        graph_id: Optional[str] = None,
    ) -> OasisAgentProfile:
        """
        候補者自身のミラーエージェントを生成する。
        Graphの全エンティティ情報を集約し、候補者本人のペルソナを構築。

        Args:
            entities: Zep Graphから取得した全エンティティ
            candidate_context: 履歴書テキスト等の候補者情報
            graph_id: Graph ID

        Returns:
            候補者ミラーのOasisAgentProfile（user_id=0）
        """
        if graph_id:
            self.graph_id = graph_id

        # Graphの全エンティティから候補者の事実情報を集約
        entity_summaries = []
        for entity in entities:
            context = self._build_entity_context(entity)
            entity_type = entity.get_entity_type() or "Entity"
            summary = f"【{entity.name}（{entity_type}）】\n{entity.summary or ''}\n{context}"
            entity_summaries.append(summary)

        graph_context = "\n\n".join(entity_summaries[:20])  # 上位20エンティティ

        prompt = f"""以下の情報から、転職活動中の候補者本人のペルソナを生成してください。
この人物はキャリアシミュレーションで「評価される側」として存在します。

## 候補者の履歴書/経歴
{candidate_context[:3000]}

## ナレッジグラフから抽出された関連情報
{graph_context[:3000]}

以下のJSON形式で返してください:
{{
    "name": "候補者の氏名（履歴書から推定、不明なら「候補者」）",
    "bio": "候補者の概要（200字）。現在の職種・経験年数・主要スキル・転職の動機を含む",
    "persona": "候補者の詳細プロフィール（2000字、改行なし）。以下を含むこと: (1) 学歴・職歴の時系列, (2) 各社での具体的な業務内容と成果, (3) 技術スキル・ソフトスキル, (4) 強み・弱み, (5) キャリアの志向性・転職で実現したいこと, (6) 人柄・コミュニケーションスタイル, (7) MBTIタイプ, (8) 【会話テーマ指示】他のエージェントから評価やアドバイスを受けた際、自分のキャリアビジョンや将来の方向性について語ること。「自分としては○○を目指している」「△△の経験を活かして□□に挑戦したい」のように、評価への応答と自己のキャリア展望を述べること。業界の将来性や次に必要なスキルについても自分の見解を述べること",
    "age": 年齢（整数、推定）,
    "gender": "male" or "female"（推定）,
    "mbti": "MBTIタイプ",
    "profession": "現在の職種",
    "interested_topics": ["関心領域1", "関心領域2", "関心領域3"]
}}"""

        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "あなたはキャリアシミュレーションの候補者プロフィール設計者です。純粋なJSON形式で返してください。"},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
            )
            result = json.loads(response.choices[0].message.content)
        except Exception as e:
            logger.error(f"Candidate mirror generation failed: {e}")
            result = {}

        name = result.get("name", "候補者")
        profile = OasisAgentProfile(
            user_id=0,
            user_name=self._generate_username(name),
            name=name,
            bio=result.get("bio", "転職活動中の候補者"),
            persona=result.get("persona", candidate_context[:500]).replace('\n', ' '),
            age=result.get("age", 30),
            gender=result.get("gender", "male"),
            mbti=result.get("mbti", "INTJ"),
            country="日本",
            profession=result.get("profession", "不明"),
            interested_topics=result.get("interested_topics", ["キャリア", "転職"]),
            source_entity_uuid=None,
            source_entity_type="candidate_mirror",
            role_category="candidate_mirror",
        )

        self._print_generated_profile(name, "候補者ミラー", profile)
        logger.info(f"[Candidate Mirror] Generated: {name}")

        return profile

    def generate_evaluator_agents_from_graph(
        self,
        entities: List[EntityNode],
        candidate_context: str,
        graph_id: Optional[str] = None,
        progress_callback: Optional[callable] = None,
    ) -> List[OasisAgentProfile]:
        """
        Graphの関係性を参照しながら、候補者を評価する関係者エージェントを独立生成。
        Graph Entityを直接Agentに変換するのではなく、Entityの情報を「参照」して
        評価者の視点を持つAgentをLLMで生成する。

        Args:
            entities: Zep Graphから取得した全エンティティ
            candidate_context: 候補者の経歴情報
            graph_id: Graph ID
            progress_callback: 進捗コールバック

        Returns:
            評価者エージェントのリスト（元同僚/クライアント担当者等）
        """
        if graph_id:
            self.graph_id = graph_id

        # 組織系エンティティを抽出（元勤務先 or クライアント）
        org_entities = []
        person_entities = []
        for entity in entities:
            entity_type = (entity.get_entity_type() or "").lower()
            if entity_type in self.GROUP_ENTITY_TYPES or entity_type == "organization":
                org_entities.append(entity)
            elif entity_type in self.INDIVIDUAL_ENTITY_TYPES or entity_type == "person":
                person_entities.append(entity)

        profiles = []
        user_id = 1  # 0は候補者ミラー

        total = len(org_entities)
        if progress_callback:
            progress_callback(0, total, "Graphの関係性から評価者を生成中...")

        # 各組織エンティティに対して、関係者エージェントを生成
        for i, entity in enumerate(org_entities):
            entity_type = entity.get_entity_type() or "Organization"
            context = self._build_entity_context(entity)

            prompt = self._build_group_persona_prompt(
                entity_name=entity.name,
                entity_type=entity_type,
                entity_summary=entity.summary or "",
                entity_attributes=entity.attributes or {},
                context=context
            )

            persona_data = None
            try:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": self._get_system_prompt(is_individual=False)},
                        {"role": "user", "content": prompt}
                    ],
                    response_format={"type": "json_object"},
                )
                persona_data = json.loads(response.choices[0].message.content)
            except Exception as e:
                logger.warning(f"Evaluator generation failed for {entity.name}: {e}")

            if not persona_data:
                persona_data = {
                    "bio": f"{entity.name}の関係者。候補者の業務実態を知る人物。",
                    "persona": f"{entity.name}に関連する人物として、候補者の業務パフォーマンスを評価する立場。",
                    "age": 40, "gender": "male", "mbti": "ISTJ",
                    "country": "日本", "profession": f"{entity.name}の関係者",
                    "role_category": "researcher",
                    "interested_topics": ["業界動向", "人材評価"]
                }

            agent_name = persona_data.get("name", f"{entity.name}関係者")
            profile = OasisAgentProfile(
                user_id=user_id,
                user_name=self._generate_username(agent_name),
                name=agent_name,
                bio=persona_data.get("bio", ""),
                persona=str(persona_data.get("persona", "")).replace('\n', ' '),
                age=persona_data.get("age", 40),
                gender=persona_data.get("gender", "male"),
                mbti=persona_data.get("mbti", "ISTJ"),
                country=persona_data.get("country", "日本"),
                profession=persona_data.get("profession", f"{entity.name}の関係者"),
                interested_topics=persona_data.get("interested_topics", []),
                source_entity_uuid=entity.uuid,
                source_entity_type=persona_data.get("role_category", "researcher"),
                role_category=persona_data.get("role_category", "researcher"),
            )
            profiles.append(profile)
            self._print_generated_profile(agent_name, f"{entity.name}の関係者", profile)
            user_id += 1

            if progress_callback:
                progress_callback(i + 1, total, f"Graph関係者 {i+1}/{total}: {agent_name}（{entity.name}）")

            logger.info(f"[Graph Evaluator {i+1}/{total}] Generated: {agent_name} for {entity.name}")

        return profiles

    def generate_all_hr_agents(
        self,
        entities: List[EntityNode],
        candidate_context: str,
        graph_id: Optional[str] = None,
        use_llm: bool = True,
        progress_callback: Optional[callable] = None,
    ) -> List[OasisAgentProfile]:
        """
        HR版Agent生成の統合メソッド。全カテゴリのエージェントを一括生成する。

        生成順序:
        1. 候補者ミラー（1名、user_id=0）
        2. Graph関係者（元同僚/クライアント、Graphエンティティ数に依存）
        3. HR専門家（プリセット、8名）
        4. 転職先企業の採用担当（LLM推定、5名）
        5. 同職種Topプレイヤー（LLM生成、1名）

        Returns:
            全エージェントのリスト
        """
        all_profiles = []

        # Phase 1: 候補者ミラー
        if progress_callback:
            progress_callback("generating_profiles", 0, "候補者ミラーを生成中...", current=0, total=1)

        mirror = self.generate_candidate_mirror(
            entities=entities,
            candidate_context=candidate_context,
            graph_id=graph_id,
        )
        all_profiles.append(mirror)
        logger.info(f"Phase 1: Candidate mirror generated: {mirror.name}")

        # Phase 2: Graph関係者（元同僚/クライアント）
        if progress_callback:
            progress_callback("generating_profiles", 15, "Graph関係者を生成中...", current=1, total=1)

        evaluators = self.generate_evaluator_agents_from_graph(
            entities=entities,
            candidate_context=candidate_context,
            graph_id=graph_id,
            progress_callback=lambda cur, tot, msg: (
                progress_callback("generating_profiles", 15 + int(cur/max(tot,1) * 35), msg, current=cur, total=tot)
                if progress_callback else None
            ),
        )
        # user_idを連番に振り直し
        for p in evaluators:
            p.user_id = len(all_profiles)
            all_profiles.append(p)
        logger.info(f"Phase 2: {len(evaluators)} graph evaluators generated")

        # Phase 3: HR専門家
        if progress_callback:
            progress_callback("generating_profiles", 55, "HR専門家を生成中...", current=len(all_profiles), total=len(all_profiles) + len(self.HR_SPECIALISTS))

        hr_profiles = self.generate_hr_specialist_profiles(
            start_user_id=len(all_profiles),
            candidate_context=candidate_context,
            use_llm=use_llm,
        )
        all_profiles.extend(hr_profiles)
        logger.info(f"Phase 3: {len(hr_profiles)} HR specialists generated")

        # Phase 4: 転職先企業
        if progress_callback:
            progress_callback("generating_profiles", 75, "転職先候補企業を生成中...", current=len(all_profiles), total=len(all_profiles) + 5)

        target_profiles = self.generate_target_company_profiles(
            start_user_id=len(all_profiles),
            candidate_context=candidate_context,
            num_companies=5,
        )
        all_profiles.extend(target_profiles)
        logger.info(f"Phase 4: {len(target_profiles)} target company agents generated")

        # Phase 5: 同職種Topプレイヤー
        if progress_callback:
            progress_callback("generating_profiles", 90, "同職種Topプレイヤーを生成中...", current=len(all_profiles), total=len(all_profiles) + 1)

        top_player = self.generate_top_player_profile(
            start_user_id=len(all_profiles),
            candidate_context=candidate_context,
        )
        all_profiles.extend(top_player)
        logger.info(f"Phase 5: {len(top_player)} top player generated")

        if progress_callback:
            progress_callback("generating_profiles", 100, f"完了！合計 {len(all_profiles)} エージェント生成", current=len(all_profiles), total=len(all_profiles))

        logger.info(f"All HR agents generated: {len(all_profiles)} total (1 mirror + {len(evaluators)} evaluators + {len(hr_profiles)} HR + {len(target_profiles)} targets + {len(top_player)} top)")

        return all_profiles

    def _print_generated_profile(self, entity_name: str, entity_type: str, profile: OasisAgentProfile):
        """Output generated persona to console in realtime (full content, no truncation)"""
        separator = "-" * 70
        
        # Build full output content (no truncation)
        topics_str = ', '.join(profile.interested_topics) if profile.interested_topics else 'None'
        
        output_lines = [
            f"\n{separator}",
            f"[Generated] {entity_name} ({entity_type})",
            f"{separator}",
            f"Username: {profile.user_name}",
            f"",
            f"【Bio】",
            f"{profile.bio}",
            f"",
            f"【Detailed Persona】",
            f"{profile.persona}",
            f"",
            f"【Basic Attributes】",
            f"Age: {profile.age} | Gender: {profile.gender} | MBTI: {profile.mbti}",
            f"Profession: {profile.profession} | Country: {profile.country}",
            f"Interested topics: {topics_str}",
            separator
        ]
        
        output = "\n".join(output_lines)
        
        # Output to console only (avoid duplication, logger no longer outputs full content)
        print(output)
    
    def save_profiles(
        self,
        profiles: List[OasisAgentProfile],
        file_path: str,
        platform: str = "reddit"
    ):
        """
        Save profiles to file (select correct format per platform)
        
        OASIS platform format requirements:
        - Twitter: CSV format
        - Reddit: JSON format
        
        Args:
            profiles: Profile list
            file_path: File path
            platform: Platform type ("reddit" or "twitter")
        """
        if platform == "twitter":
            self._save_twitter_csv(profiles, file_path)
        else:
            self._save_reddit_json(profiles, file_path)
    
    def _save_twitter_csv(self, profiles: List[OasisAgentProfile], file_path: str):
        """
        Save Twitter profiles as CSV (per OASIS official requirements)
        
        OASIS Twitter required CSV fields:
        - user_id: User ID (sequential from 0 based on CSV order)
        - name: User real name
        - username: System username
        - user_char: Detailed persona description (injected into LLM system prompt to guide agent behavior)
        - description: Brief public bio (displayed on user profile page)
        
        user_char vs description difference:
        - user_char: Internal use, LLM system prompt, determines how agent thinks and acts
        - description: External display, bio visible to other users
        """
        import csv
        
        # Ensure file extension is .csv
        if not file_path.endswith('.csv'):
            file_path = file_path.replace('.json', '.csv')
        
        with open(file_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            # Write OASIS required headers
            headers = ['user_id', 'name', 'username', 'user_char', 'description']
            writer.writerow(headers)
            
            # Write data rows
            for idx, profile in enumerate(profiles):
                # user_char: Full persona (bio + persona), for LLM system prompt
                user_char = profile.bio
                if profile.persona and profile.persona != profile.bio:
                    user_char = f"{profile.bio} {profile.persona}"
                # Handle newlines (replace with spaces in CSV)
                user_char = user_char.replace('\n', ' ').replace('\r', ' ')
                
                # description: Brief bio for external display
                description = profile.bio.replace('\n', ' ').replace('\r', ' ')
                
                row = [
                    idx,                    # user_id: Sequential ID starting from 0
                    profile.name,           # name: Real name
                    profile.user_name,      # username: Username
                    user_char,              # user_char: Full persona (internal LLM use)
                    description             # description: Brief bio (external display)
                ]
                writer.writerow(row)
        
        logger.info(f"Saved {len(profiles)}  Twitter profiles to {file_path} (OASIS CSV format)")
    
    def _normalize_gender(self, gender: Optional[str]) -> str:
        """
        Standardize gender field to OASIS required English format
        
        OASIS requires: male, female, other
        """
        if not gender:
            return "other"
        
        gender_lower = gender.lower().strip()
        
        gender_map = {
            # Japanese
            "男性": "male",
            "女性": "female",
            "組織": "other",
            "その他": "other",
            # Chinese (legacy OASIS compatibility)
            "男": "male",
            "女": "female",
            "机构": "other",
            "其他": "other",
            # English
            "male": "male",
            "female": "female",
            "other": "other",
        }
        
        return gender_map.get(gender_lower, "other")
    
    def _save_reddit_json(self, profiles: List[OasisAgentProfile], file_path: str):
        """
        Save Reddit profiles as JSON
        
        Use format consistent with to_reddit_format() to ensure OASIS reads correctly.
        Must include user_id field, this is the key for OASIS agent_graph.get_agent() matching!
        
        Required fields:
        - user_id: User ID (integer, for matching poster_agent_id in initial_posts)
        - username: Username
        - name: Display name
        - bio: Bio
        - persona: Detailed Persona
        - age: Age (integer)
        - gender: "male", "female", or "other"
        - mbti: MBTI type
        - country: Country
        """
        data = []
        for idx, profile in enumerate(profiles):
            # Use format consistent with to_reddit_format()
            item = {
                "user_id": profile.user_id if profile.user_id is not None else idx,  # Key: must include user_id
                "username": profile.user_name,
                "name": profile.name,
                "bio": profile.bio[:150] if profile.bio else f"{profile.name}",
                "persona": profile.persona or f"{profile.name} is a participant in social discussions.",
                "karma": profile.karma if profile.karma else 1000,
                "created_at": profile.created_at,
                # OASIS required fields - ensure all have default values
                "age": profile.age if profile.age else 30,
                "gender": self._normalize_gender(profile.gender),
                "mbti": profile.mbti if profile.mbti else "ISTJ",
                "country": profile.country if profile.country else "China",
            }
            
            # Optional fields
            if profile.profession:
                item["profession"] = profile.profession
            if profile.interested_topics:
                item["interested_topics"] = profile.interested_topics
            
            data.append(item)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Saved {len(profiles)}  Reddit profiles to {file_path} (JSON format, includes user_id field)")
    
    # HR specialist definitions for automatic injection
    HR_SPECIALISTS = [
        {
            "name": "田中 美咲",
            "role": "キャリアアドバイザー（候補者の主要業界特化）",
            "role_category": "agent",
            "bio": "候補者の主要業界に精通したキャリアアドバイザー。その業界の採用動向・年収相場・キャリアパスに詳しく、業界内の人脈も豊富。",
            "persona": "田中美咲は候補者の主要業界（IT・Web・スタートアップ等）に特化したシニアキャリアアドバイザー。大手人材紹介会社で10年以上の実績を持ち、この業界の転職市場を熟知している。年間200名以上の転職支援実績があり、業界特有の選考傾向・年収レンジ・キャリアパスを踏まえた具体的な提案を行う。候補者のスキルセットと経験から転職先として可能性の高い具体的な企業名・ポジションを提案し、各社の社風や選考傾向もアドバイスする。カテゴリBのエージェントとして、候補者への業界特化型マッチング提案が行動の中心。LLMカスタマイズで候補者の実際の業界に合わせた専門知識が付与される。MBTI：ENFJ。",
            "age": 38, "gender": "female", "mbti": "ENFJ", "country": "日本",
            "topics": ["転職市場", "キャリア設計", "面接対策", "年収交渉", "業界動向"]
        },
        {
            "name": "木村 拓也",
            "role": "キャリアアドバイザー（隣接業界・異業種転職特化）",
            "role_category": "agent",
            "bio": "異業種転職・キャリアチェンジを専門とするキャリアアドバイザー。候補者のスキルが活かせる異業界のポジションを開拓する。",
            "persona": "木村拓也は異業種転職・キャリアチェンジを専門とするキャリアアドバイザー。候補者の現在の業界以外で、そのスキルセットが高く評価される隣接業界や新興領域を提案する。例えばIT業界の候補者にはコンサル・金融・メーカーDX部門など、スキルの転用可能性が高い領域を提示する。年間150名以上の異業種転職を成功させた実績から、業界をまたいだ年収交渉や、異業種面接での自己PR方法にも精通する。カテゴリBのエージェントとして、候補者が思いもよらなかった可能性を提示するのが強み。MBTI：ENTP。",
            "age": 35, "gender": "male", "mbti": "ENTP", "country": "日本",
            "topics": ["異業種転職", "キャリアチェンジ", "スキル転用", "新興業界", "DX人材"]
        },
        {
            "name": "山本 大輔",
            "role": "ヘッドハンター",
            "role_category": "agent",
            "bio": "エグゼクティブサーチ専門のヘッドハンター。CxO・VP・事業責任者クラスの人材を専門に扱い、非公開ポジションのマッチングに強い。",
            "persona": "山本大輔はエグゼクティブサーチファームのパートナーとして、CxO・VP・事業責任者クラスの人材紹介を専門とする。慶應義塾大学経済学部卒業後、外資系戦略コンサルを経て人材業界に転身。現在はビズリーチのダイレクトリクルーティング部門を率いる。年間50件以上のエグゼクティブ転職を成約させてきた。候補者の経営視点・リーダーシップ・事業インパクトを重視し、非公開ポジションとの適合性を見極める。カテゴリBのエージェントとして、ハイレイヤー市場での価値評価と最適ポジション提案が行動の中心。候補者の経歴から転職先として最も可能性の高い具体的な企業名を挙げ、各社の非公開ポジションや年収レンジ、選考難易度を踏まえたマッチング提案を行う。率直かつビジネスライクなコミュニケーションスタイル。MBTI：ENTJ。",
            "age": 45, "gender": "male", "mbti": "ENTJ", "country": "日本",
            "topics": ["エグゼクティブ転職", "経営人材", "非公開求人", "リーダーシップ評価", "報酬設計"]
        },
        {
            "name": "佐藤 健一",
            "role": "採用担当者",
            "role_category": "gatekeeper",
            "bio": "メガベンチャーの人事部採用チームリーダー。書類選考から一次面接まで年間1000名以上の候補者を評価してきた採用のプロフェッショナル。",
            "persona": "佐藤健一はメガベンチャーの人事部で採用チームリーダーを務める。明治大学法学部卒業後、パーソルキャリアで法人営業を経験し、事業会社の人事に転身。現在はサイバーエージェント系列企業で中途採用全般を統括。年間1000名以上の書類選考と300名以上の面接を実施してきた。カテゴリAのゲートキーパーとして、候補者を「採るか採らないか」判断する立場。書類選考では職務経歴の一貫性と成果の定量性を重視し、面接では論理的思考力とカルチャーフィットを見極める。不採用理由を明確に言語化できることが強み。MBTI：ISTJ。",
            "age": 35, "gender": "male", "mbti": "ISTJ", "country": "日本",
            "topics": ["書類選考", "面接設計", "採用基準", "カルチャーフィット", "オンボーディング"]
        },
        {
            "name": "鈴木 裕子",
            "role": "人事マネージャー",
            "role_category": "gatekeeper",
            "bio": "上場企業の人事部長（CHRO補佐）。組織開発・人事制度設計・採用戦略を統括し、経営層と連携して人材ポートフォリオを管理する。",
            "persona": "鈴木裕子は東証プライム上場企業の人事部長として、採用戦略・組織開発・人事制度を統括する。東京大学経済学部卒業後、野村総合研究所のHRコンサル部門で8年間勤務し、現在は事業会社の人事責任者。従業員2000名規模の組織の人材ポートフォリオを管理し、経営会議で採用計画を報告する立場。カテゴリAのゲートキーパーとして、組織全体の人材戦略との整合性、給与レンジとの適合性、既存チームとの補完性を判断する。オファー条件の最終決裁者でもある。冷静で分析的だが、人の可能性を信じるスタンス。MBTI：INFJ。",
            "age": 42, "gender": "female", "mbti": "INFJ", "country": "日本",
            "topics": ["組織開発", "人事制度", "採用戦略", "人材ポートフォリオ", "報酬制度"]
        },
        # 注意: 「同職種のTopプレイヤー」は HR_SPECIALISTS から削除。
        # generate_top_player_profile() で候補者の職種に合わせてLLM動的生成する。
        {
            "name": "中島 理恵",
            "role": "キャリアコーチ",
            "role_category": "agent",
            "bio": "国家資格キャリアコンサルタント。自己分析支援とキャリアビジョンの明確化を専門とし、候補者の内面的な動機と価値観を深掘りする。",
            "persona": "中島理恵は国家資格キャリアコンサルタント（GCDF-Japan）として独立し、年間150名以上のキャリア相談を受けている。上智大学文学部心理学科卒業後、企業内カウンセラーを経て独立。カテゴリBのコーチとして、候補者の自己分析支援・キャリアビジョンの明確化・転職の意思決定支援が行動の中心。スキルや経歴だけでなく、候補者の価値観・動機・ライフステージを総合的に捉えたキャリア設計を提案する。傾聴と問いかけを重視し、候補者自身が気づいていない強みを引き出すことを得意とする。MBTI：INFP。",
            "age": 44, "gender": "female", "mbti": "INFP", "country": "日本",
            "topics": ["キャリアデザイン", "自己分析", "ワークライフバランス", "キャリアチェンジ", "心理学"]
        },
        {
            "name": "渡辺 学",
            "role": "労働経済学者",
            "role_category": "researcher",
            "bio": "労働市場分析を専門とする経済学者。賃金動態・雇用流動性・人的資本理論の観点から候補者のキャリアを定量的に分析する。",
            "persona": "渡辺学は東京大学社会科学研究所の准教授として、労働経済学を専門に研究する。一橋大学経済学研究科博士課程修了、労働政策研究・研修機構（JILPT）を経て現職。カテゴリCの観察者として、候補者のキャリアを労働市場の需給バランス・賃金プレミアム・人的資本蓄積の観点から定量的に分析する。IT業界の転職市場データ、職種別の需給ギャップ、年齢別の転職成功率などのエビデンスに基づいた所見を提供する。感情論ではなくデータと理論に基づく冷徹な分析が特徴。MBTI：INTJ。",
            "age": 48, "gender": "male", "mbti": "INTJ", "country": "日本",
            "topics": ["労働経済学", "賃金動態", "雇用流動性", "人的資本理論", "労働市場分析"]
        },
        {
            "name": "小林 あかり",
            "role": "雇用ジャーナリスト",
            "role_category": "researcher",
            "bio": "雇用・働き方を専門とするジャーナリスト。転職市場のトレンド、企業の採用動向、キャリア形成の社会的文脈を報道する。",
            "persona": "小林あかりは日経ビジネスや東洋経済で雇用・キャリアをテーマに執筆するフリーランスジャーナリスト。早稲田大学政治経済学部卒業後、日経BP社で12年間の記者経験を積み独立。カテゴリCの観察者として、候補者のキャリアを転職市場のマクロトレンド、業界再編の文脈、社会構造の変化と照らし合わせて分析する。年間100社以上の取材経験から得た業界の裏事情や、表に出ない採用の実態にも精通する。客観的かつ読者視点での分析を重視し、個人のキャリアを社会的文脈に位置づけることを得意とする。MBTI：ENTP。",
            "age": 41, "gender": "female", "mbti": "ENTP", "country": "日本",
            "topics": ["雇用トレンド", "働き方改革", "転職市場動向", "企業採用戦略", "キャリア形成"]
        },
    ]

    def generate_hr_specialist_profiles(
        self,
        start_user_id: int,
        candidate_context: str = "",
        use_llm: bool = True,
        progress_callback: Optional[callable] = None
    ) -> List[OasisAgentProfile]:
        """
        Generate HR specialist agent profiles that don't exist in the knowledge graph.

        These are synthetic agents representing key HR stakeholders:
        - Career Advisors, Headhunters (Category B: Agent/Coach)
        - Recruiters, HR Managers (Category A: Gatekeeper)
        - Peer Professionals, Labor Economists, Journalists (Category C: Researcher)

        Args:
            start_user_id: Starting user_id (should be after existing entity profiles)
            candidate_context: Context about the candidate for LLM customization
            use_llm: Whether to use LLM to customize personas with candidate context
            progress_callback: Progress callback function

        Returns:
            List of HR specialist OasisAgentProfile
        """
        profiles = []
        total = len(self.HR_SPECIALISTS)

        for i, spec in enumerate(self.HR_SPECIALISTS):
            user_id = start_user_id + i

            persona = spec["persona"]

            # If LLM is available and we have candidate context, customize the persona
            if use_llm and candidate_context:
                try:
                    customized = self._customize_hr_specialist(spec, candidate_context)
                    if customized:
                        persona = customized
                except Exception as e:
                    logger.warning(f"Failed to customize HR specialist {spec['name']}: {e}")

            profile = OasisAgentProfile(
                user_id=user_id,
                user_name=self._generate_username(spec["name"]),
                name=spec["name"],
                bio=spec["bio"],
                persona=persona,
                age=spec["age"],
                gender=spec["gender"],
                mbti=spec["mbti"],
                country=spec["country"],
                profession=spec["role"],
                interested_topics=spec["topics"],
                source_entity_uuid=None,
                source_entity_type=spec["role_category"],
                role_category=spec["role_category"],
            )
            profiles.append(profile)

            # Print generated profile
            self._print_generated_profile(spec["name"], spec["role"], profile)

            if progress_callback:
                progress_callback(i + 1, total, f"HR Specialist {i+1}/{total}: {spec['name']}（{spec['role']}）")

            logger.info(f"[HR Specialist {i+1}/{total}] Generated: {spec['name']} ({spec['role']})")

        return profiles

    def _customize_hr_specialist(self, spec: dict, candidate_context: str) -> Optional[str]:
        """Use LLM to customize HR specialist persona based on candidate context"""
        # Inject HR trends knowledge
        knowledge_context = KnowledgeLoader.get_relevant_knowledge(
            candidate_context, injection_point="hr_specialist"
        )
        knowledge_section = f"""

## HRトレンド・市場データ（参考情報）
{knowledge_context}
""" if knowledge_context else ""

        prompt = f"""以下のHR専門家のペルソナを、候補者の情報を踏まえてカスタマイズしてください。
ベースとなる人物像はそのまま維持し、候補者に対する具体的な評価視点や質問を追加してください。

## HR専門家
名前: {spec['name']}
役割: {spec['role']}
ベースペルソナ: {spec['persona']}

## 候補者の概要
{candidate_context[:2000]}
{knowledge_section}

## カスタマイズの必須要素
1. 候補者に対する具体的な評価視点や質問を追加
2. 以下の会話テーマを自然に組み込むこと:
   - 候補者のキャリアの可能性と将来性（「この経験があれば○○方面に進める」等）
   - 業界の未来予測（「今後3-5年で○○スキルの需要がどう変わるか」「AI/DXが業界に与える影響」等）
   - キャリアパスの分岐シナリオ（「マネジメントに進むか専門特化するか」「海外展開の可能性」等）
   - 候補者が次に経験すべきこと（「足りないのは○○の経験」「次の転職では△△を重視すべき」等）
   - 他のエージェント（採用側・アドバイザー・元同僚等）の意見への反応と議論

カスタマイズされたペルソナを純粋なテキストで返してください（JSON不要、改行不要、1つの連続したテキスト）。"""

        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "あなたはHRキャリアシミュレーションのペルソナ設計者です。"},
                    {"role": "user", "content": prompt}
                ],
            )
            content = response.choices[0].message.content.strip()
            if len(content) > 100:  # Sanity check
                return content.replace('\n', ' ')
        except Exception as e:
            logger.warning(f"HR specialist customization failed: {e}")

        return None

    def generate_target_company_profiles(
        self,
        start_user_id: int,
        candidate_context: str,
        num_companies: int = 5,
        progress_callback: Optional[callable] = None
    ) -> List[OasisAgentProfile]:
        """
        Use LLM to infer target companies the candidate is likely to apply to,
        and generate hiring manager personas for each.

        Args:
            start_user_id: Starting user_id
            candidate_context: Candidate's resume/context for LLM inference
            num_companies: Number of target companies to generate
            progress_callback: Progress callback

        Returns:
            List of target company hiring manager OasisAgentProfile
        """
        if not candidate_context:
            logger.warning("No candidate context provided, skipping target company generation")
            return []

        # Inject job market knowledge
        knowledge_context = KnowledgeLoader.get_relevant_knowledge(
            candidate_context, injection_point="target_company"
        )
        knowledge_section = f"""

## 転職市場データ（参考情報）
{knowledge_context}
""" if knowledge_context else ""

        # Step 1: Ask LLM to suggest target companies
        prompt = f"""以下の候補者の経歴・スキルセットから、この候補者が転職先として応募する可能性が高い企業を{num_companies}社推薦してください。
過去に在籍した企業は除外してください。

## 候補者の概要
{candidate_context[:3000]}
{knowledge_section}
以下のJSON形式で返してください:
{{
    "companies": [
        {{
            "name": "企業名",
            "position": "想定ポジション名",
            "reason": "なぜこの企業が候補なのか（1文）",
            "hiring_manager_name": "採用面接官の名前（架空の日本人名）",
            "hiring_manager_role": "面接官の役職（例：プロダクト部門VP、エンジニアリングマネージャー等）",
            "hiring_manager_age": 年齢（整数）,
            "hiring_manager_gender": "male" or "female"
        }}
    ]
}}"""

        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "あなたは転職市場の専門家です。候補者の経歴から転職先候補企業を推薦してください。純粋なJSON形式で返してください。"},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
            )
            result = json.loads(response.choices[0].message.content)
            companies = result.get("companies", [])
        except Exception as e:
            logger.warning(f"Target company generation failed: {e}")
            return []

        # Step 2: Generate hiring manager profiles for each company
        profiles = []
        total = len(companies)

        for i, company in enumerate(companies):
            user_id = start_user_id + i
            company_name = company.get("name", f"企業{i+1}")
            position = company.get("position", "プロダクトマネージャー")
            reason = company.get("reason", "")
            manager_name = company.get("hiring_manager_name", f"面接官{i+1}")
            manager_role = company.get("hiring_manager_role", "採用責任者")
            manager_age = company.get("hiring_manager_age", 40)
            manager_gender = company.get("hiring_manager_gender", "male")

            # Generate detailed persona with LLM
            persona_prompt = f"""以下の転職先候補企業の採用面接官のペルソナを生成してください。

企業名: {company_name}
想定ポジション: {position}
この企業が候補である理由: {reason}
面接官名: {manager_name}
面接官役職: {manager_role}

候補者の概要:
{candidate_context[:1500]}

この面接官が候補者を面接する場面を想定し、以下を含む詳細なペルソナを1つの連続したテキスト（改行なし）で生成してください:
- {company_name}の事業内容と採用ニーズ
- {position}ポジションの具体的な職務要件と求めるスキル
- この面接官が候補者の経歴で評価するポイント
- この面接官が候補者に対して持つ懸念点や確認したい事項
- 面接での質問傾向と判断基準
- カテゴリA（ゲートキーパー）としての合否判断基準
- 【会話テーマ指示】他のエージェントとの対話で以下を積極的に議論すること: (1) このポジションでの候補者の成長可能性（「入社後1-2年でどこまで伸びるか」）, (2) {company_name}の業界での今後の展望と必要スキルの変化, (3) 候補者がこのポジションに就いた場合の3-5年後のキャリアパス, (4) 他のエージェントの評価への反応（「アドバイザーの見立てには同意するが、実際の面接では○○も確認したい」等）"""

            persona = f"{manager_name}は{company_name}の{manager_role}として、{position}ポジションの採用面接を担当する。{reason}"

            try:
                resp = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": "あなたはHRキャリアシミュレーションのペルソナ設計者です。"},
                        {"role": "user", "content": persona_prompt}
                    ],
                )
                content = resp.choices[0].message.content.strip()
                if len(content) > 100:
                    persona = content.replace('\n', ' ')
            except Exception as e:
                logger.warning(f"Target company persona generation failed for {company_name}: {e}")

            profile = OasisAgentProfile(
                user_id=user_id,
                user_name=self._generate_username(f"{company_name}_{manager_name}"),
                name=f"{manager_name}（{company_name}）",
                bio=f"{company_name}の{manager_role}。{position}ポジションの採用を担当。{reason}",
                persona=persona,
                age=manager_age,
                gender=manager_gender,
                mbti=random.choice(["ENTJ", "ISTJ", "INTJ", "ESTJ"]),
                country="日本",
                profession=f"{company_name} {manager_role}",
                interested_topics=[position, company_name, "採用", "面接", "組織開発"],
                source_entity_uuid=None,
                source_entity_type="gatekeeper",
                role_category="gatekeeper",
            )
            profiles.append(profile)

            self._print_generated_profile(f"{manager_name}（{company_name}）", "転職先候補", profile)

            if progress_callback:
                progress_callback(i + 1, total, f"Target Company {i+1}/{total}: {company_name}")

            logger.info(f"[Target Company {i+1}/{total}] Generated: {manager_name} at {company_name} for {position}")

        return profiles

    def generate_top_player_profile(
        self,
        start_user_id: int,
        candidate_context: str,
        progress_callback: Optional[callable] = None
    ) -> List[OasisAgentProfile]:
        """
        LLMで候補者の同職種におけるTopプレイヤーを自動生成する。
        候補者の職種を推定し、その職種で業界トップクラスの人材像を生成。
        カテゴリC（観察者/研究者）として、「卓越した人材とは何か」の視点から候補者を評価する。

        Args:
            start_user_id: Starting user_id
            candidate_context: Candidate's resume/context
            progress_callback: Progress callback

        Returns:
            List containing the top player OasisAgentProfile (1 agent)
        """
        if not candidate_context:
            logger.warning("No candidate context provided, skipping top player generation")
            return []

        # Inject industry knowledge
        knowledge_context = KnowledgeLoader.get_relevant_knowledge(
            candidate_context, injection_point="top_player"
        )
        knowledge_section = f"""

## 業界・スキル市場データ（参考情報）
{knowledge_context}
""" if knowledge_context else ""

        prompt = f"""以下の候補者の経歴から、この候補者と同じ職種における業界トップクラスの人材（Topプレイヤー）のペルソナを生成してください。

## 候補者の概要
{candidate_context[:3000]}
{knowledge_section}
## 指示
1. まず候補者の主要な職種を特定してください（例：プロダクトマネージャー、ソフトウェアエンジニア、データサイエンティスト、経営コンサルタント、営業、マーケター等）
2. その職種で日本国内トップクラスの実績を持つ架空の人物を1名生成してください
3. この人物は候補者と同じ職種の「最高峰」を体現する人物です

以下のJSON形式で返してください:
{{
    "candidate_profession": "候補者の職種（日本語）",
    "name": "トップレイヤーの名前（架空の日本人名）",
    "role": "同職種のTopプレイヤー（○○）← 括弧内に具体的な職種名",
    "bio": "この人物の概要（200字）。同職種で突出した実績を持つ人物としての紹介。候補者を評価する立場であることを明記",
    "persona": "詳細なペルソナ（2000字、改行なし、1つの連続テキスト）。以下を含むこと: (1) 経歴・学歴・所属企業の実績, (2) この職種で卓越している具体的なスキルと成果, (3) 業界での受賞歴・登壇実績・メディア露出等, (4) 同職種の候補者を評価する際の基準（技術力/思考力/リーダーシップ/ビジネスインパクト等）, (5) カテゴリCの観察者として候補者の相対的位置づけをどう見るか, (6) MBTIタイプとその行動パターン, (7) 【会話テーマ指示】他のエージェントとの対話で以下を積極的に議論すること: 業界の未来予測（今後3-5年でこの職種に求められるスキルがどう変わるか）、候補者が同職種トップに到達するために必要な経験と成長ステップ、AI/テクノロジーが業界に与える影響と新たに生まれるキャリア機会、他のエージェントの評価への具体的な反応（「アドバイザーの見立ては甘い、トップ層から見ると○○が足りない」等の率直なフィードバック）",
    "age": 年齢（整数、30-50の範囲）,
    "gender": "male" or "female",
    "mbti": "MBTIタイプ",
    "interested_topics": ["関心領域1", "関心領域2", "関心領域3", "関心領域4", "関心領域5"]
}}"""

        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "あなたはHRキャリアシミュレーションのペルソナ設計者です。候補者と同職種の業界トッププレイヤーを生成してください。純粋なJSON形式で返してください。"},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
            )
            result = json.loads(response.choices[0].message.content)
        except Exception as e:
            logger.warning(f"Top player generation failed: {e}")
            return []

        name = result.get("name", "山田 太郎")
        role = result.get("role", "同職種のTopプレイヤー")
        bio = result.get("bio", f"同職種のトップクラス人材。候補者のスキルレベルと業界内ポジションを評価する。")
        persona = result.get("persona", "").replace('\n', ' ')
        age = result.get("age", 38)
        gender = result.get("gender", "male")
        mbti = result.get("mbti", "INTJ")
        topics = result.get("interested_topics", ["業界動向", "スキル評価", "キャリア設計"])

        if len(persona) < 100:
            persona = f"{name}は{role}として活躍する業界トップクラスの人材。カテゴリCの観察者として、同職種の立場から候補者のスキルレベル・実績・成長性を客観的に評価する。"

        profile = OasisAgentProfile(
            user_id=start_user_id,
            user_name=self._generate_username(name),
            name=name,
            bio=bio,
            persona=persona,
            age=age,
            gender=gender,
            mbti=mbti,
            country="日本",
            profession=role,
            interested_topics=topics,
            source_entity_uuid=None,
            source_entity_type="researcher",
            role_category="researcher",
        )

        self._print_generated_profile(name, role, profile)

        if progress_callback:
            progress_callback(1, 1, f"Top Player: {name}（{role}）")

        logger.info(f"[Top Player] Generated: {name} ({role})")

        return [profile]

    # Keep old method names as aliases for backward compatibility
    def save_profiles_to_json(
        self,
        profiles: List[OasisAgentProfile],
        file_path: str,
        platform: str = "reddit"
    ):
        """[Deprecated] Please use save_profiles() method"""
        logger.warning("save_profiles_to_json is deprecated, please use save_profiles method")
        self.save_profiles(profiles, file_path, platform)

