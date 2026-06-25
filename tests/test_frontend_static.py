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


def test_frontend_exposes_recent_project_controls():
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")

    assert 'id="recent-projects"' in html
    assert 'id="open-project-button"' in html
    assert "/api/projects" in js
    assert "loadProjects()" in js


def test_frontend_exposes_score_settings_editor():
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")

    assert 'id="score-settings-form"' in html
    assert 'id="score-tempo"' in html
    assert 'id="score-time-signature"' in html
    assert 'id="score-key-signature"' in html
    assert 'id="score-quantization"' in html
    assert 'id="score-tempo" name="tempo" type="number" min="40" max="240" step="1" value="120" required' in html
    assert '<option value="3/4">3/4</option>' in html
    assert '<option value="F#">F#</option>' in html
    assert "/score-settings" in js
    assert "scoreSettingsBody" in js
    assert 'timeSignature: els.scoreTimeSignature.value' in js
    assert 'keySignature: els.scoreKeySignature.value' in js


def test_frontend_transcribes_selected_stem():
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")

    assert 'aria-label="Stem list"' in html
    assert "selectedStemId" in js
    assert "selectStem(stem.id)" in js
    assert "setProject(project, project.stems?.[0]?.id || null)" in js
    assert "stemId: selectedStemId" in js
    assert "state.project.stems[0].id" not in js


def test_frontend_exposes_note_playback_controls():
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")

    assert 'id="note-play-button"' in html
    assert 'id="note-stop-button"' in html
    assert 'id="playback-time"' in html
    assert 'id="playback-playhead"' in html
    assert "AudioContext" in js
    assert "schedulePlaybackNotes" in js
    assert "stopPlayback" in js


def test_frontend_windows_dense_score_and_scrolls_piano_roll():
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    css = (ROOT / "frontend" / "styles.css").read_text(encoding="utf-8")
    js = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")

    assert 'id="view-prev-button"' in html
    assert 'id="view-next-button"' in html
    assert 'id="view-window-label"' in html
    assert "visibleNotes()" in js
    assert "MAX_SCORE_NOTES" in js
    assert "advanceViewWindow" in js
    assert "overflow-x: auto" in css
    assert ".piano-roll-track" in css
