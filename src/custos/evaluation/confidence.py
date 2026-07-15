utf-8from pydantic import BaseModel

from custos.core.config import settings

class ConfidenceReport(BaseModel):
    final_score: int
    is_blocked: bool
    is_warned: bool
    breakdown: dict[str, float]

class ConfidenceAggregator:
    """
    Combines independent evaluation signals into a single, explainable 0-100 score.
    """
    def __init__(self) -> None:
        self.weights = settings.confidence
        
    def aggregate(
        self,
        syntax_valid: bool,
        schema_coverage_score: float,
        back_translation_score: float,
        sanity_check_score: float,
        multi_query_score: float
    ) -> ConfidenceReport:
        """
        Calculates the weighted average of the confidence signals.
        If syntax is invalid, the score is immediately 0.
        """
        if not syntax_valid:
            return ConfidenceReport(
                final_score=0,
                is_blocked=True,
                is_warned=True,
                breakdown={"syntax_valid": 0.0}
            )
            
        total_weight = (
            self.weights.schema_coverage_plausibility +
            self.weights.back_translation_alignment +
            self.weights.sanity_check_pass_rate +
            self.weights.multi_query_agreement
        )
        
        weighted_sum = (
            (schema_coverage_score * self.weights.schema_coverage_plausibility) +
            (back_translation_score * self.weights.back_translation_alignment) +
            (sanity_check_score * self.weights.sanity_check_pass_rate) +
            (multi_query_score * self.weights.multi_query_agreement)
        )
        
        
        final_score = int(weighted_sum / total_weight)
        
        is_blocked = final_score < self.weights.confidence_block_threshold
        is_warned = final_score < self.weights.confidence_warning_threshold
        
        return ConfidenceReport(
            final_score=final_score,
            is_blocked=is_blocked,
            is_warned=is_warned,
            breakdown={
                "syntax_valid": 100.0,
                "schema_coverage": schema_coverage_score,
                "back_translation": back_translation_score,
                "sanity_check": sanity_check_score,
                "multi_query": multi_query_score
            }
        )
