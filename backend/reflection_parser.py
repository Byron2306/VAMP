"""Reflection Parser - Analyzes workflow decisions and generates feedback forms.

Phase 6: Reflection Parser
Extracts insights from approval decisions and generates structured feedback.
Supports HTML form generation and deterministic decision analysis.
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import logging
import json


class DecisionCategory(Enum):
    """Categories of HR approval decisions for reflection."""
    POLICY_ADHERENCE = "policy_adherence"
    EVIDENCE_QUALITY = "evidence_quality"
    WORKFLOW_EFFICIENCY = "workflow_efficiency"
    APPROVER_CONFIDENCE = "approver_confidence"
    ESCALATION_PATTERNS = "escalation_patterns"
    DECISION_TIME = "decision_time"


class FeedbackType(Enum):
    """Types of feedback generated from decisions."""
    IMPROVEMENT = "improvement"
    COMPLIANCE = "compliance"
    EFFICIENCY = "efficiency"
    QUALITY = "quality"
    PATTERN = "pattern"


@dataclass
class DecisionInsight:
    """Insight extracted from a single approval decision."""
    decision_id: str
    category: DecisionCategory
    insight_type: str
    description: str
    metrics: Dict[str, Any] = field(default_factory=dict)
    confidence_level: int = 85  # 0-100
    actionable: bool = True
    generated_at: datetime = field(default_factory=datetime.now)


@dataclass
class ReflectionForm:
    """Structured feedback form based on workflow analysis."""
    form_id: str
    title: str
    description: str
    questions: List[Dict[str, Any]] = field(default_factory=list)
    sections: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    generated_at: datetime = field(default_factory=datetime.now)
    
    def add_question(self, question_type: str, text: str, required: bool = True, options: Optional[List] = None):
        """Add question to form."""
        self.questions.append({
            "type": question_type,  # text, rating, multiple_choice, textarea
            "text": text,
            "required": required,
            "options": options or []
        })
    
    def add_section(self, title: str, description: str, questions: List = None):
        """Add section to form."""
        self.sections.append({
            "title": title,
            "description": description,
            "questions": questions or []
        })
    
    def to_html(self) -> str:
        """Generate HTML representation of form."""
        html = f"""<form id="{self.form_id}" class="reflection-form">
    <h2>{self.title}</h2>
    <p>{self.description}</p>
"""
        
        for section in self.sections:
            html += f"""    <fieldset>
        <legend>{section['title']}</legend>
        <p>{section['description']}</p>
"""
            for q in section['questions']:
                html += f"""        <div class="form-group">
            <label>{q.get('text', '')}</label>
"""
                if q.get('type') == 'textarea':
                    html += f"""            <textarea name="{q.get('name', '')}" required="{q.get('required', False)}"></textarea>
"""
                elif q.get('type') == 'rating':
                    html += f"""            <input type="range" min="1" max="5" name="{q.get('name', '')}" />
"""
                html += "        </div>\n"
            html += "    </fieldset>\n"
        
        html += "    <button type="submit">Submit Feedback</button>\n</form>"
        return html


class ReflectionParser:
    """Parses approval workflow decisions and generates feedback."""
    
    def __init__(self):
        self.logger = logging.getLogger("ReflectionParser")
        self.insights: List[DecisionInsight] = []
        self.forms_generated: List[ReflectionForm] = []
        self.analysis_history: List[Dict] = []
    
    def analyze_decision(self, decision: Dict) -> Optional[DecisionInsight]:
        """Extract insight from approval decision.
        
        Args:
            decision: Decision record with metadata
            
        Returns:
            DecisionInsight or None if analysis fails
        """
        try:
            # Analyze decision factors
            approval_time = decision.get('approval_time', 0)
            confidence = decision.get('confidence', 70)
            was_escalated = decision.get('escalated', False)
            
            # Determine insight category
            if was_escalated:
                category = DecisionCategory.ESCALATION_PATTERNS
                description = "Decision required escalation - may indicate complexity"
            elif approval_time > 3600:  # > 1 hour
                category = DecisionCategory.DECISION_TIME
                description = "Extended decision time - may need process optimization"
            elif confidence < 70:
                category = DecisionCategory.APPROVER_CONFIDENCE
                description = "Lower confidence score - may need more evidence"
            else:
                category = DecisionCategory.WORKFLOW_EFFICIENCY
                description = "Efficient decision with good confidence"
            
            insight = DecisionInsight(
                decision_id=decision.get('id', 'unknown'),
                category=category,
                insight_type="automatic_analysis",
                description=description,
                metrics={
                    "approval_time_seconds": approval_time,
                    "confidence_score": confidence,
                    "was_escalated": was_escalated
                },
                confidence_level=min(95, max(50, confidence))
            )
            
            self.insights.append(insight)
            self._log_analysis("ANALYZED", decision.get('id', 'unknown'))
            return insight
            
        except Exception as e:
            self.logger.error(f"Analysis failed: {str(e)}")
            return None
    
    def generate_feedback_form(self, decision_category: DecisionCategory, title: str) -> ReflectionForm:
        """Generate structured feedback form for category.
        
        Args:
            decision_category: Category of decisions to address
            title: Form title
            
        Returns:
            ReflectionForm with questions and sections
        """
        form = ReflectionForm(
            form_id=f"form_{decision_category.value}_{datetime.now().timestamp()}",
            title=title,
            description=f"Feedback form for {decision_category.value} decisions"
        )
        
        if decision_category == DecisionCategory.EVIDENCE_QUALITY:
            form.add_section(
                "Evidence Assessment",
                "How would you rate the quality of evidence in this workflow?",
                [
                    {"text": "Was the evidence clear and relevant?", "type": "rating"},
                    {"text": "Suggestions for improvement:", "type": "textarea"}
                ]
            )
        
        elif decision_category == DecisionCategory.WORKFLOW_EFFICIENCY:
            form.add_section(
                "Process Efficiency",
                "How efficient was this approval workflow?",
                [
                    {"text": "Decision time was appropriate", "type": "rating"},
                    {"text": "Process suggestions:", "type": "textarea"}
                ]
            )
        
        elif decision_category == DecisionCategory.ESCALATION_PATTERNS:
            form.add_section(
                "Escalation Analysis",
                "Was the escalation necessary and handled well?",
                [
                    {"text": "Escalation was justified", "type": "rating"},
                    {"text": "Escalation details:", "type": "textarea"}
                ]
            )
        
        form.add_question(
            "text",
            "Additional comments or concerns:",
            required=False
        )
        
        self.forms_generated.append(form)
        self._log_analysis("FORM_GENERATED", form.form_id)
        return form
    
    def analyze_batch_decisions(self, decisions: List[Dict]) -> Dict[str, Any]:
        """Analyze multiple decisions and generate summary.
        
        Args:
            decisions: List of decision records
            
        Returns:
            Analysis summary with insights and patterns
        """
        results = {
            "timestamp": datetime.now().isoformat(),
            "total_decisions": len(decisions),
            "insights_generated": 0,
            "by_category": {},
            "patterns_detected": [],
            "recommendations": []
        }
        
        category_counts = {}
        
        for decision in decisions:
            insight = self.analyze_decision(decision)
            if insight:
                results["insights_generated"] += 1
                category = insight.category.value
                category_counts[category] = category_counts.get(category, 0) + 1
        
        results["by_category"] = category_counts
        
        # Detect patterns
        if category_counts.get(DecisionCategory.ESCALATION_PATTERNS.value, 0) > len(decisions) * 0.3:
            results["patterns_detected"].append(
                "High escalation rate - may indicate process complexity"
            )
            results["recommendations"].append(
                "Review evidence requirements and approver training"
            )
        
        self._log_analysis("BATCH_ANALYSIS_COMPLETE", f"Processed {len(decisions)} decisions")
        return results
    
    def get_insights_by_category(self, category: DecisionCategory) -> List[DecisionInsight]:
        """Get all insights for a specific category.
        
        Args:
            category: Decision category to filter
            
        Returns:
            List of DecisionInsight objects
        """
        return [i for i in self.insights if i.category == category]
    
    def _log_analysis(self, action: str, details: str):
        """Log analysis action for audit trail."""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "details": details
        }
        self.analysis_history.append(log_entry)
    
    def get_analysis_history(self) -> List[Dict]:
        """Get complete analysis audit trail."""
        return self.analysis_history.copy()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Example: Parse workflow decisions
    parser = ReflectionParser()
    
    # Analyze sample decisions
    sample_decisions = [
        {"id": "dec_001", "approval_time": 1200, "confidence": 92, "escalated": False},
        {"id": "dec_002", "approval_time": 4500, "confidence": 65, "escalated": True},
        {"id": "dec_003", "approval_time": 900, "confidence": 88, "escalated": False}
    ]
    
    analysis = parser.analyze_batch_decisions(sample_decisions)
    print("Analysis Results:")
    print(json.dumps(analysis, indent=2))
    
    # Generate feedback form for evidence quality
    form = parser.generate_feedback_form(
        DecisionCategory.EVIDENCE_QUALITY,
        "Evidence Quality Feedback"
    )
    
    print("\nGenerated Form HTML:")
    print(form.to_html())
