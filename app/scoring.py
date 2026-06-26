def combine_signals(llm_score: float, stylometric_score: float) -> float:
    # Reweighted toward the LLM after calibration testing (see README).
    combined = (0.75 * llm_score) + (0.25 * stylometric_score)
    return round(max(0.0, min(1.0, combined)), 4)


def classify(combined_ai_likelihood: float):
    """
    Map combined AI-likelihood to (attribution, user-facing confidence)
    using the asymmetric thresholds from spec §2.

    Thresholds (asymmetric — high bar to accuse AI, lower bar to clear human):
        >= 0.75        -> likely_ai
        0.40 - 0.749   -> uncertain
        < 0.40         -> likely_human
    """
    score = combined_ai_likelihood

    if score >= 0.75:
        attribution = "likely_ai"
        confidence = score                       # confidence in the AI verdict
    elif score < 0.40:
        attribution = "likely_human"
        confidence = round(1.0 - score, 4)        # confidence in the human verdict
    else:
        attribution = "uncertain"
        # Peaks at 0.5 (max uncertainty), lower as it nears a boundary.
        confidence = round(1.0 - (2 * abs(score - 0.5)), 4)
        confidence = max(0.0, confidence)

    return attribution, confidence


def confidence_word(attribution: str, confidence: float) -> str:
    """Plain-language bucket for the label (spec §3)."""
    if attribution == "uncertain":
        return "low"
    if confidence >= 0.80:
        return "high"
    if confidence >= 0.60:
        return "moderate"
    return "low"