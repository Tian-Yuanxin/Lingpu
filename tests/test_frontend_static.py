from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_frontend_exposes_processing_engine_controls():
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")

    assert 'id="separation-engine"' in html
    assert 'id="transcription-engine"' in html
    assert "/api/engines" in js
    assert "engineId: els.separationEngine.value" in js
    assert "engineId: els.transcriptionEngine.value" in js
