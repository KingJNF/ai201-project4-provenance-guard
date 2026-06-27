import uuid
from flask import Flask, request, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from app.audit import (init_db, write_entry, get_log,
                       get_classification, update_status)
from app.signals import llm_signal, stylometric_signal, repetition_signal
from app.scoring import combine_signals, classify, confidence_word
from app.labels import generate_label

app = Flask(__name__)
init_db()

# --- Rate limiting ----------------------------------------------------------
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://",
)


# --- Pipeline dispatcher ----------------------------------------------------
def run_pipeline(text: str, content_type: str = "text") -> dict:
    if content_type == "text":
        return {
            "llm": llm_signal(text),
            "stylometric": stylometric_signal(text),
            "repetition": repetition_signal(text),
        }
    raise ValueError(f"Unsupported content_type: {content_type}")


@app.route("/submit", methods=["POST"])
@limiter.limit("10 per minute;100 per day")
def submit():
    body = request.get_json(silent=True) or {}
    text = body.get("text")
    creator_id = body.get("creator_id")
    content_type = body.get("content_type", "text")

    if not text or not isinstance(text, str) or not text.strip():
        return jsonify({"error": "Field 'text' is required and must be non-empty."}), 400
    if not creator_id:
        return jsonify({"error": "Field 'creator_id' is required."}), 400

    content_id = str(uuid.uuid4())

    try:
        results = run_pipeline(text, content_type)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    llm_score = results["llm"]["ai_likelihood"]
    stylo_score = results["stylometric"]["ai_likelihood"]
    rep_score = results["repetition"]["ai_likelihood"]

    combined = combine_signals(llm_score, stylo_score, rep_score)
    attribution, confidence = classify(combined)
    label = generate_label(attribution, confidence)

    write_entry(
        content_id=content_id,
        creator_id=creator_id,
        event_type="classification",
        attribution=attribution,
        confidence=confidence,
        signals={
            "llm_score": llm_score,
            "stylometric_score": stylo_score,
            "repetition_score": rep_score,
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
            "repetition_score": rep_score,
            "combined_ai_likelihood": combined,
        },
        "status": "classified",
    }), 200


@app.route("/appeal", methods=["POST"])
def appeal():
    body = request.get_json(silent=True) or {}
    content_id = body.get("content_id")
    creator_reasoning = body.get("creator_reasoning")

    if not content_id:
        return jsonify({"error": "Field 'content_id' is required."}), 400
    if not creator_reasoning or not creator_reasoning.strip():
        return jsonify({"error": "Field 'creator_reasoning' is required."}), 400

    original = get_classification(content_id)
    if original is None:
        return jsonify({"error": f"No classification found for content_id {content_id}."}), 404

    # Flip status to under_review and log the appeal beside the original decision
    update_status(content_id, "under_review")
    write_entry(
        content_id=content_id,
        creator_id=original["creator_id"],
        event_type="appeal",
        attribution=original["attribution"],
        confidence=original["confidence"],
        signals=original["signals"],
        status="under_review",
        detail=creator_reasoning,
    )

    return jsonify({
        "content_id": content_id,
        "status": "under_review",
        "message": "Appeal received. Your content is now under review by a human moderator.",
        "original_attribution": original["attribution"],
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
            "POST /appeal": "Contest a classification",
            "GET /log": "View the audit log",
            "GET /health": "Health check",
        }
    }), 200


if __name__ == "__main__":
    app.run(debug=True, port=5000)