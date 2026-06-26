import uuid
from flask import Flask, request, jsonify

from app.audit import init_db, write_entry, get_log
from app.signals import llm_signal

app = Flask(__name__)
init_db()


# --- Pipeline dispatcher seam (M4 adds signal 2; stretch adds modalities) ---
def run_pipeline(text: str, content_type: str = "text") -> dict:
    """Selects and runs detection signals based on content_type."""
    if content_type == "text":
        sig1 = llm_signal(text)
        return {"llm": sig1}
    # Future content types (e.g. "metadata") snap in here without
    # touching the text path.
    raise ValueError(f"Unsupported content_type: {content_type}")


# --- Placeholder scoring/label (REPLACED in M4/M5) --------------------------
def placeholder_attribution(llm_score: float):
    """Temporary single-signal mapping. Real scoring arrives in M4."""
    if llm_score >= 0.75:
        return "likely_ai", llm_score
    elif llm_score < 0.40:
        return "likely_human", round(1.0 - llm_score, 4)
    return "uncertain", 0.5


def placeholder_label(attribution: str) -> str:
    return f"[PLACEHOLDER LABEL] attribution={attribution} — finalized in M4/M5."
# ----------------------------------------------------------------------------


@app.route("/submit", methods=["POST"])
def submit():
    body = request.get_json(silent=True) or {}
    text = body.get("text")
    creator_id = body.get("creator_id")
    content_type = body.get("content_type", "text")

    # Input validation
    if not text or not isinstance(text, str) or not text.strip():
        return jsonify({"error": "Field 'text' is required and must be non-empty."}), 400
    if not creator_id:
        return jsonify({"error": "Field 'creator_id' is required."}), 400

    content_id = str(uuid.uuid4())

    # Run detection pipeline (Signal 1 only for now)
    try:
        results = run_pipeline(text, content_type)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    llm = results["llm"]
    attribution, confidence = placeholder_attribution(llm["ai_likelihood"])
    label = placeholder_label(attribution)

    # Structured audit entry
    write_entry(
        content_id=content_id,
        creator_id=creator_id,
        event_type="classification",
        attribution=attribution,
        confidence=round(confidence, 4),
        signals={"llm_score": llm["ai_likelihood"],
                 "llm_rationale": llm["rationale"]},
        status="classified",
    )

    return jsonify({
        "content_id": content_id,
        "attribution": attribution,
        "confidence": round(confidence, 4),
        "label": label,
        "signals": {"llm_score": llm["ai_likelihood"]},
        "status": "classified",
    }), 200


@app.route("/log", methods=["GET"])
def log():
    return jsonify({"entries": get_log()}), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    app.run(debug=True, port=5000)