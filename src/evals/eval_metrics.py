"""
Evaluation Metrics Calculator for LLM-generated dashboards.

Calculates metrics for comparing Structured vs RAG pipeline outputs:
- Factual Accuracy (0-3)
- Schema Compliance (0-2)
- Provenance Quality (0-2)
- Hallucination Detection (0-2)
- Readability (0-1)
- Mean Reciprocal Ranking (MRR)

Usage:
    from eval_metrics import EvaluationMetrics, calculate_mrr
    
    metrics = EvaluationMetrics(
        company_name="World Labs",
        pipeline_type="structured"
    )
    
    # Manually score metrics
    metrics.factual_accuracy = 3
    metrics.schema_compliance = 2
    # ... etc
    
    # Or calculate from ground truth
    scores = metrics.from_ground_truth(ground_truth_data)
"""

import json
import logging
from dataclasses import dataclass, asdict, field
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class MetricRange(Enum):
    """Metric range constraints."""
    FACTUAL_ACCURACY = (0, 3)
    SCHEMA_COMPLIANCE = (0, 2)
    PROVENANCE_QUALITY = (0, 2)
    HALLUCINATION_DETECTION = (0, 2)
    READABILITY = (0, 1)
    MRR = (0.0, 1.0)


@dataclass
class EvaluationMetrics:
    """Container for evaluation metrics of a single output."""
    
    company_name: str
    company_slug: str
    pipeline_type: str  # "structured" or "rag"
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    
    # Metrics (0-3 scale)
    factual_accuracy: Optional[int] = None
    
    # Metrics (0-2 scale)
    schema_compliance: Optional[int] = None
    provenance_quality: Optional[int] = None
    hallucination_detection: Optional[int] = None
    
    # Metrics (0-1 scale)
    readability: Optional[int] = None
    
    # Ranking metric
    mrr_score: Optional[float] = None
    
    # Notes and justification
    notes: str = ""
    
    def __post_init__(self):
        """Validate metrics on initialization."""
        self.validate()
    
    def validate(self) -> bool:
        """Validate all metrics are in valid ranges."""
        validators = {
            "factual_accuracy": (0, 3),
            "schema_compliance": (0, 2),
            "provenance_quality": (0, 2),
            "hallucination_detection": (0, 2),
            "readability": (0, 1),
            "mrr_score": (0.0, 1.0),
        }
        
        errors = []
        for field_name, (min_val, max_val) in validators.items():
            value = getattr(self, field_name)
            if value is not None:
                if not (min_val <= value <= max_val):
                    errors.append(
                        f"{field_name}={value} not in range [{min_val}, {max_val}]"
                    )
        
        if errors:
            logger.warning(f"Validation errors for {self.company_slug}/{self.pipeline_type}: {', '.join(errors)}")
            return False
        
        return True
    
    def get_total_score(self) -> Optional[float]:
        """
        Calculate total score out of 14 (max sum of all metrics).
        
        Max scores:
        - Factual Accuracy: 3
        - Schema Compliance: 2
        - Provenance Quality: 2
        - Hallucination Detection: 2
        - Readability: 1
        - MRR: 2 (scaled from 0-1 to 0-2 for comparison)
        
        Returns:
            Total score or None if any metric is missing
        """
        if any(m is None for m in [
            self.factual_accuracy,
            self.schema_compliance,
            self.provenance_quality,
            self.hallucination_detection,
            self.readability,
            self.mrr_score
        ]):
            return None
        
        # Scale MRR to 0-2 range for comparison
        mrr_scaled = self.mrr_score * 2
        
        total = (
            self.factual_accuracy +
            self.schema_compliance +
            self.provenance_quality +
            self.hallucination_detection +
            self.readability +
            mrr_scaled
        )
        
        return total
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        data = asdict(self)
        data["total_score"] = self.get_total_score()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvaluationMetrics":
        """Create from dictionary."""
        # Remove total_score if present (it's calculated)
        data_copy = {k: v for k, v in data.items() if k != "total_score"}
        return cls(**data_copy)


@dataclass
class ComparisonResult:
    """Comparison of metrics between two pipelines."""
    
    company_name: str
    company_slug: str
    structured: EvaluationMetrics
    rag: EvaluationMetrics
    
    def get_winner(self, metric_name: str) -> Optional[str]:
        """
        Get which pipeline wins for a specific metric.
        
        Args:
            metric_name: Name of metric (e.g., "factual_accuracy")
        
        Returns:
            "structured", "rag", or "tie"
        """
        struct_val = getattr(self.structured, metric_name, None)
        rag_val = getattr(self.rag, metric_name, None)
        
        if struct_val is None or rag_val is None:
            return None
        
        if struct_val > rag_val:
            return "structured"
        elif rag_val > struct_val:
            return "rag"
        else:
            return "tie"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "company_name": self.company_name,
            "company_slug": self.company_slug,
            "structured": self.structured.to_dict(),
            "rag": self.rag.to_dict(),
            "winners": {
                "factual_accuracy": self.get_winner("factual_accuracy"),
                "schema_compliance": self.get_winner("schema_compliance"),
                "provenance_quality": self.get_winner("provenance_quality"),
                "hallucination_detection": self.get_winner("hallucination_detection"),
                "readability": self.get_winner("readability"),
                "mrr_score": self.get_winner("mrr_score"),
            }
        }


def calculate_mrr(
    ranked_facts: List[Dict[str, Any]],
    relevant_threshold: float = 0.7
) -> float:
    """
    Calculate Mean Reciprocal Ranking (MRR) for a list of facts.
    
    MRR measures how well highly relevant information is ranked.
    Formula: MRR = 1/rank_of_first_relevant_item
    
    Args:
        ranked_facts: List of dicts with 'relevance_score' (0-1)
                     and optionally 'rank', 'text', 'source'
        relevant_threshold: Minimum relevance to consider "relevant" (default: 0.7)
    
    Returns:
        MRR score (0-1). Higher is better.
        
    Examples:
        # Perfect ranking (first fact most relevant)
        >>> calculate_mrr([{"relevance_score": 0.95}, {"relevance_score": 0.5}])
        1.0
        
        # Good ranking (second fact most relevant)
        >>> calculate_mrr([{"relevance_score": 0.5}, {"relevance_score": 0.95}])
        0.5
        
        # No relevant facts found
        >>> calculate_mrr([{"relevance_score": 0.3}, {"relevance_score": 0.4}])
        0.0
    """
    if not ranked_facts:
        return 0.0
    
    # Find first relevant fact
    for rank, fact in enumerate(ranked_facts, start=1):
        relevance = fact.get("relevance_score", 0.0)
        if relevance >= relevant_threshold:
            mrr = 1.0 / rank
            logger.debug(f"MRR: Found relevant fact at rank {rank}, MRR={mrr:.3f}")
            return min(mrr, 1.0)  # Cap at 1.0
    
    # No relevant facts found
    logger.debug("MRR: No relevant facts found above threshold")
    return 0.0


def calculate_aggregate_mrr(
    pipeline_results: List[Dict[str, Any]]
) -> float:
    """
    Calculate aggregate MRR across multiple evaluation results.
    
    Args:
        pipeline_results: List of results with 'mrr_score'
    
    Returns:
        Average MRR across all results
    """
    if not pipeline_results:
        return 0.0
    
    scores = [r.get("mrr_score", 0.0) for r in pipeline_results]
    avg_mrr = sum(scores) / len(scores)
    
    logger.info(f"Aggregate MRR: {avg_mrr:.3f} (n={len(scores)})")
    return avg_mrr


def score_from_ground_truth(
    generated_text: str,
    ground_truth_data: Dict[str, Any],
    company_slug: str
) -> EvaluationMetrics:
    """
    Score generated output against ground truth data.
    
    This is a template function - in practice, you would customize
    the scoring logic based on your specific evaluation criteria.
    
    Args:
        generated_text: The dashboard markdown generated by pipeline
        ground_truth_data: Ground truth facts and reference material
        company_slug: Slug of the company
    
    Returns:
        EvaluationMetrics with calculated scores
    """
    metrics = EvaluationMetrics(
        company_name=ground_truth_data.get("company_name", ""),
        company_slug=company_slug,
        pipeline_type="unknown"
    )
    
    # Placeholder scoring logic
    # In practice, this would involve:
    # 1. Named entity extraction from generated_text
    # 2. Comparison against ground_truth_data["key_facts"]
    # 3. Verification of citations/provenance
    # 4. Fact ordering analysis for MRR calculation
    
    logger.warning(
        "score_from_ground_truth is a placeholder. "
        "Implement custom scoring logic for your dataset."
    )
    
    return metrics


def compare_pipelines(
    company_slug: str,
    structured_metrics: EvaluationMetrics,
    rag_metrics: EvaluationMetrics
) -> ComparisonResult:
    """
    Create a comparison between structured and RAG pipeline metrics.
    
    Args:
        company_slug: Slug of the company
        structured_metrics: Metrics for structured pipeline
        rag_metrics: Metrics for RAG pipeline
    
    Returns:
        ComparisonResult with comparison and winners
    """
    if structured_metrics.validate() and rag_metrics.validate():
        comparison = ComparisonResult(
            company_name=structured_metrics.company_name,
            company_slug=company_slug,
            structured=structured_metrics,
            rag=rag_metrics
        )
        return comparison
    
    logger.error(f"Invalid metrics for {company_slug}")
    return None


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Example MRR calculation
    print("=== MRR Calculation Examples ===\n")
    
    # Perfect ranking
    facts_perfect = [
        {"relevance_score": 0.95, "text": "Founded in 2023"},
        {"relevance_score": 0.5, "text": "Based in San Francisco"},
    ]
    mrr_perfect = calculate_mrr(facts_perfect)
    print(f"Perfect ranking MRR: {mrr_perfect:.3f}")
    
    # Sub-optimal ranking
    facts_suboptimal = [
        {"relevance_score": 0.5, "text": "Based in San Francisco"},
        {"relevance_score": 0.95, "text": "Founded in 2023"},
    ]
    mrr_suboptimal = calculate_mrr(facts_suboptimal)
    print(f"Sub-optimal ranking MRR: {mrr_suboptimal:.3f}")
    
    # No relevant facts
    facts_none = [
        {"relevance_score": 0.3, "text": "Some fact"},
        {"relevance_score": 0.4, "text": "Another fact"},
    ]
    mrr_none = calculate_mrr(facts_none)
    print(f"No relevant facts MRR: {mrr_none:.3f}")
    
    # Example metrics comparison
    print("\n=== Metrics Comparison Example ===\n")
    
    struct_metrics = EvaluationMetrics(
        company_name="World Labs",
        company_slug="world-labs",
        pipeline_type="structured",
        factual_accuracy=3,
        schema_compliance=2,
        provenance_quality=2,
        hallucination_detection=2,
        readability=1,
        mrr_score=0.95,
        notes="Excellent structured output"
    )
    
    rag_metrics = EvaluationMetrics(
        company_name="World Labs",
        company_slug="world-labs",
        pipeline_type="rag",
        factual_accuracy=2,
        schema_compliance=2,
        provenance_quality=1,
        hallucination_detection=1,
        readability=1,
        mrr_score=0.75,
        notes="Good content but some hallucinations"
    )
    
    print(f"Structured Total: {struct_metrics.get_total_score():.1f}/14")
    print(f"RAG Total: {rag_metrics.get_total_score():.1f}/14")
    
    comparison = compare_pipelines("world-labs", struct_metrics, rag_metrics)
    if comparison:
        print(f"\nWinners by metric:")
        for metric in ["factual_accuracy", "schema_compliance", "provenance_quality", 
                      "hallucination_detection", "readability", "mrr_score"]:
            winner = comparison.get_winner(metric)
            print(f"  {metric}: {winner}")
