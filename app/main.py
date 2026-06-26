import uuid
from flask import Flask, request, jsonify

from app.audit import init_db, write_entry, get_log
from app.signals import llm_signal, stylometric_signal
from app.scoring import combine_signals, classify, confidence_word

app = Flask(__name__)
init_db()


# --- Pipeline dispatcher: runs both signals for text ------------------------
def run_pipeline(text: str, content_type: str = "text") -> dict:
    """Selects and runs detection signals based on content_type.
    The content_type seam lets stretch features (e.g. metadata) snap in
    later without touching the text path."""
    if content_type == "text":
        return {
            "llm": llm_signal(text),
            "stylometric": stylometric_signal(text),
        }
    raise ValueError(f"Unsupported content_type: {content_type}")


# --- Temporary label (real variants arrive in M5) ---------------------------
def placeholder_label(attribution: str, conf_word: str) -> str:
    return f"[PLACEHOLDER] {attribution} (confidence: {conf_word}) — final text in M5."


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

    # Run detection pipeline (both signals)
    try:
        results = run_pipeline(text, content_type)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    llm_score = results["llm"]["ai_likelihood"]
    stylo_score = results["stylometric"]["ai_likelihood"]

    # Combine signals -> calibrated confidence -> attribution
    combined = combine_signals(llm_score, stylo_score)
    attribution, confidence = classify(combined)
    conf_word = confidence_word(attribution, confidence)
    label = placeholder_label(attribution, conf_word)

    # Structured audit entry (both signals + combined score)
    write_entry(
        content_id=content_id,
        creator_id=creator_id,
        event_type="classification",
        attribution=attribution,
        confidence=confidence,
        signals={
            "llm_score": llm_score,
            "stylometric_score": stylo_score,
            "combined_ai_likelihood": combined,
            "llm_rationale": results["llm"]["rationale"],
        },
        status="classified",
    )

    return jsonify({
        "content_id": content_id,
        "attribution": attribution,
        "confidence": confidence,
        "label": label,
        "signals": {
            "llm_score": llm_score,
            "stylometric_score": stylo_score,
            "combined_ai_likelihood": combined,
        },
        "status": "classified",
    }), 200


@app.route("/log", methods=["GET"])
def log():
    return jsonify({"entries": get_log()}), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/", methods=["GET"])
def index():
    return jsonify({
        "service": "Provenance Guard",
        "endpoints": {
            "POST /submit": "Submit text for attribution analysis",
            "GET /log": "View the audit log",
            "GET /health": "Health check",
        }
    }), 200


if __name__ == "__main__":
    app.run(debug=True, port=5000)