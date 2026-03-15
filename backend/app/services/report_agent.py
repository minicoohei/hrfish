"""
Report Agent service
Uses LangChain + Zep to implement ReACT-based simulation report generation

Features:
1. Generate reports from simulation requirements and Zep graph data
2. Plan outline structure, then generate section by section
3. Each section uses ReACT multi-round thinking and reflection
4. Supports user conversation with autonomous retrieval tool calls
"""

import os
import json
import time
import re
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from ..config import Config
from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger
from .knowledge_loader import KnowledgeLoader
from .zep_tools import (
    ZepToolsService, 
    SearchResult, 
    InsightForgeResult, 
    PanoramaResult,
    InterviewResult
)

logger = get_logger('mirofish.report_agent')


class ReportLogger:
    """
    Report Agent detailed logger
    
    Generates agent_log.jsonl in the report folder, recording each detailed action.
    Each line is a complete JSON object with timestamp, action type, and details.
    """
    
    def __init__(self, report_id: str):
        """
        Initialize logger
        
        Args:
            report_id: Report ID for determining log file path
        """
        self.report_id = report_id
        self.log_file_path = os.path.join(
            Config.UPLOAD_FOLDER, 'reports', report_id, 'agent_log.jsonl'
        )
        self.start_time = datetime.now()
        self._ensure_log_file()
    
    def _ensure_log_file(self):
        """Ensure log file directory exists"""
        log_dir = os.path.dirname(self.log_file_path)
        os.makedirs(log_dir, exist_ok=True)
    
    def _get_elapsed_time(self) -> float:
        """Get elapsed time in seconds from start"""
        return (datetime.now() - self.start_time).total_seconds()
    
    def log(
        self, 
        action: str, 
        stage: str,
        details: Dict[str, Any],
        section_title: str = None,
        section_index: int = None
    ):
        """
        Write a log entry
        
        Args:
            action: Action type, e.g. 'start', 'tool_call', 'llm_response', 'section_complete', etc.
            stage: Current stage, e.g. 'planning', 'generating', 'completed'
            details: Details dict, untruncated
            section_title: Current section title (optional)
            section_index: Current section index (optional)
        """
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "elapsed_seconds": round(self._get_elapsed_time(), 2),
            "report_id": self.report_id,
            "action": action,
            "stage": stage,
            "section_title": section_title,
            "section_index": section_index,
            "details": details
        }
        
        # Append to JSONL file
        with open(self.log_file_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
    
    def log_start(self, simulation_id: str, graph_id: str, simulation_requirement: str):
        """Log report generation start"""
        self.log(
            action="report_start",
            stage="pending",
            details={
                "simulation_id": simulation_id,
                "graph_id": graph_id,
                "simulation_requirement": simulation_requirement,
                "message": "Report generation task started"
            }
        )
    
    def log_planning_start(self):
        """Log outline planning start"""
        self.log(
            action="planning_start",
            stage="planning",
            details={"message": "Starting report outline planning"}
        )
    
    def log_planning_context(self, context: Dict[str, Any]):
        """Log context obtained during planning"""
        self.log(
            action="planning_context",
            stage="planning",
            details={
                "message": "Obtained simulation context",
                "context": context
            }
        )
    
    def log_planning_complete(self, outline_dict: Dict[str, Any]):
        """Log outline planning complete"""
        self.log(
            action="planning_complete",
            stage="planning",
            details={
                "message": "Outline planning complete",
                "outline": outline_dict
            }
        )
    
    def log_section_start(self, section_title: str, section_index: int):
        """Log section generation start"""
        self.log(
            action="section_start",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={"message": f"Starting section generation: {section_title}"}
        )
    
    def log_react_thought(self, section_title: str, section_index: int, iteration: int, thought: str):
        """Log ReACT thinking process"""
        self.log(
            action="react_thought",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "thought": thought,
                "message": f"ReACT iteration {iteration} thinking"
            }
        )
    
    def log_tool_call(
        self, 
        section_title: str, 
        section_index: int,
        tool_name: str, 
        parameters: Dict[str, Any],
        iteration: int
    ):
        """Log tool call"""
        self.log(
            action="tool_call",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "tool_name": tool_name,
                "parameters": parameters,
                "message": f"Calling tool: {tool_name}"
            }
        )
    
    def log_tool_result(
        self,
        section_title: str,
        section_index: int,
        tool_name: str,
        result: str,
        iteration: int
    ):
        """Log tool call result (full content, untruncated)"""
        self.log(
            action="tool_result",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "tool_name": tool_name,
                "result": result,  # Full result, untruncated
                "result_length": len(result),
                "message": f"Tool {tool_name} returned result"
            }
        )
    
    def log_llm_response(
        self,
        section_title: str,
        section_index: int,
        response: str,
        iteration: int,
        has_tool_calls: bool,
        has_final_answer: bool
    ):
        """Log LLM response (full content, untruncated)"""
        self.log(
            action="llm_response",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "response": response,  # Full response, untruncated
                "response_length": len(response),
                "has_tool_calls": has_tool_calls,
                "has_final_answer": has_final_answer,
                "message": f"LLM response (tool_call: {has_tool_calls}, final_answer: {has_final_answer})"
            }
        )
    
    def log_section_content(
        self,
        section_title: str,
        section_index: int,
        content: str,
        tool_calls_count: int
    ):
        """Log section content generation complete (content only, not full section completion)"""
        self.log(
            action="section_content",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "content": content,  # Full content, untruncated
                "content_length": len(content),
                "tool_calls_count": tool_calls_count,
                "message": f"Section {section_title} content generation complete"
            }
        )
    
    def log_section_full_complete(
        self,
        section_title: str,
        section_index: int,
        full_content: str
    ):
        """
        Log section generation complete

        Frontend should listen to this log to determine if a section is truly complete and get full content
        """
        self.log(
            action="section_complete",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "content": full_content,
                "content_length": len(full_content),
                "message": f"Section {section_title} generation complete"
            }
        )
    
    def log_report_complete(self, total_sections: int, total_time_seconds: float):
        """Log report generation complete"""
        self.log(
            action="report_complete",
            stage="completed",
            details={
                "total_sections": total_sections,
                "total_time_seconds": round(total_time_seconds, 2),
                "message": "Report generation complete"
            }
        )
    
    def log_error(self, error_message: str, stage: str, section_title: str = None):
        """Log error"""
        self.log(
            action="error",
            stage=stage,
            section_title=section_title,
            section_index=None,
            details={
                "error": error_message,
                "message": f"Error occurred: {error_message}"
            }
        )


class ReportConsoleLogger:
    """
    Report Agent console logger
    
    Writes console-style logs (INFO, WARNING, etc.) to console_log.txt in the report folder.
    These logs differ from agent_log.jsonl - they are plain-text console output.
    """
    
    def __init__(self, report_id: str):
        """
        Initialize console logger
        
        Args:
            report_id: Report ID for determining log file path
        """
        self.report_id = report_id
        self.log_file_path = os.path.join(
            Config.UPLOAD_FOLDER, 'reports', report_id, 'console_log.txt'
        )
        self._ensure_log_file()
        self._file_handler = None
        self._setup_file_handler()
    
    def _ensure_log_file(self):
        """Ensure log file directory exists"""
        log_dir = os.path.dirname(self.log_file_path)
        os.makedirs(log_dir, exist_ok=True)
    
    def _setup_file_handler(self):
        """Set up file handler to write logs to file"""
        import logging
        
        # Create file handler
        self._file_handler = logging.FileHandler(
            self.log_file_path,
            mode='a',
            encoding='utf-8'
        )
        self._file_handler.setLevel(logging.INFO)
        
        # Use same concise format as console
        formatter = logging.Formatter(
            '[%(asctime)s] %(levelname)s: %(message)s',
            datefmt='%H:%M:%S'
        )
        self._file_handler.setFormatter(formatter)
        
        # Attach to report_agent related loggers
        loggers_to_attach = [
            'mirofish.report_agent',
            'mirofish.zep_tools',
        ]
        
        for logger_name in loggers_to_attach:
            target_logger = logging.getLogger(logger_name)
            # Avoid duplicate handlers
            if self._file_handler not in target_logger.handlers:
                target_logger.addHandler(self._file_handler)
    
    def close(self):
        """Close file handler and remove from loggers"""
        import logging
        
        if self._file_handler:
            loggers_to_detach = [
                'mirofish.report_agent',
                'mirofish.zep_tools',
            ]
            
            for logger_name in loggers_to_detach:
                target_logger = logging.getLogger(logger_name)
                if self._file_handler in target_logger.handlers:
                    target_logger.removeHandler(self._file_handler)
            
            self._file_handler.close()
            self._file_handler = None
    
    def __del__(self):
        """Ensure file handler is closed on destruction"""
        self.close()


class ReportStatus(str, Enum):
    """Report status"""
    PENDING = "pending"
    PLANNING = "planning"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ReportSection:
    """Report section"""
    title: str
    content: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "content": self.content
        }

    def to_markdown(self, level: int = 2) -> str:
        """Convert to Markdown format"""
        md = f"{'#' * level} {self.title}\n\n"
        if self.content:
            md += f"{self.content}\n\n"
        return md


@dataclass
class ReportOutline:
    """Report outline"""
    title: str
    summary: str
    sections: List[ReportSection]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "summary": self.summary,
            "sections": [s.to_dict() for s in self.sections]
        }
    
    def to_markdown(self) -> str:
        """Convert to Markdown format"""
        md = f"# {self.title}\n\n"
        md += f"> {self.summary}\n\n"
        for section in self.sections:
            md += section.to_markdown()
        return md


@dataclass
class Report:
    """Full report"""
    report_id: str
    simulation_id: str
    graph_id: str
    simulation_requirement: str
    status: ReportStatus
    outline: Optional[ReportOutline] = None
    markdown_content: str = ""
    created_at: str = ""
    completed_at: str = ""
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "simulation_id": self.simulation_id,
            "graph_id": self.graph_id,
            "simulation_requirement": self.simulation_requirement,
            "status": self.status.value,
            "outline": self.outline.to_dict() if self.outline else None,
            "markdown_content": self.markdown_content,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "error": self.error
        }


# ═══════════════════════════════════════════════════════════════
# Prompt template constants
# ═══════════════════════════════════════════════════════════════

# ── Tool descriptions ──

TOOL_DESC_INSIGHT_FORGE = """\
[Deep Insight Retrieval - Powerful retrieval tool]
This is our powerful retrieval function designed for deep analysis. It will:
1. Automatically decompose your question into multiple sub-questions
2. Retrieve information from the simulation graph across multiple dimensions
3. Integrate results from semantic search, entity analysis, and relationship chain tracking
4. Return the most comprehensive and in-depth retrieval content

[Use cases]
- Need to deeply analyze a topic
- Need to understand multiple aspects of an event
- Need rich material to support report sections

[Return content]
- Related facts (can be directly quoted)
- Core entity insights
- Relationship chain analysis"""

TOOL_DESC_PANORAMA_SEARCH = """\
[Breadth Search - Full picture view]
This tool retrieves the full picture of simulation results, especially suited for understanding event evolution. It will:
1. Get all related nodes and relationships
2. Distinguish between current valid facts and historical/expired facts
3. Help you understand how public opinion evolved

[Use cases]
- Need to understand the complete development of an event
- Need to compare opinion changes across different stages
- Need comprehensive entity and relationship information

[Return content]
- Current valid facts (latest simulation results)
- Historical/expired facts (evolution records)
- All involved entities"""

TOOL_DESC_QUICK_SEARCH = """\
[Simple Search - Quick retrieval]
Lightweight quick retrieval tool, suitable for simple, direct information queries.

[Use cases]
- Need to quickly find specific information
- Need to verify a fact
- Simple information retrieval

[Return content]
- List of facts most relevant to the query"""

TOOL_DESC_INTERVIEW_AGENTS = """\
[Deep Interview - Real agent interview (dual platform)]
Calls the OASIS simulation environment interview API to conduct real interviews with running simulation agents!
This is not LLM simulation but calls the real interview API to get original answers from simulation agents.
By default, interviews are conducted on both Twitter and Reddit platforms simultaneously for more comprehensive viewpoints.

Workflow:
1. Auto-read profile files to understand all simulation agents
2. Intelligently select agents most relevant to the interview topic (e.g., students, media, officials)
3. Auto-generate interview questions
4. Call /api/simulation/interview/batch API for real interviews on both platforms
5. Integrate all interview results for multi-perspective analysis

[Use cases]
- Need different role perspectives on events (How do students see it? Media? Officials?)
- Need to collect multi-party opinions and stances
- Need real answers from simulation agents (from OASIS simulation environment)
- Want to make the report more vivid with "interview transcripts"

[Return content]
- Interviewed agent identity information
- Each agent's interview responses on Twitter and Reddit platforms
- Key quotes (can be directly cited)
- Interview summary and viewpoint comparison

[Important] OASIS simulation environment must be running to use this feature!"""

TOOL_DESC_KNOWLEDGE_SEARCH = """\
[Industry Knowledge Search - Preset knowledge base]
Search curated industry knowledge including salary benchmarks, hiring trends,
skill demand data, career patterns, and industry overviews.

Use this tool when you need:
- Factual market data (salary ranges, hiring trends, industry growth rates)
- Industry-specific context beyond what simulation agents know
- Career pattern analysis and success factors
- Skill demand trends and future predictions

This searches locally curated Markdown files, NOT the Zep graph.
Results are pre-structured and may include data from external sources (news, job postings).

[Parameters]
- query: Search keywords (e.g., "IT業界 年収相場", "PM スキル需要")
- category: "industries", "job_market", "career_patterns", or "all" (default "all")"""

# ── Outline planning prompt ──

PLAN_SYSTEM_PROMPT = """\
あなたは「キャリア分析レポート」の作成専門家であり、シミュレーション世界の「神の視点」を持っています。シミュレーション内のすべてのステークホルダー（Agent）の評価、助言、意思決定を見通すことができます。

【核心理念】
私たちはキャリアシミュレーション世界を構築し、求職者の履歴書・職務経歴書を投入しました。各ステークホルダーが求職者をどう評価するかをシミュレーションした結果が、キャリアの可能性の予測です。

【あなたのタスク】
「キャリア分析レポート」を作成し、以下に回答してください：
1. 各ステークホルダーは求職者をどのように評価したか？
2. どのようなキャリアの可能性と適合ポジションがあるか？
3. リスキリング・スキル開発の方向性として何が示唆されるか？

【レポートの位置づけ】
- 各ステークホルダーからの評価予測に基づくキャリア分析レポート
- キャリアの可能性と適合ポジションの提示に焦点
- 各ステークホルダーの評価・コメントが核心的なエビデンス
- リスクと注意点も含めた包括的な分析

【推奨章節構成】
以下を参考に、2-5章で構成してください：
- キャリアパス シミュレーション結果（複数の将来シナリオの比較分析）
- 各ステークホルダーからの評価予測（各パスに対するリアクション）
- キャリアの可能性と適合ポジション
- リスキリング・スキル開発の方向性（必須 — 下記ガイドライン参照）
- リスクと注意点

【リスキリング方向性セクションのガイドライン】
このセクションは必ず含めてください。以下を網羅的に分析すること：
1. **現在のスキルギャップ分析**: シミュレーション結果から見えた、求職者の現スキルと各キャリアパスで求められるスキルの差分
2. **短期（1-2年）のリスキリング提案**: すぐ着手すべきスキル・資格（例: クラウド認定、データ分析、マネジメント研修等）
3. **中長期（3-5年）のスキル投資戦略**: キャリアの方向性に応じた専門性の深化・拡張の提案
4. **リスキリング手段の具体例**: オンライン講座（Coursera, Udemy等）、大学院・MBA、社内異動、副業・プロボノ、メンター探し等
5. **各キャリアパスとの対応**: 推奨パスごとに「このパスを選ぶなら○○のスキルが鍵」という形で対応づけること
6. **ROI観点**: リスキリング投資（時間・費用）と期待リターン（年収アップ、キャリアオプション拡大）の見通し

【重要】キャリアパス シミュレーション結果が提供されている場合、必ずレポートに含めてください。
各パスの年収推移、ライフイベント、リスク/リターンを比較し、ステークホルダーの視点から各パスを評価してください。

【章節数量制限】
- 最少2章、最多5章
- サブ章節は不要、各章で完結した内容を記述
- 内容は精緻で、核心的な分析結果に焦点を当てる

JSON形式でレポート大綱を出力してください：
{
    "title": "レポートタイトル",
    "summary": "レポート要約（一文で核心的な分析結果を概括）",
    "sections": [
        {
            "title": "章タイトル",
            "description": "章の内容説明"
        }
    ]
}

注意：sections配列は最少2個、最多5個の要素！"""

PLAN_USER_PROMPT_TEMPLATE = """\
【キャリア分析シナリオ】
求職者の履歴書・職務経歴書に基づくシミュレーション要件：{simulation_requirement}

【シミュレーション規模】
- 参加エンティティ数: {total_nodes}
- エンティティ間の関係数: {total_edges}
- エンティティタイプ分布: {entity_types}
- アクティブAgent数: {total_entities}

【シミュレーションで得られた評価・コメントのサンプル】
{related_facts_json}

{career_paths_section}

「神の視点」でこのキャリアシミュレーションを分析してください：
1. 各ステークホルダーは求職者をどのように評価したか？
2. どのようなキャリアの可能性と適合ポジションが示されたか？
3. リスキリング・スキル開発の方向性として何が示唆されるか？（スキルギャップ分析、短期/中長期の具体的なリスキリング提案、ROI観点を含む）
4. 各キャリアパスにおけるライフイベントの影響とリスク要因は何か？

分析結果に基づき、最適なレポート章節構成を設計してください。
キャリアパスシミュレーション結果がある場合、必ず「キャリアパス比較分析」章を含めてください。

【再確認】レポート章節数：最少2章、最多5章。内容は精緻で核心的な分析結果に焦点を当てること。"""

# ── Section generation prompt ──

SECTION_SYSTEM_PROMPT_TEMPLATE = """\
あなたは「キャリア分析レポート」の作成専門家であり、レポートの一つの章を執筆しています。

レポートタイトル: {report_title}
レポート要約: {report_summary}
キャリア分析シナリオ（シミュレーション要件）: {simulation_requirement}

現在執筆する章: {section_title}

═══════════════════════════════════════════════════════════════
【核心理念】
═══════════════════════════════════════════════════════════════

キャリアシミュレーションは、求職者の履歴書を元に各ステークホルダーが
どのように評価するかを予測するものです。シミュレーション内の各Agentの
評価・コメントが、実際のキャリア場面での反応の予測となります。

あなたのタスクは：
- 各ステークホルダーが求職者をどう評価したかを明らかにする
- キャリアの可能性と適合ポジションを提示する
- リスキリング・スキル開発の方向性を具体的に提示する（スキルギャップ分析→短期/中長期の提案→具体的手段→ROI見通し）
- リスクと注意点を指摘する

═══════════════════════════════════════════════════════════════
【最重要ルール - 必ず遵守】
═══════════════════════════════════════════════════════════════

1. 【必ずツールを呼び出してシミュレーション世界を観察すること】
   - 「神の視点」でキャリアシミュレーションを観察している
   - すべての内容はシミュレーション内で発生した各ステークホルダーの評価・コメントに基づくこと
   - 自身の知識でレポート内容を作成することは禁止
   - 各章で最低3回（最大5回）ツールを呼び出して観察すること

2. 【各ステークホルダーの評価・コメントを引用すること】
   - 各Agentの評価・コメントはキャリア分析の核心的エビデンス
   - レポート内で引用形式で表示すること。例：
     > "転職エージェントの評価：原文内容..."
   - これらの引用がシミュレーション予測の核心的証拠

3. 【キャリアパス シミュレーション結果を活用すること】
   - キャリアパスデータが提供されている場合、review_career_paths ツールで各パスに対する
     エージェント群の反応・評価を取得すること
   - web_career_research ツールで求人市場データやキャリア論を取得し、パスの実現可能性を裏付けること
   - ライフイベント（結婚、出産、介護、健康問題、住宅購入、地方移住、海外移住等）の
     キャリアへの影響を具体的に記述すること

4. 【言語の一貫性 - 引用内容はレポート言語に翻訳すること】
   - ツールが返す内容には英語や英日混在の表現が含まれる可能性がある
   - レポートは全て日本語で作成すること
   - ツールが返した英語や英日混在の内容を引用する場合、自然な日本語に翻訳してからレポートに記載すること
   - 翻訳時は原意を保ち、表現が自然で通じやすいことを確認
   - このルールは本文と引用ブロック（> 形式）の両方に適用

5. [Faithfully present prediction results]
   - Report content must reflect simulation results representing future predictions
   - Do not add information that does not exist in the simulation
   - If information is insufficient in some area, state it honestly

═══════════════════════════════════════════════════════════════
[Format specifications - extremely important!]
═══════════════════════════════════════════════════════════════

[One section = minimum content unit]
- Each section is the minimum content block of the report
- Do not use any Markdown headings (#, ##, ###, #### etc.) within sections
- Do not add section heading at the beginning of content
- Section headings are added automatically by the system; write only body text
- Use **bold**, paragraphs, quotes, and lists to organize content, but no headings

[Correct example]
```
This section analyzes the public opinion propagation. Through deep analysis of simulation data, we found...

**Initial trigger phase**

Weibo served as the primary source, bearing the core function of initial information release:

> "Weibo contributed 68% of initial voice volume..."

**Sentiment amplification phase**

The Douyin platform further amplified the event impact:

- Strong visual impact
- High emotional resonance
```

[Wrong example]
```
## Executive Summary   <- Wrong! Do not add any headings
### I. Initial Phase   <- Wrong! Do not use ### for subsections
#### 1.1 Detailed Analysis <- Wrong! Do not use #### for details

This section analyzes...
```

═══════════════════════════════════════════════════════════════
[Available retrieval tools] (call 3-5 times per section)
═══════════════════════════════════════════════════════════════

{tools_description}

[Tool usage tips - mix different tools, do not use only one]
- insight_forge: Deep insight analysis, auto-decomposes questions and retrieves facts/relations across dimensions
- panorama_search: Wide-angle panoramic search, understand full picture, timeline, and evolution
- quick_search: Quick verification of specific information points
- interview_agents: Interview simulation agents, get first-person perspectives and real reactions from different roles

═══════════════════════════════════════════════════════════════
[Workflow]
═══════════════════════════════════════════════════════════════

Each reply, you can only do ONE of the following (not both):

Option A - Call a tool:
Output your reasoning, then call a tool using this format:
<tool_call>
{{"name": "tool_name", "parameters": {{"param_name": "param_value"}}}}
</tool_call>
The system will execute the tool and return the result. You cannot write tool results yourself.

Option B - Output final content:
When you have gathered enough information via tools, output section content starting with "Final Answer:".

Strictly prohibited:
- Do not include both a tool call and Final Answer in one reply
- Do not fabricate tool results (Observation); all tool results are injected by the system
- Call at most one tool per reply

═══════════════════════════════════════════════════════════════
[Section content requirements]
═══════════════════════════════════════════════════════════════

1. Content must be based on simulation data retrieved by tools
2. Extensively quote original text to demonstrate simulation effects
3. Use Markdown format (but no headings):
   - Use **bold text** for emphasis (instead of sub-headings)
   - Use lists (- or 1.2.3.) to organize key points
   - Use blank lines to separate paragraphs
   - Do not use #, ##, ###, #### or any heading syntax
4. [Quote format - must be standalone paragraph]
   Quotes must be standalone paragraphs with blank lines before and after:

   Correct format:
   ```
   The school's response was considered lacking in substance.

   > "The school's response pattern appeared rigid and slow in the fast-changing social media environment."

   This assessment reflects widespread public dissatisfaction.
   ```

   Wrong format:
   ```
   The school's response was lacking. > "The response pattern..." This reflects...
   ```
5. Maintain logical coherence with other sections
6. [Avoid repetition] Carefully read completed sections below; do not repeat the same information
7. [Reminder] Do not add any headings! Use **bold** instead of sub-headings"""

SECTION_USER_PROMPT_TEMPLATE = """\
Completed section content (read carefully to avoid repetition):
{previous_content}

═══════════════════════════════════════════════════════════════
[Current task] Write section: {section_title}
═══════════════════════════════════════════════════════════════

[Important reminders]
1. Carefully read completed sections above to avoid repeating content!
2. Must call tools to retrieve simulation data before starting
3. Mix different tools; do not use only one type
4. Report content must come from retrieval results, not your own knowledge

[Format warning - must comply]
- Do not write any headings (#, ##, ###, #### are all prohibited)
- Do not write "{section_title}" as the opening
- Section headings are added automatically by the system
- Write body text directly, use **bold** instead of sub-headings

Please begin:
1. First think (Thought) about what information this section needs
2. Then call tools (Action) to retrieve simulation data
3. After collecting enough information, output Final Answer (body text only, no headings)"""

# ── ReACT loop message templates ──

REACT_OBSERVATION_TEMPLATE = """\
Observation (retrieval results):

=== Tool {tool_name} returned ===
{result}

═══════════════════════════════════════════════════════════════
Tools called {tool_calls_count}/{max_tool_calls} times (used: {used_tools_str}){unused_hint}
- If information is sufficient: output section content starting with "Final Answer:" (must quote the above text)
- If more information is needed: call a tool to continue retrieval
═══════════════════════════════════════════════════════════════"""

REACT_INSUFFICIENT_TOOLS_MSG = (
    "[Note] You have only called tools {tool_calls_count} times; at least {min_tool_calls} calls are required."
    "Please call more tools to get simulation data before outputting Final Answer.{unused_hint}"
)

REACT_INSUFFICIENT_TOOLS_MSG_ALT = (
    "Currently only {tool_calls_count} tool calls made; at least {min_tool_calls} required."
    "Please call tools to get simulation data.{unused_hint}"
)

REACT_TOOL_LIMIT_MSG = (
    "Tool call limit reached ({tool_calls_count}/{max_tool_calls}); no more tool calls allowed."
    'Please immediately output section content starting with "Final Answer:" based on gathered information.'
)

REACT_UNUSED_TOOLS_HINT = "\n💡 You haven't used: {unused_list}. Try different tools for multi-angle information"

REACT_FORCE_FINAL_MSG = "Tool call limit reached. Please output Final Answer: and generate section content directly."

# ── Chat prompt ──

CHAT_SYSTEM_PROMPT_TEMPLATE = """\
You are a concise and efficient simulation prediction assistant.

[Background]
Prediction conditions: {simulation_requirement}

[Generated analysis report]
{report_content}

[Rules]
1. Prioritize answering based on the above report content
2. Answer directly, avoid lengthy reasoning
3. Only call tools for more data when report content is insufficient
4. Answers should be concise, clear, and well-organized

[Available tools] (use only when needed, max 1-2 calls)
{tools_description}

[Tool call format]
<tool_call>
{{"name": "tool_name", "parameters": {{"param_name": "param_value"}}}}
</tool_call>

[Answer style]
- Concise and direct, no lengthy explanations
- Use > format to quote key content
- Give conclusions first, then explain reasons"""

CHAT_OBSERVATION_SUFFIX = "\n\nPlease answer concisely."


# ═══════════════════════════════════════════════════════════════
# ReportAgent main class
# ═══════════════════════════════════════════════════════════════


class ReportAgent:
    """
    Report Agent - simulation report generation agent

    Uses ReACT (Reasoning + Acting) pattern:
    1. Planning phase: analyze simulation requirements, plan report structure
    2. Generation phase: generate content section by section, each section can call tools multiple times
    3. Reflection phase: check content completeness and accuracy
    """
    
    # Max tool calls per section
    MAX_TOOL_CALLS_PER_SECTION = 5
    
    # Max reflection rounds
    MAX_REFLECTION_ROUNDS = 3
    
    # Max tool calls per chat
    MAX_TOOL_CALLS_PER_CHAT = 2
    
    def __init__(
        self,
        graph_id: str,
        simulation_id: str,
        simulation_requirement: str,
        llm_client: Optional[LLMClient] = None,
        zep_tools: Optional[ZepToolsService] = None,
        career_paths_context: str = "",
        career_paths_data: Optional[dict] = None,
    ):
        """
        Initialize Report Agent

        Args:
            graph_id: Graph ID
            simulation_id: Simulation ID
            simulation_requirement: Simulation requirement description
            llm_client: LLM client (optional)
            zep_tools: Zep tools service (optional)
            career_paths_context: Formatted career path simulation results for LLM context
            career_paths_data: Raw career path simulation data (for frontend)
        """
        self.graph_id = graph_id
        self.simulation_id = simulation_id
        self.simulation_requirement = simulation_requirement
        self.career_paths_context = career_paths_context
        self.career_paths_data = career_paths_data
        
        self.llm = llm_client or LLMClient(use_chat_model=True)  # レポート生成もチャットモデル（gpt-5.4）を使用
        self.chat_llm = self.llm  # インタラクティブチャットも同一モデル
        self.zep_tools = zep_tools or ZepToolsService()
        
        # Tool definitions
        self.tools = self._define_tools()
        
        # Logger (initialized in generate_report)
        self.report_logger: Optional[ReportLogger] = None
        # Console logger (initialized in generate_report)
        self.console_logger: Optional[ReportConsoleLogger] = None
        
        logger.info(f"ReportAgent initialized: graph_id={graph_id}, simulation_id={simulation_id}")
    
    def _define_tools(self) -> Dict[str, Dict[str, Any]]:
        """Define available tools"""
        return {
            "insight_forge": {
                "name": "insight_forge",
                "description": TOOL_DESC_INSIGHT_FORGE,
                "parameters": {
                    "query": "The question or topic you want to analyze in depth",
                    "report_context": "Current report section context (optional, helps generate more precise sub-questions)"
                }
            },
            "panorama_search": {
                "name": "panorama_search",
                "description": TOOL_DESC_PANORAMA_SEARCH,
                "parameters": {
                    "query": "Search query for relevance ranking",
                    "include_expired": "Whether to include expired/historical content (default True)"
                }
            },
            "quick_search": {
                "name": "quick_search",
                "description": TOOL_DESC_QUICK_SEARCH,
                "parameters": {
                    "query": "Search query string",
                    "limit": "Number of results (optional, default 10)"
                }
            },
            "interview_agents": {
                "name": "interview_agents",
                "description": TOOL_DESC_INTERVIEW_AGENTS,
                "parameters": {
                    "interview_topic": "Interview topic or requirement description",
                    "max_agents": "Max number of agents to interview (optional, default 5, max 10)"
                }
            },
            "knowledge_search": {
                "name": "knowledge_search",
                "description": TOOL_DESC_KNOWLEDGE_SEARCH,
                "parameters": {
                    "query": "Search query for industry knowledge (e.g., 'IT業界の年収相場', 'PM職の市場トレンド')",
                    "category": "Knowledge category: 'industries', 'job_market', 'career_patterns', or 'all' (default 'all')"
                }
            },
            "web_career_research": {
                "name": "web_career_research",
                "description": (
                    "Web検索で最新の求人情報、キャリア論、業界トレンド、転職市場データを収集する。"
                    "キャリアパスの実現可能性を外部データで裏付ける。"
                ),
                "parameters": {
                    "query": "検索クエリ（例: 'ITエンジニア 年収 転職市場 2026', 'フリーランス 独立 成功率'）",
                    "focus": "検索の焦点: 'job_market'(求人・年収), 'career_theory'(キャリア論), 'industry'(業界動向), 'general'(全般)"
                }
            },
            "review_career_paths": {
                "name": "review_career_paths",
                "description": (
                    "キャリアパス シミュレーション結果に対して、シミュレーション内のエージェント群（転職エージェント、HR担当者、"
                    "業界の専門家、友人など）にレビューを依頼する。各エージェントがキャリアパスの実現可能性、リスク、"
                    "ライフイベントの影響について意見を述べる。"
                ),
                "parameters": {
                    "path_label": "レビュー対象のキャリアパスのラベル（例: '現職で昇進', '起業', '海外移住'）。'all' で全パス概要レビュー",
                    "focus": "レビューの焦点（例: '実現可能性', 'リスク', 'ライフイベント影響', '市場需要'）。省略可"
                }
            }
        }
    
    def _execute_tool(self, tool_name: str, parameters: Dict[str, Any], report_context: str = "") -> str:
        """
        Execute tool call
        
        Args:
            tool_name: Tool name
            parameters: Tool parameters
            report_context: Report context (for InsightForge)
            
        Returns:
            Tool execution result (text format)
        """
        logger.info(f"Executing tool: {tool_name}, params: {parameters}")
        
        try:
            if tool_name == "insight_forge":
                query = parameters.get("query", "")
                ctx = parameters.get("report_context", "") or report_context
                result = self.zep_tools.insight_forge(
                    graph_id=self.graph_id,
                    query=query,
                    simulation_requirement=self.simulation_requirement,
                    report_context=ctx
                )
                return result.to_text()
            
            elif tool_name == "panorama_search":
                # Breadth search - get full picture
                query = parameters.get("query", "")
                include_expired = parameters.get("include_expired", True)
                if isinstance(include_expired, str):
                    include_expired = include_expired.lower() in ['true', '1', 'yes']
                result = self.zep_tools.panorama_search(
                    graph_id=self.graph_id,
                    query=query,
                    include_expired=include_expired
                )
                return result.to_text()
            
            elif tool_name == "quick_search":
                # Simple search - quick retrieval
                query = parameters.get("query", "")
                limit = parameters.get("limit", 10)
                if isinstance(limit, str):
                    limit = int(limit)
                result = self.zep_tools.quick_search(
                    graph_id=self.graph_id,
                    query=query,
                    limit=limit
                )
                return result.to_text()
            
            elif tool_name == "interview_agents":
                # Deep interview - call real OASIS interview API for simulation agent responses (dual platform)
                interview_topic = parameters.get("interview_topic", parameters.get("query", ""))
                max_agents = parameters.get("max_agents", 5)
                if isinstance(max_agents, str):
                    max_agents = int(max_agents)
                max_agents = min(max_agents, 10)
                result = self.zep_tools.interview_agents(
                    simulation_id=self.simulation_id,
                    interview_requirement=interview_topic,
                    simulation_requirement=self.simulation_requirement,
                    max_agents=max_agents
                )
                return result.to_text()

            elif tool_name == "knowledge_search":
                query = parameters.get("query", "")
                category = parameters.get("category", "all")
                return KnowledgeLoader.search_knowledge(query=query, category=category)

            elif tool_name == "web_career_research":
                return self._web_career_research(
                    query=parameters.get("query", ""),
                    focus=parameters.get("focus", "general"),
                )

            elif tool_name == "review_career_paths":
                return self._review_career_paths(
                    path_label=parameters.get("path_label", "all"),
                    focus=parameters.get("focus", ""),
                )

            # ========== Backward-compatible old tools (internally redirected to new tools) ==========
            
            elif tool_name == "search_graph":
                # Redirect to quick_search
                logger.info("search_graph redirected to quick_search")
                return self._execute_tool("quick_search", parameters, report_context)
            
            elif tool_name == "get_graph_statistics":
                result = self.zep_tools.get_graph_statistics(self.graph_id)
                return json.dumps(result, ensure_ascii=False, indent=2)
            
            elif tool_name == "get_entity_summary":
                entity_name = parameters.get("entity_name", "")
                result = self.zep_tools.get_entity_summary(
                    graph_id=self.graph_id,
                    entity_name=entity_name
                )
                return json.dumps(result, ensure_ascii=False, indent=2)
            
            elif tool_name == "get_simulation_context":
                # Redirect to insight_forge since it is more powerful
                logger.info("get_simulation_context redirected to insight_forge")
                query = parameters.get("query", self.simulation_requirement)
                return self._execute_tool("insight_forge", {"query": query}, report_context)
            
            elif tool_name == "get_entities_by_type":
                entity_type = parameters.get("entity_type", "")
                nodes = self.zep_tools.get_entities_by_type(
                    graph_id=self.graph_id,
                    entity_type=entity_type
                )
                result = [n.to_dict() for n in nodes]
                return json.dumps(result, ensure_ascii=False, indent=2)
            
            else:
                return f"Unknown tool: {tool_name}. Please use one of: insight_forge, panorama_search, quick_search"
                
        except Exception as e:
            logger.error(f"Tool execution failed: {tool_name}, error: {str(e)}")
            return f"Tool execution failed: {str(e)}"
    
    # Valid tool name set for bare JSON fallback parsing validation
    VALID_TOOL_NAMES = {"insight_forge", "panorama_search", "quick_search", "interview_agents", "knowledge_search"}

    def _parse_tool_calls(self, response: str) -> List[Dict[str, Any]]:
        """
        Parse tool calls from LLM response

        Supported formats (by priority):
        1. <tool_call>{"name": "tool_name", "parameters": {...}}</tool_call>
        2. Bare JSON (response body or single line is a tool call JSON)
        """
        tool_calls = []

        # Format 1: XML style (standard format)
        xml_pattern = r'<tool_call>\s*(\{.*?\})\s*</tool_call>'
        for match in re.finditer(xml_pattern, response, re.DOTALL):
            try:
                call_data = json.loads(match.group(1))
                tool_calls.append(call_data)
            except json.JSONDecodeError:
                pass

        if tool_calls:
            return tool_calls

        # Format 2: Fallback - LLM outputs bare JSON (without <tool_call> tags)
        # Only try if format 1 did not match, to avoid false matches in body text
        stripped = response.strip()
        if stripped.startswith('{') and stripped.endswith('}'):
            try:
                call_data = json.loads(stripped)
                if self._is_valid_tool_call(call_data):
                    tool_calls.append(call_data)
                    return tool_calls
            except json.JSONDecodeError:
                pass

        # Response may contain reasoning text + bare JSON; try extracting last JSON object
        json_pattern = r'(\{"(?:name|tool)"\s*:.*?\})\s*$'
        match = re.search(json_pattern, stripped, re.DOTALL)
        if match:
            try:
                call_data = json.loads(match.group(1))
                if self._is_valid_tool_call(call_data):
                    tool_calls.append(call_data)
            except json.JSONDecodeError:
                pass

        return tool_calls

    def _is_valid_tool_call(self, data: dict) -> bool:
        """Validate whether parsed JSON is a valid tool call"""
        # Support both {"name": ..., "parameters": ...} and {"tool": ..., "params": ...} key formats
        tool_name = data.get("name") or data.get("tool")
        if tool_name and tool_name in self.VALID_TOOL_NAMES:
            # Normalize keys to name / parameters
            if "tool" in data:
                data["name"] = data.pop("tool")
            if "params" in data and "parameters" not in data:
                data["parameters"] = data.pop("params")
            return True
        return False
    
    def _web_career_research(self, query: str, focus: str = "general") -> str:
        """
        Search the web for job market data, career theories, and industry trends
        using Tavily API via ExternalDataFetcher.
        """
        from .external_data_fetcher import ExternalDataFetcher
        fetcher = ExternalDataFetcher()

        if not fetcher.is_available:
            return "Web検索APIが利用できません（TAVILY_API_KEY未設定）。プリセット知識のみ利用可能です。"

        try:
            if focus == "job_market":
                results = fetcher.search(query, search_depth="advanced", max_results=5, include_answer=True)
            elif focus == "career_theory":
                results = fetcher.search(
                    f"{query} キャリア理論 キャリアデザイン 研究",
                    search_depth="advanced", max_results=5, include_answer=True
                )
            elif focus == "industry":
                results = fetcher.search(query, topic="news", max_results=5, include_answer=True)
            else:
                results = fetcher.search(query, search_depth="advanced", max_results=5, include_answer=True)

            if not results:
                return f"「{query}」に関するWeb検索結果が見つかりませんでした。"

            lines = [f"【Web検索結果: {query}】\n"]
            for r in results:
                if r["type"] == "answer":
                    lines.append(f"■ AI要約: {r['content']}\n")
                else:
                    lines.append(f"・{r['title']}")
                    if r.get("content"):
                        lines.append(f"  {r['content'][:300]}")
                    lines.append("")

            return "\n".join(lines)

        except Exception as e:
            logger.warning(f"Web career research failed: {e}")
            return f"Web検索に失敗しました: {e}"

    def _review_career_paths(self, path_label: str = "all", focus: str = "") -> str:
        """
        Have OASIS agents review career path simulation results.
        Interviews agents with career path context for their professional opinions.
        """
        if not self.career_paths_data or not self.career_paths_data.get("paths"):
            return "キャリアパス シミュレーション結果がありません。"

        paths = self.career_paths_data["paths"]

        # Build path summary for agent context
        if path_label.lower() == "all":
            path_desc_lines = []
            for i, p in enumerate(paths, 1):
                events_text = ""
                if p.get("key_events"):
                    events_text = "、".join(
                        f'{e["age"]}歳:{e["event"]}' for e in p["key_events"][:3]
                    )
                path_desc_lines.append(
                    f"パス{i}「{p['path_label']}」: 最終年収{p.get('final_salary', 0)}万円, "
                    f"満足度{p.get('final_satisfaction', 0)}, スコア{p.get('score', 0)}"
                    + (f" [主要イベント: {events_text}]" if events_text else "")
                )
            path_summary = "\n".join(path_desc_lines)
        else:
            # Find specific path
            target = next((p for p in paths if path_label in p.get("path_label", "")), None)
            if not target:
                return f"パス「{path_label}」が見つかりません。利用可能: {', '.join(p['path_label'] for p in paths)}"
            events_text = "\n".join(
                f"  - {e['age']}歳: {e['event']}" for e in target.get("key_events", [])
            )
            path_summary = (
                f"パス「{target['path_label']}」\n"
                f"最終役職: {target.get('final_role', '?')} @ {target.get('final_employer', '?')}\n"
                f"最終年収: {target.get('final_salary', 0)}万円 (ピーク: {target.get('peak_salary', 0)}万円)\n"
                f"資産: {target.get('final_cash_buffer', 0)}万円\n"
                f"ストレス: {target.get('avg_stress', 0)} / 満足度: {target.get('final_satisfaction', 0)}\n"
                f"ライフイベント:\n{events_text}"
            )

        focus_text = f"特に「{focus}」の観点から" if focus else ""
        interview_topic = (
            f"以下のキャリアパス シミュレーション結果について、{focus_text}"
            f"あなたの専門的な立場から率直に評価・コメントしてください。\n"
            f"実現可能性、リスク、ライフイベントの影響、市場環境を踏まえて意見を述べてください。\n\n"
            f"【キャリアパス シミュレーション結果】\n{path_summary}"
        )

        # Use existing interview_agents tool to get agent reactions
        try:
            result = self.zep_tools.interview_agents(
                simulation_id=self.simulation_id,
                interview_requirement=interview_topic,
                simulation_requirement=self.simulation_requirement,
                max_agents=6
            )
            return f"【エージェント群によるキャリアパスレビュー】\n{result.to_text()}"
        except Exception as e:
            logger.warning(f"Career path review via agents failed: {e}")
            return f"エージェントレビューに失敗しました: {e}"

    def _get_tools_description(self) -> str:
        """Generate tool description text"""
        desc_parts = ["Available tools:"]
        for name, tool in self.tools.items():
            params_desc = ", ".join([f"{k}: {v}" for k, v in tool["parameters"].items()])
            desc_parts.append(f"- {name}: {tool['description']}")
            if params_desc:
                desc_parts.append(f"  Parameters: {params_desc}")
        return "\n".join(desc_parts)
    
    def plan_outline(
        self, 
        progress_callback: Optional[Callable] = None
    ) -> ReportOutline:
        """
        Plan report outline
        
        Use LLM to analyze simulation requirements and plan report structure
        
        Args:
            progress_callback: Progress callback function
            
        Returns:
            ReportOutline: Report outline
        """
        logger.info("Planning report outline...")
        
        if progress_callback:
            progress_callback("planning", 0, "Analyzing simulation requirements...")
        
        # First get simulation context
        context = self.zep_tools.get_simulation_context(
            graph_id=self.graph_id,
            simulation_requirement=self.simulation_requirement
        )
        
        if progress_callback:
            progress_callback("planning", 30, "Generating report outline...")
        
        system_prompt = PLAN_SYSTEM_PROMPT
        # Build career paths section for the prompt
        career_paths_section = ""
        if self.career_paths_context:
            career_paths_section = f"【キャリアパス シミュレーション結果（並列実行・ライフイベント付き）】\n{self.career_paths_context}"

        user_prompt = PLAN_USER_PROMPT_TEMPLATE.format(
            simulation_requirement=self.simulation_requirement,
            total_nodes=context.get('graph_statistics', {}).get('total_nodes', 0),
            total_edges=context.get('graph_statistics', {}).get('total_edges', 0),
            entity_types=list(context.get('graph_statistics', {}).get('entity_types', {}).keys()),
            total_entities=context.get('total_entities', 0),
            related_facts_json=json.dumps(context.get('related_facts', [])[:10], ensure_ascii=False, indent=2),
            career_paths_section=career_paths_section,
        )

        try:
            response = self.llm.chat_json(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3
            )
            
            if progress_callback:
                progress_callback("planning", 80, "Parsing outline structure...")
            
            # Parse outline
            sections = []
            for section_data in response.get("sections", []):
                sections.append(ReportSection(
                    title=section_data.get("title", ""),
                    content=""
                ))
            
            outline = ReportOutline(
                title=response.get("title", "Simulation Analysis Report"),
                summary=response.get("summary", ""),
                sections=sections
            )
            
            if progress_callback:
                progress_callback("planning", 100, "Outline planning complete")
            
            logger.info(f"Outline planning complete: {len(sections)} sections")
            return outline
            
        except Exception as e:
            logger.error(f"Outline planning failed: {str(e)}")
            # Return default outline (3 sections as fallback)
            return ReportOutline(
                title="Future Prediction Report",
                summary="Future trends and risk analysis based on simulation predictions",
                sections=[
                    ReportSection(title="Prediction Scenarios and Key Findings"),
                    ReportSection(title="Population Behavior Prediction Analysis"),
                    ReportSection(title="Trend Outlook and Risk Alerts")
                ]
            )
    
    def _generate_section_react(
        self, 
        section: ReportSection,
        outline: ReportOutline,
        previous_sections: List[str],
        progress_callback: Optional[Callable] = None,
        section_index: int = 0
    ) -> str:
        """
        Generate single section content using ReACT pattern
        
        ReACT loop:
        1. Thought - Analyze what information is needed
        2. Action - Call tools to get information
        3. Observation - Analyze tool return results
        4. Repeat until information is sufficient or max iterations reached
        5. Final Answer - Generate section content
        
        Args:
            section: Section to generate
            outline: Full outline
            previous_sections: Previous section content (for coherence)
            progress_callback: Progress callback
            section_index: Section index (for logging)
            
        Returns:
            Section content (Markdown format)
        """
        logger.info(f"ReACT generating section: {section.title}")
        
        # Log section start
        if self.report_logger:
            self.report_logger.log_section_start(section.title, section_index)
        
        # Build career paths addendum for section context
        career_paths_addendum = ""
        if self.career_paths_context:
            career_paths_addendum = (
                "\n\n═══════════════════════════════════════════════════════════════\n"
                "【キャリアパス シミュレーション結果（参考データ）】\n"
                "═══════════════════════════════════════════════════════════════\n"
                f"{self.career_paths_context}\n"
                "\n上記のキャリアパスデータは並列シミュレーションで得られた結果です。\n"
                "各パスのライフイベント、年収推移、ストレス・満足度を活用して章を執筆してください。\n"
            )

        system_prompt = SECTION_SYSTEM_PROMPT_TEMPLATE.format(
            report_title=outline.title,
            report_summary=outline.summary,
            simulation_requirement=self.simulation_requirement,
            section_title=section.title,
            tools_description=self._get_tools_description(),
        ) + career_paths_addendum

        # Build user prompt - pass max 4000 chars per completed section
        if previous_sections:
            previous_parts = []
            for sec in previous_sections:
                # Max 4000 chars per section
                truncated = sec[:4000] + "..." if len(sec) > 4000 else sec
                previous_parts.append(truncated)
            previous_content = "\n\n---\n\n".join(previous_parts)
        else:
            previous_content = "(This is the first section)"
        
        user_prompt = SECTION_USER_PROMPT_TEMPLATE.format(
            previous_content=previous_content,
            section_title=section.title,
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        # ReACT loop
        tool_calls_count = 0
        max_iterations = 5  # Max iteration rounds
        min_tool_calls = 3  # Min tool calls required
        conflict_retries = 0  # Consecutive conflict count (tool call + Final Answer simultaneously)
        used_tools = set()  # Track used tool names
        all_tools = {"insight_forge", "panorama_search", "quick_search", "interview_agents", "knowledge_search", "web_career_research", "review_career_paths"}

        # Report context for InsightForge sub-question generation
        report_context = f"Section title: {section.title}\nSimulation requirement: {self.simulation_requirement}"
        
        for iteration in range(max_iterations):
            if progress_callback:
                progress_callback(
                    "generating", 
                    int((iteration / max_iterations) * 100),
                    f"Deep retrieval and writing ({tool_calls_count}/{self.MAX_TOOL_CALLS_PER_SECTION})"
                )
            
            # Call LLM
            response = self.llm.chat(
                messages=messages,
                temperature=0.5,
                max_tokens=16384
            )

            # Check if LLM response is None (API error or empty content)
            if response is None:
                logger.warning(f"Section {section.title} iteration {iteration + 1}: LLM returned None")
                # If iterations remain, add message and retry
                if iteration < max_iterations - 1:
                    messages.append({"role": "assistant", "content": "(Empty response)"})
                    messages.append({"role": "user", "content": "Please continue generating content."})
                    continue
                # Last iteration also returned None; break out for forced completion
                break

            logger.debug(f"LLM response: {response[:200]}...")

            # Parse once, reuse result
            tool_calls = self._parse_tool_calls(response)
            has_tool_calls = bool(tool_calls)
            has_final_answer = "Final Answer:" in response

            # ── Conflict handling: LLM output both tool call and Final Answer ──
            if has_tool_calls and has_final_answer:
                conflict_retries += 1
                logger.warning(
                    f"Section {section.title} iteration {iteration+1}: "
                    f"LLM output both tool call and Final Answer (conflict #{conflict_retries})"
                )

                if conflict_retries <= 2:
                    # First two times: discard response, ask LLM to reply again
                    messages.append({"role": "assistant", "content": response})
                    messages.append({
                        "role": "user",
                        "content": (
                            "[Format error] You included both a tool call and Final Answer in one reply. This is not allowed.\n"
                            "Each reply can only do one of the following:\n"
                            "- Call a tool (output one <tool_call> block, do not write Final Answer)\n"
                            "- Output final content (start with 'Final Answer:', do not include <tool_call>)\n"
                            "Please reply again, doing only one of these."
                        ),
                    })
                    continue
                else:
                    # Third time: degraded handling, truncate to first tool call, force execute
                    logger.warning(
                        f"Section {section.title}: {conflict_retries} consecutive conflicts, "
                        "degrading to truncated execution of first tool call"
                    )
                    first_tool_end = response.find('</tool_call>')
                    if first_tool_end != -1:
                        response = response[:first_tool_end + len('</tool_call>')]
                        tool_calls = self._parse_tool_calls(response)
                        has_tool_calls = bool(tool_calls)
                    has_final_answer = False
                    conflict_retries = 0

            # Log LLM response
            if self.report_logger:
                self.report_logger.log_llm_response(
                    section_title=section.title,
                    section_index=section_index,
                    response=response,
                    iteration=iteration + 1,
                    has_tool_calls=has_tool_calls,
                    has_final_answer=has_final_answer
                )

            # ── Case 1: LLM output Final Answer ──
            if has_final_answer:
                # Insufficient tool calls; reject and request more tool calls
                if tool_calls_count < min_tool_calls:
                    messages.append({"role": "assistant", "content": response})
                    unused_tools = all_tools - used_tools
                    unused_hint = f"(These tools have not been used yet, try them: {', '.join(unused_tools)})" if unused_tools else ""
                    messages.append({
                        "role": "user",
                        "content": REACT_INSUFFICIENT_TOOLS_MSG.format(
                            tool_calls_count=tool_calls_count,
                            min_tool_calls=min_tool_calls,
                            unused_hint=unused_hint,
                        ),
                    })
                    continue

                # Normal completion
                final_answer = response.split("Final Answer:")[-1].strip()
                logger.info(f"Section {section.title} generation complete (tool calls: {tool_calls_count})")

                if self.report_logger:
                    self.report_logger.log_section_content(
                        section_title=section.title,
                        section_index=section_index,
                        content=final_answer,
                        tool_calls_count=tool_calls_count
                    )
                return final_answer

            # ── Case 2: LLM attempts to call tool ──
            if has_tool_calls:
                # Tool quota exhausted -> explicitly notify, request Final Answer
                if tool_calls_count >= self.MAX_TOOL_CALLS_PER_SECTION:
                    messages.append({"role": "assistant", "content": response})
                    messages.append({
                        "role": "user",
                        "content": REACT_TOOL_LIMIT_MSG.format(
                            tool_calls_count=tool_calls_count,
                            max_tool_calls=self.MAX_TOOL_CALLS_PER_SECTION,
                        ),
                    })
                    continue

                # Only execute first tool call
                call = tool_calls[0]
                if len(tool_calls) > 1:
                    logger.info(f"LLM attempted {len(tool_calls)} tool calls, executing only first: {call['name']}")

                if self.report_logger:
                    self.report_logger.log_tool_call(
                        section_title=section.title,
                        section_index=section_index,
                        tool_name=call["name"],
                        parameters=call.get("parameters", {}),
                        iteration=iteration + 1
                    )

                result = self._execute_tool(
                    call["name"],
                    call.get("parameters", {}),
                    report_context=report_context
                )

                if self.report_logger:
                    self.report_logger.log_tool_result(
                        section_title=section.title,
                        section_index=section_index,
                        tool_name=call["name"],
                        result=result,
                        iteration=iteration + 1
                    )

                tool_calls_count += 1
                used_tools.add(call['name'])

                # Build unused tools hint
                unused_tools = all_tools - used_tools
                unused_hint = ""
                if unused_tools and tool_calls_count < self.MAX_TOOL_CALLS_PER_SECTION:
                    unused_hint = REACT_UNUSED_TOOLS_HINT.format(unused_list="、".join(unused_tools))

                messages.append({"role": "assistant", "content": response})
                messages.append({
                    "role": "user",
                    "content": REACT_OBSERVATION_TEMPLATE.format(
                        tool_name=call["name"],
                        result=result,
                        tool_calls_count=tool_calls_count,
                        max_tool_calls=self.MAX_TOOL_CALLS_PER_SECTION,
                        used_tools_str=", ".join(used_tools),
                        unused_hint=unused_hint,
                    ),
                })
                continue

            # ── Case 3: Neither tool call nor Final Answer ──
            messages.append({"role": "assistant", "content": response})

            if tool_calls_count < min_tool_calls:
                # Insufficient tool calls, recommend unused tools
                unused_tools = all_tools - used_tools
                unused_hint = f"(These tools have not been used yet, try them: {', '.join(unused_tools)})" if unused_tools else ""

                messages.append({
                    "role": "user",
                    "content": REACT_INSUFFICIENT_TOOLS_MSG_ALT.format(
                        tool_calls_count=tool_calls_count,
                        min_tool_calls=min_tool_calls,
                        unused_hint=unused_hint,
                    ),
                })
                continue

            # Sufficient tool calls, LLM output content without "Final Answer:" prefix
            # Use this content directly as final answer, no more empty iterations
            logger.info(f"Section {section.title}: 'Final Answer:' prefix not detected, adopting LLM output as final content (tool calls: {tool_calls_count})")
            final_answer = response.strip()

            if self.report_logger:
                self.report_logger.log_section_content(
                    section_title=section.title,
                    section_index=section_index,
                    content=final_answer,
                    tool_calls_count=tool_calls_count
                )
            return final_answer
        
        # Max iterations reached, force generate content
        logger.warning(f"Section {section.title} reached max iterations, forcing generation")
        messages.append({"role": "user", "content": REACT_FORCE_FINAL_MSG})
        
        response = self.llm.chat(
            messages=messages,
            temperature=0.5,
            max_tokens=4096
        )

        # Check if LLM returned None during forced completion
        if response is None:
            logger.error(f"Section {section.title}: LLM returned None during forced completion, using default error message")
            final_answer = f"(Section generation failed: LLM returned empty response, please retry later)"
        elif "Final Answer:" in response:
            final_answer = response.split("Final Answer:")[-1].strip()
        else:
            final_answer = response
        
        # Log section content generation complete
        if self.report_logger:
            self.report_logger.log_section_content(
                section_title=section.title,
                section_index=section_index,
                content=final_answer,
                tool_calls_count=tool_calls_count
            )
        
        return final_answer
    
    def generate_report(
        self, 
        progress_callback: Optional[Callable[[str, int, str], None]] = None,
        report_id: Optional[str] = None
    ) -> Report:
        """
        Generate full report (real-time output per section)
        
        Each section is saved to folder immediately after generation, no need to wait for full report.
        File structure:
        reports/{report_id}/
            meta.json       - Report metadata
            outline.json    - Report outline
            progress.json   - Generation progress
            section_01.md   - Section 1
            section_02.md   - Section 2
            ...
            full_report.md  - Full report
        
        Args:
            progress_callback: Progress callback function (stage, progress, message)
            report_id: Report ID (optional, auto-generated if not provided)
            
        Returns:
            Report: Full report
        """
        import uuid
        
        # Auto-generate report_id if not provided
        if not report_id:
            report_id = f"report_{uuid.uuid4().hex[:12]}"
        start_time = datetime.now()
        
        report = Report(
            report_id=report_id,
            simulation_id=self.simulation_id,
            graph_id=self.graph_id,
            simulation_requirement=self.simulation_requirement,
            status=ReportStatus.PENDING,
            created_at=datetime.now().isoformat()
        )
        
        # Completed section title list (for progress tracking)
        completed_section_titles = []
        
        try:
            # Initialize: create report folder and save initial state
            ReportManager._ensure_report_folder(report_id)
            
            # Initialize logger (structured log agent_log.jsonl)
            self.report_logger = ReportLogger(report_id)
            self.report_logger.log_start(
                simulation_id=self.simulation_id,
                graph_id=self.graph_id,
                simulation_requirement=self.simulation_requirement
            )
            
            # Initialize console logger（console_log.txt）
            self.console_logger = ReportConsoleLogger(report_id)
            
            ReportManager.update_progress(
                report_id, "pending", 0, "Initializing report...",
                completed_sections=[]
            )
            ReportManager.save_report(report)
            
            # Phase 1: Plan outline
            report.status = ReportStatus.PLANNING
            ReportManager.update_progress(
                report_id, "planning", 5, "Planning report outline...",
                completed_sections=[]
            )
            
            # Log planning start
            self.report_logger.log_planning_start()
            
            if progress_callback:
                progress_callback("planning", 0, "Planning report outline...")
            
            outline = self.plan_outline(
                progress_callback=lambda stage, prog, msg: 
                    progress_callback(stage, prog // 5, msg) if progress_callback else None
            )
            report.outline = outline
            
            # Log planning complete
            self.report_logger.log_planning_complete(outline.to_dict())
            
            # Save outline to file
            ReportManager.save_outline(report_id, outline)
            ReportManager.update_progress(
                report_id, "planning", 15, f"Outline planning complete, {len(outline.sections)} sections",
                completed_sections=[]
            )
            ReportManager.save_report(report)
            
            logger.info(f"Outline saved to file: {report_id}/outline.json")
            
            # Phase 2: Generate section by section (save per section)
            report.status = ReportStatus.GENERATING
            
            total_sections = len(outline.sections)
            generated_sections = []  # Save content for context
            
            for i, section in enumerate(outline.sections):
                section_num = i + 1
                base_progress = 20 + int((i / total_sections) * 70)
                
                # Update progress
                ReportManager.update_progress(
                    report_id, "generating", base_progress,
                    f"Generating section: {section.title} ({section_num}/{total_sections})",
                    current_section=section.title,
                    completed_sections=completed_section_titles
                )
                
                if progress_callback:
                    progress_callback(
                        "generating", 
                        base_progress, 
                        f"Generating section: {section.title} ({section_num}/{total_sections})"
                    )
                
                # Generate main section content
                section_content = self._generate_section_react(
                    section=section,
                    outline=outline,
                    previous_sections=generated_sections,
                    progress_callback=lambda stage, prog, msg:
                        progress_callback(
                            stage, 
                            base_progress + int(prog * 0.7 / total_sections),
                            msg
                        ) if progress_callback else None,
                    section_index=section_num
                )
                
                section.content = section_content
                generated_sections.append(f"## {section.title}\n\n{section_content}")

                # Save section
                ReportManager.save_section(report_id, section_num, section)
                completed_section_titles.append(section.title)

                # Log section complete
                full_section_content = f"## {section.title}\n\n{section_content}"

                if self.report_logger:
                    self.report_logger.log_section_full_complete(
                        section_title=section.title,
                        section_index=section_num,
                        full_content=full_section_content.strip()
                    )

                logger.info(f"Section saved: {report_id}/section_{section_num:02d}.md")
                
                # Update progress
                ReportManager.update_progress(
                    report_id, "generating", 
                    base_progress + int(70 / total_sections),
                    f"Section {section.title} completed",
                    current_section=None,
                    completed_sections=completed_section_titles
                )
            
            # Phase 3: Assemble full report
            if progress_callback:
                progress_callback("generating", 95, "Assembling full report...")
            
            ReportManager.update_progress(
                report_id, "generating", 95, "Assembling full report...",
                completed_sections=completed_section_titles
            )
            
            # Use ReportManager to assemble full report
            report.markdown_content = ReportManager.assemble_full_report(report_id, outline)
            report.status = ReportStatus.COMPLETED
            report.completed_at = datetime.now().isoformat()
            
            # Calculate total time
            total_time_seconds = (datetime.now() - start_time).total_seconds()
            
            # Log report complete
            if self.report_logger:
                self.report_logger.log_report_complete(
                    total_sections=total_sections,
                    total_time_seconds=total_time_seconds
                )
            
            # Save final report
            ReportManager.save_report(report)
            ReportManager.update_progress(
                report_id, "completed", 100, "Report generation complete",
                completed_sections=completed_section_titles
            )
            
            if progress_callback:
                progress_callback("completed", 100, "Report generation complete")
            
            logger.info(f"Report generation complete: {report_id}")
            
            # Close console logger
            if self.console_logger:
                self.console_logger.close()
                self.console_logger = None
            
            return report
            
        except Exception as e:
            logger.error(f"Report generation failed: {str(e)}")
            report.status = ReportStatus.FAILED
            report.error = str(e)
            
            # Log error
            if self.report_logger:
                self.report_logger.log_error(str(e), "failed")
            
            # Save failed state
            try:
                ReportManager.save_report(report)
                ReportManager.update_progress(
                    report_id, "failed", -1, f"Report generation failed: {str(e)}",
                    completed_sections=completed_section_titles
                )
            except Exception:
                pass  # Ignore save failure errors
            
            # Close console logger
            if self.console_logger:
                self.console_logger.close()
                self.console_logger = None
            
            return report
    
    def chat(
        self, 
        message: str,
        chat_history: List[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Chat with Report Agent
        
        In conversation, the agent can autonomously call retrieval tools to answer questions
        
        Args:
            message: User message
            chat_history: Chat history
            
        Returns:
            {
                "response": "Agent reply",
                "tool_calls": [list of tools called],
                "sources": [information sources]
            }
        """
        logger.info(f"Report Agent chat: {message[:50]}...")
        
        chat_history = chat_history or []
        
        # Get generated report content
        report_content = ""
        try:
            report = ReportManager.get_report_by_simulation(self.simulation_id)
            if report and report.markdown_content:
                # Limit report length to avoid excessive context
                report_content = report.markdown_content[:15000]
                if len(report.markdown_content) > 15000:
                    report_content += "\n\n... [Report content truncated] ..."
        except Exception as e:
            logger.warning(f"Failed to get report content: {e}")
        
        system_prompt = CHAT_SYSTEM_PROMPT_TEMPLATE.format(
            simulation_requirement=self.simulation_requirement,
            report_content=report_content if report_content else "(No report yet)",
            tools_description=self._get_tools_description(),
        )

        # Build messages
        messages = [{"role": "system", "content": system_prompt}]
        
        # Add chat history
        for h in chat_history[-10:]:  # Limit history length
            messages.append(h)
        
        # Add user message
        messages.append({
            "role": "user", 
            "content": message
        })
        
        # ReACT loop (simplified)
        tool_calls_made = []
        max_iterations = 2  # Reduced iteration rounds
        
        for iteration in range(max_iterations):
            response = self.chat_llm.chat(
                messages=messages,
                temperature=0.5
            )
            
            # Parse tool calls
            tool_calls = self._parse_tool_calls(response)
            
            if not tool_calls:
                # No tool calls, return response directly
                clean_response = re.sub(r'<tool_call>.*?</tool_call>', '', response, flags=re.DOTALL)
                clean_response = re.sub(r'\[TOOL_CALL\].*?\)', '', clean_response)
                
                return {
                    "response": clean_response.strip(),
                    "tool_calls": tool_calls_made,
                    "sources": [tc.get("parameters", {}).get("query", "") for tc in tool_calls_made]
                }
            
            # Execute tool call（限制数量）
            tool_results = []
            for call in tool_calls[:1]:  # Max 1 tool call per round
                if len(tool_calls_made) >= self.MAX_TOOL_CALLS_PER_CHAT:
                    break
                result = self._execute_tool(call["name"], call.get("parameters", {}))
                tool_results.append({
                    "tool": call["name"],
                    "result": result[:1500]  # Limit result length
                })
                tool_calls_made.append(call)
            
            # Add results to messages
            messages.append({"role": "assistant", "content": response})
            observation = "\n".join([f"[{r['tool']} result]\n{r['result']}" for r in tool_results])
            messages.append({
                "role": "user",
                "content": observation + CHAT_OBSERVATION_SUFFIX
            })
        
        # Max iterations reached, get final response
        final_response = self.chat_llm.chat(
            messages=messages,
            temperature=0.5
        )
        
        # Clean response
        clean_response = re.sub(r'<tool_call>.*?</tool_call>', '', final_response, flags=re.DOTALL)
        clean_response = re.sub(r'\[TOOL_CALL\].*?\)', '', clean_response)
        
        return {
            "response": clean_response.strip(),
            "tool_calls": tool_calls_made,
            "sources": [tc.get("parameters", {}).get("query", "") for tc in tool_calls_made]
        }


class ReportManager:
    """
    Report manager
    
    Handles persistent storage and retrieval of reports
    
    File structure (per-section output):
    reports/
      {report_id}/
        meta.json          - Report metadata and status
        outline.json       - Report outline
        progress.json      - Generation progress
        section_01.md      - Section 1
        section_02.md      - Section 2
        ...
        full_report.md     - Full report
    """
    
    # Report storage directory
    REPORTS_DIR = os.path.join(Config.UPLOAD_FOLDER, 'reports')
    
    @classmethod
    def _ensure_reports_dir(cls):
        """Ensure reports root directory exists"""
        os.makedirs(cls.REPORTS_DIR, exist_ok=True)
    
    @classmethod
    def _get_report_folder(cls, report_id: str) -> str:
        """Get report folder path"""
        return os.path.join(cls.REPORTS_DIR, report_id)
    
    @classmethod
    def _ensure_report_folder(cls, report_id: str) -> str:
        """Ensure report folder exists and return path"""
        folder = cls._get_report_folder(report_id)
        os.makedirs(folder, exist_ok=True)
        return folder
    
    @classmethod
    def _get_report_path(cls, report_id: str) -> str:
        """Get report metadata file path"""
        return os.path.join(cls._get_report_folder(report_id), "meta.json")
    
    @classmethod
    def _get_report_markdown_path(cls, report_id: str) -> str:
        """Get full report Markdown file path"""
        return os.path.join(cls._get_report_folder(report_id), "full_report.md")
    
    @classmethod
    def _get_outline_path(cls, report_id: str) -> str:
        """Get outline file path"""
        return os.path.join(cls._get_report_folder(report_id), "outline.json")
    
    @classmethod
    def _get_progress_path(cls, report_id: str) -> str:
        """Get progress file path"""
        return os.path.join(cls._get_report_folder(report_id), "progress.json")
    
    @classmethod
    def _get_section_path(cls, report_id: str, section_index: int) -> str:
        """Get section Markdown file path"""
        return os.path.join(cls._get_report_folder(report_id), f"section_{section_index:02d}.md")
    
    @classmethod
    def _get_agent_log_path(cls, report_id: str) -> str:
        """Get agent log file path"""
        return os.path.join(cls._get_report_folder(report_id), "agent_log.jsonl")
    
    @classmethod
    def _get_console_log_path(cls, report_id: str) -> str:
        """Get console log file path"""
        return os.path.join(cls._get_report_folder(report_id), "console_log.txt")
    
    @classmethod
    def get_console_log(cls, report_id: str, from_line: int = 0) -> Dict[str, Any]:
        """
        Get console log content
        
        These are console output logs (INFO, WARNING, etc.) during report generation,
        different from the structured logs in agent_log.jsonl.
        
        Args:
            report_id: Report ID
            from_line: Line number to start reading from (for incremental fetch, 0 = start)
            
        Returns:
            {
                "logs": [log line list],
                "total_lines": total lines,
                "from_line": starting line number,
                "has_more": whether there are more logs
            }
        """
        log_path = cls._get_console_log_path(report_id)
        
        if not os.path.exists(log_path):
            return {
                "logs": [],
                "total_lines": 0,
                "from_line": 0,
                "has_more": False
            }
        
        logs = []
        total_lines = 0
        
        with open(log_path, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                total_lines = i + 1
                if i >= from_line:
                    # Keep original log line, strip trailing newline
                    logs.append(line.rstrip('\n\r'))
        
        return {
            "logs": logs,
            "total_lines": total_lines,
            "from_line": from_line,
            "has_more": False  # Read to end
        }
    
    @classmethod
    def get_console_log_stream(cls, report_id: str) -> List[str]:
        """
        Get complete console log (one-time full fetch)
        
        Args:
            report_id: Report ID
            
        Returns:
            Log line list
        """
        result = cls.get_console_log(report_id, from_line=0)
        return result["logs"]
    
    @classmethod
    def get_agent_log(cls, report_id: str, from_line: int = 0) -> Dict[str, Any]:
        """
        Get agent log content
        
        Args:
            report_id: Report ID
            from_line: Line number to start reading from (for incremental fetch, 0 = start)
            
        Returns:
            {
                "logs": [log entry list],
                "total_lines": total lines,
                "from_line": starting line number,
                "has_more": whether there are more logs
            }
        """
        log_path = cls._get_agent_log_path(report_id)
        
        if not os.path.exists(log_path):
            return {
                "logs": [],
                "total_lines": 0,
                "from_line": 0,
                "has_more": False
            }
        
        logs = []
        total_lines = 0
        
        with open(log_path, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                total_lines = i + 1
                if i >= from_line:
                    try:
                        log_entry = json.loads(line.strip())
                        logs.append(log_entry)
                    except json.JSONDecodeError:
                        # Skip lines that fail to parse
                        continue
        
        return {
            "logs": logs,
            "total_lines": total_lines,
            "from_line": from_line,
            "has_more": False  # Read to end
        }
    
    @classmethod
    def get_agent_log_stream(cls, report_id: str) -> List[Dict[str, Any]]:
        """
        Get complete agent log (for one-time full fetch)
        
        Args:
            report_id: Report ID
            
        Returns:
            Log entry list
        """
        result = cls.get_agent_log(report_id, from_line=0)
        return result["logs"]
    
    @classmethod
    def save_outline(cls, report_id: str, outline: ReportOutline) -> None:
        """
        Save report outline
        
        Called immediately after planning phase completes
        """
        cls._ensure_report_folder(report_id)
        
        with open(cls._get_outline_path(report_id), 'w', encoding='utf-8') as f:
            json.dump(outline.to_dict(), f, ensure_ascii=False, indent=2)
        
        logger.info(f"Outline saved: {report_id}")
    
    @classmethod
    def save_section(
        cls,
        report_id: str,
        section_index: int,
        section: ReportSection
    ) -> str:
        """
        Save single section

        Called immediately after each section is generated for per-section output

        Args:
            report_id: Report ID
            section_index: Section index (1-based)
            section: Section object

        Returns:
            Saved file path
        """
        cls._ensure_report_folder(report_id)

        # Build section Markdown content - clean possible duplicate headings
        cleaned_content = cls._clean_section_content(section.content, section.title)
        md_content = f"## {section.title}\n\n"
        if cleaned_content:
            md_content += f"{cleaned_content}\n\n"

        # Save file
        file_suffix = f"section_{section_index:02d}.md"
        file_path = os.path.join(cls._get_report_folder(report_id), file_suffix)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(md_content)

        logger.info(f"Section saved: {report_id}/{file_suffix}")
        return file_path
    
    @classmethod
    def _clean_section_content(cls, content: str, section_title: str) -> str:
        """
        Clean section content
        
        1. Remove Markdown heading lines at the beginning that duplicate the section title
        2. Convert all ### and lower-level headings to bold text
        
        Args:
            content: Original content
            section_title: Section title
            
        Returns:
            Cleaned content
        """
        import re
        
        if not content:
            return content
        
        content = content.strip()
        lines = content.split('\n')
        cleaned_lines = []
        skip_next_empty = False
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            # Check if this is a Markdown heading line
            heading_match = re.match(r'^(#{1,6})\s+(.+)$', stripped)
            
            if heading_match:
                level = len(heading_match.group(1))
                title_text = heading_match.group(2).strip()
                
                # Check if heading duplicates section title (skip duplicates in first 5 lines)
                if i < 5:
                    if title_text == section_title or title_text.replace(' ', '') == section_title.replace(' ', ''):
                        skip_next_empty = True
                        continue
                
                # Convert all heading levels (#, ##, ###, #### etc.) to bold
                # Since section headings are added by the system, content should not have any headings
                cleaned_lines.append(f"**{title_text}**")
                cleaned_lines.append("")  # Add blank line
                continue
            
            # If previous line was a skipped heading and current line is empty, skip too
            if skip_next_empty and stripped == '':
                skip_next_empty = False
                continue
            
            skip_next_empty = False
            cleaned_lines.append(line)
        
        # Remove leading blank lines
        while cleaned_lines and cleaned_lines[0].strip() == '':
            cleaned_lines.pop(0)
        
        # Remove leading separator lines
        while cleaned_lines and cleaned_lines[0].strip() in ['---', '***', '___']:
            cleaned_lines.pop(0)
            # Also remove blank lines after separator
            while cleaned_lines and cleaned_lines[0].strip() == '':
                cleaned_lines.pop(0)
        
        return '\n'.join(cleaned_lines)
    
    @classmethod
    def update_progress(
        cls, 
        report_id: str, 
        status: str, 
        progress: int, 
        message: str,
        current_section: str = None,
        completed_sections: List[str] = None
    ) -> None:
        """
        Update report generation progress
        
        Frontend can read progress.json for real-time progress
        """
        cls._ensure_report_folder(report_id)
        
        progress_data = {
            "status": status,
            "progress": progress,
            "message": message,
            "current_section": current_section,
            "completed_sections": completed_sections or [],
            "updated_at": datetime.now().isoformat()
        }
        
        with open(cls._get_progress_path(report_id), 'w', encoding='utf-8') as f:
            json.dump(progress_data, f, ensure_ascii=False, indent=2)
    
    @classmethod
    def get_progress(cls, report_id: str) -> Optional[Dict[str, Any]]:
        """Get report generation progress"""
        path = cls._get_progress_path(report_id)
        
        if not os.path.exists(path):
            return None
        
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    @classmethod
    def get_generated_sections(cls, report_id: str) -> List[Dict[str, Any]]:
        """
        Get list of generated sections
        
        Returns info for all saved section files
        """
        folder = cls._get_report_folder(report_id)
        
        if not os.path.exists(folder):
            return []
        
        sections = []
        for filename in sorted(os.listdir(folder)):
            if filename.startswith('section_') and filename.endswith('.md'):
                file_path = os.path.join(folder, filename)
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                # Parse section index from filename
                parts = filename.replace('.md', '').split('_')
                section_index = int(parts[1])

                sections.append({
                    "filename": filename,
                    "section_index": section_index,
                    "content": content
                })

        return sections
    
    @classmethod
    def assemble_full_report(cls, report_id: str, outline: ReportOutline) -> str:
        """
        Assemble full report
        
        Assemble full report from saved section files with heading cleanup
        """
        folder = cls._get_report_folder(report_id)
        
        # Build report header
        md_content = f"# {outline.title}\n\n"
        md_content += f"> {outline.summary}\n\n"
        md_content += f"---\n\n"
        
        # Read all section files in order
        sections = cls.get_generated_sections(report_id)
        for section_info in sections:
            md_content += section_info["content"]
        
        # Post-process: clean up heading issues across the report
        md_content = cls._post_process_report(md_content, outline)
        
        # Save full report
        full_path = cls._get_report_markdown_path(report_id)
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(md_content)
        
        logger.info(f"Full report assembled: {report_id}")
        return md_content
    
    @classmethod
    def _post_process_report(cls, content: str, outline: ReportOutline) -> str:
        """
        Post-process report content
        
        1. Remove duplicate headings
        2. Keep report title (#) and section headings (##), remove other heading levels (###, #### etc.)
        3. Clean up excessive blank lines and separators
        
        Args:
            content: Original report content
            outline: Report outline
            
        Returns:
            Processed content
        """
        import re
        
        lines = content.split('\n')
        processed_lines = []
        prev_was_heading = False
        
        # Collect all section titles from outline
        section_titles = set()
        for section in outline.sections:
            section_titles.add(section.title)
        
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            
            # Check if line is a heading
            heading_match = re.match(r'^(#{1,6})\s+(.+)$', stripped)
            
            if heading_match:
                level = len(heading_match.group(1))
                title = heading_match.group(2).strip()
                
                # Check for duplicate heading (same title within 5 consecutive lines)
                is_duplicate = False
                for j in range(max(0, len(processed_lines) - 5), len(processed_lines)):
                    prev_line = processed_lines[j].strip()
                    prev_match = re.match(r'^(#{1,6})\s+(.+)$', prev_line)
                    if prev_match:
                        prev_title = prev_match.group(2).strip()
                        if prev_title == title:
                            is_duplicate = True
                            break
                
                if is_duplicate:
                    # Skip duplicate heading and following blank lines
                    i += 1
                    while i < len(lines) and lines[i].strip() == '':
                        i += 1
                    continue
                
                # Heading level handling:
                # - # (level=1) Keep only report main title
                # - ## (level=2) Keep section headings
                # - ### and below (level>=3) Convert to bold text
                
                if level == 1:
                    if title == outline.title:
                        # Keep report main title
                        processed_lines.append(line)
                        prev_was_heading = True
                    elif title in section_titles:
                        # Section title incorrectly used #, correct to ##
                        processed_lines.append(f"## {title}")
                        prev_was_heading = True
                    else:
                        # Convert other h1 titles to bold
                        processed_lines.append(f"**{title}**")
                        processed_lines.append("")
                        prev_was_heading = False
                elif level == 2:
                    if title in section_titles or title == outline.title:
                        # Keep section heading
                        processed_lines.append(line)
                        prev_was_heading = True
                    else:
                        # Convert non-section h2 titles to bold
                        processed_lines.append(f"**{title}**")
                        processed_lines.append("")
                        prev_was_heading = False
                else:
                    # ### and below heading levels converted to bold text
                    processed_lines.append(f"**{title}**")
                    processed_lines.append("")
                    prev_was_heading = False
                
                i += 1
                continue
            
            elif stripped == '---' and prev_was_heading:
                # Skip separator line immediately after heading
                i += 1
                continue
            
            elif stripped == '' and prev_was_heading:
                # Keep only one blank line after heading
                if processed_lines and processed_lines[-1].strip() != '':
                    processed_lines.append(line)
                prev_was_heading = False
            
            else:
                processed_lines.append(line)
                prev_was_heading = False
            
            i += 1
        
        # Clean consecutive blank lines (keep max 2)
        result_lines = []
        empty_count = 0
        for line in processed_lines:
            if line.strip() == '':
                empty_count += 1
                if empty_count <= 2:
                    result_lines.append(line)
            else:
                empty_count = 0
                result_lines.append(line)
        
        return '\n'.join(result_lines)
    
    @classmethod
    def save_report(cls, report: Report) -> None:
        """Save report metadata and full report"""
        cls._ensure_report_folder(report.report_id)
        
        # Save metadata JSON
        with open(cls._get_report_path(report.report_id), 'w', encoding='utf-8') as f:
            json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)
        
        # Save outline
        if report.outline:
            cls.save_outline(report.report_id, report.outline)
        
        # Save full Markdown report
        if report.markdown_content:
            with open(cls._get_report_markdown_path(report.report_id), 'w', encoding='utf-8') as f:
                f.write(report.markdown_content)
        
        logger.info(f"Report saved: {report.report_id}")
    
    @classmethod
    def get_report(cls, report_id: str) -> Optional[Report]:
        """Get report"""
        path = cls._get_report_path(report_id)
        
        if not os.path.exists(path):
            # Backward compatibility: check files stored directly in reports directory
            old_path = os.path.join(cls.REPORTS_DIR, f"{report_id}.json")
            if os.path.exists(old_path):
                path = old_path
            else:
                return None
        
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Rebuild Report object
        outline = None
        if data.get('outline'):
            outline_data = data['outline']
            sections = []
            for s in outline_data.get('sections', []):
                sections.append(ReportSection(
                    title=s['title'],
                    content=s.get('content', '')
                ))
            outline = ReportOutline(
                title=outline_data['title'],
                summary=outline_data['summary'],
                sections=sections
            )
        
        # If markdown_content is empty, try reading from full_report.md
        markdown_content = data.get('markdown_content', '')
        if not markdown_content:
            full_report_path = cls._get_report_markdown_path(report_id)
            if os.path.exists(full_report_path):
                with open(full_report_path, 'r', encoding='utf-8') as f:
                    markdown_content = f.read()
        
        return Report(
            report_id=data['report_id'],
            simulation_id=data['simulation_id'],
            graph_id=data['graph_id'],
            simulation_requirement=data['simulation_requirement'],
            status=ReportStatus(data['status']),
            outline=outline,
            markdown_content=markdown_content,
            created_at=data.get('created_at', ''),
            completed_at=data.get('completed_at', ''),
            error=data.get('error')
        )
    
    @classmethod
    def get_report_by_simulation(cls, simulation_id: str) -> Optional[Report]:
        """Get report by simulation ID"""
        cls._ensure_reports_dir()
        
        for item in os.listdir(cls.REPORTS_DIR):
            item_path = os.path.join(cls.REPORTS_DIR, item)
            # New format: folder
            if os.path.isdir(item_path):
                report = cls.get_report(item)
                if report and report.simulation_id == simulation_id:
                    return report
            # Backward compatibility: JSON file
            elif item.endswith('.json'):
                report_id = item[:-5]
                report = cls.get_report(report_id)
                if report and report.simulation_id == simulation_id:
                    return report
        
        return None
    
    @classmethod
    def list_reports(cls, simulation_id: Optional[str] = None, limit: int = 50) -> List[Report]:
        """List reports"""
        cls._ensure_reports_dir()
        
        reports = []
        for item in os.listdir(cls.REPORTS_DIR):
            item_path = os.path.join(cls.REPORTS_DIR, item)
            # New format: folder
            if os.path.isdir(item_path):
                report = cls.get_report(item)
                if report:
                    if simulation_id is None or report.simulation_id == simulation_id:
                        reports.append(report)
            # Backward compatibility: JSON file
            elif item.endswith('.json'):
                report_id = item[:-5]
                report = cls.get_report(report_id)
                if report:
                    if simulation_id is None or report.simulation_id == simulation_id:
                        reports.append(report)
        
        # Sort by creation time descending
        reports.sort(key=lambda r: r.created_at, reverse=True)
        
        return reports[:limit]
    
    @classmethod
    def delete_report(cls, report_id: str) -> bool:
        """Delete report (entire folder)"""
        import shutil
        
        folder_path = cls._get_report_folder(report_id)
        
        # New format: delete entire folder
        if os.path.exists(folder_path) and os.path.isdir(folder_path):
            shutil.rmtree(folder_path)
            logger.info(f"Report folder deleted: {report_id}")
            return True
        
        # Backward compatibility: delete individual files
        deleted = False
        old_json_path = os.path.join(cls.REPORTS_DIR, f"{report_id}.json")
        old_md_path = os.path.join(cls.REPORTS_DIR, f"{report_id}.md")
        
        if os.path.exists(old_json_path):
            os.remove(old_json_path)
            deleted = True
        if os.path.exists(old_md_path):
            os.remove(old_md_path)
            deleted = True
        
        return deleted
