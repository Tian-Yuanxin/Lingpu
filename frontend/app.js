const SCORE_WINDOW_SECONDS = 16;
const MAX_SCORE_NOTES = 180;
const PIANO_ROLL_PIXELS_PER_SECOND = 54;

const state = {
  project: null,
  projects: [],
  engines: [],
  busy: false,
  selectedStemId: null,
  viewStartSec: 0,
  stemMixer: {
    isPlaying: false,
    currentTimeSec: 0,
    tracks: {},
    audioElements: new Map(),
    animationFrameId: null,
  },
  playback: {
    audioContext: null,
    masterGain: null,
    isPlaying: false,
    startOffsetSec: 0,
    startedAtSec: 0,
    scheduledNodes: [],
    animationFrameId: null,
  },
};

const els = {
  uploadForm: document.querySelector("#upload-form"),
  audioFile: document.querySelector("#audio-file"),
  recentProjects: document.querySelector("#recent-projects"),
  openProjectButton: document.querySelector("#open-project-button"),
  separationEngine: document.querySelector("#separation-engine"),
  separateButton: document.querySelector("#separate-button"),
  transcriptionEngine: document.querySelector("#transcription-engine"),
  transcribeButton: document.querySelector("#transcribe-button"),
  scoreSettingsForm: document.querySelector("#score-settings-form"),
  scoreSettingsFieldset: document.querySelector("#score-settings-fieldset"),
  scoreTempo: document.querySelector("#score-tempo"),
  scoreTimeSignature: document.querySelector("#score-time-signature"),
  scoreKeySignature: document.querySelector("#score-key-signature"),
  scoreQuantization: document.querySelector("#score-quantization"),
  exportMidi: document.querySelector("#export-midi"),
  exportMusicxml: document.querySelector("#export-musicxml"),
  exportPdf: document.querySelector("#export-pdf"),
  statusLine: document.querySelector("#status-line"),
  projectTitle: document.querySelector("#project-title"),
  projectMeta: document.querySelector("#project-meta"),
  stemStrip: document.querySelector("#stem-strip"),
  stemPlayButton: document.querySelector("#stem-play-button"),
  stemStopButton: document.querySelector("#stem-stop-button"),
  stemTime: document.querySelector("#stem-time"),
  stemPlayhead: document.querySelector("#stem-playhead"),
  notePlayButton: document.querySelector("#note-play-button"),
  noteStopButton: document.querySelector("#note-stop-button"),
  playbackTime: document.querySelector("#playback-time"),
  playbackPlayhead: document.querySelector("#playback-playhead"),
  viewPrevButton: document.querySelector("#view-prev-button"),
  viewNextButton: document.querySelector("#view-next-button"),
  viewWindowLabel: document.querySelector("#view-window-label"),
  scoreSettings: document.querySelector("#score-settings"),
  scoreSvg: document.querySelector("#score-svg"),
  pianoRoll: document.querySelector("#piano-roll"),
  noteCount: document.querySelector("#note-count"),
  notesBody: document.querySelector("#notes-body"),
  saveNotes: document.querySelector("#save-notes"),
};

els.uploadForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = els.audioFile.files[0];
  if (!file) return;

  const body = new FormData();
  body.append("file", file);

  await runTask("Creating project...", async () => {
    const project = await api("/api/projects", { method: "POST", body });
    setProject(project, project.stems?.[0]?.id || null);
    rememberProject(project);
    setStatus("Project created. Run separation next.");
    render();
  });
});

els.openProjectButton.addEventListener("click", () => {
  const project = state.projects.find((candidate) => candidate.id === els.recentProjects.value);
  if (!project) return;

  setProject(project);
  setStatus("Project opened.");
  render();
});

els.separateButton.addEventListener("click", async () => {
  if (!state.project) return;
  await runTask("Separating stems...", async () => {
    const project = await api(`/api/projects/${state.project.id}/separate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ engineId: els.separationEngine.value }),
    });
    setProject(project, project.stems?.[0]?.id || null);
    rememberProject(project);
    setStatus(state.project.message || "Stem separation finished.");
    render();
  });
});

els.transcribeButton.addEventListener("click", async () => {
  if (!state.project || !state.selectedStemId) return;
  const selectedStemId = state.selectedStemId;
  await runTask("Transcribing notes...", async () => {
    const project = await api(`/api/projects/${state.project.id}/transcribe`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ stemId: selectedStemId, engineId: els.transcriptionEngine.value }),
    });
    setProject(project, selectedStemId);
    rememberProject(project);
    setStatus(state.project.message || "Transcription finished.");
    render();
  });
});

els.saveNotes.addEventListener("click", async () => {
  if (!state.project) return;
  const selectedStemId = state.selectedStemId;
  await runTask("Saving edits...", async () => {
    const project = await api(`/api/projects/${state.project.id}/notes`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ notes: state.project.notes }),
    });
    setProject(project, selectedStemId);
    rememberProject(project);
    setStatus("Note edits saved.");
    render();
  });
});

els.scoreSettingsForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.project) return;
  const selectedStemId = state.selectedStemId;

  await runTask("Saving score settings...", async () => {
    const project = await api(`/api/projects/${state.project.id}/score-settings`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(scoreSettingsBody()),
    });
    setProject(project, selectedStemId);
    rememberProject(project);
    setStatus("Score settings saved.");
    render();
  });
});

els.exportMidi.addEventListener("click", () => download("midi"));
els.exportMusicxml.addEventListener("click", () => download("musicxml"));
els.exportPdf.addEventListener("click", () => download("pdf"));
els.stemPlayButton.addEventListener("click", () => toggleStemPlayback());
els.stemStopButton.addEventListener("click", () => stopStemPlayback());
els.notePlayButton.addEventListener("click", () => {
  if (state.playback.isPlaying) {
    pausePlayback();
  } else {
    startPlayback();
  }
});
els.noteStopButton.addEventListener("click", () => stopPlayback(true));
els.viewPrevButton.addEventListener("click", () => advanceViewWindow(-1));
els.viewNextButton.addEventListener("click", () => advanceViewWindow(1));

loadEngines();
loadProjects();

async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    let detail = `Request failed with ${response.status}`;
    try {
      const payload = await response.json();
      detail = payload.detail || detail;
    } catch (_error) {
      // Leave the generic message when the response is not JSON.
    }
    throw new Error(detail);
  }
  return response.json();
}

async function runTask(message, task) {
  setBusy(true, message);
  try {
    await task();
  } catch (error) {
    setStatus(error.message);
  } finally {
    setBusy(false);
  }
}

function setBusy(isBusy, message) {
  state.busy = isBusy;
  if (message) setStatus(message);
  renderButtons();
}

function setStatus(message) {
  els.statusLine.textContent = message;
}

function render() {
  renderEngineOptions();
  renderRecentProjects();
  renderProjectHeader();
  renderScoreSettingsForm();
  renderStems();
  renderStemMixerTransport();
  renderPlayback();
  renderScore();
  renderPianoRoll();
  renderNotesTable();
  renderButtons();
}

async function loadEngines() {
  try {
    state.engines = await api("/api/engines");
    render();
  } catch (error) {
    setStatus(`Could not load engine list: ${error.message}`);
  }
}

async function loadProjects() {
  try {
    state.projects = await api("/api/projects");
    render();
  } catch (error) {
    setStatus(`Could not load recent projects: ${error.message}`);
  }
}

function renderEngineOptions() {
  renderEngineSelect(els.separationEngine, "separation", "local-fallback");
  renderEngineSelect(els.transcriptionEngine, "transcription", "local-placeholder");
}

function renderEngineSelect(select, kind, fallbackId) {
  const previous = select.value || fallbackId;
  const engines = state.engines.filter((engine) => engine.kind === kind);
  select.replaceChildren();

  for (const engine of engines) {
    const option = document.createElement("option");
    option.value = engine.id;
    option.textContent = engine.available ? engine.label : `${engine.label} (not installed)`;
    option.disabled = !engine.available && engine.id !== fallbackId;
    option.title = engine.detail;
    select.append(option);
  }

  const hasPrevious = engines.some((engine) => engine.id === previous && (engine.available || engine.id === fallbackId));
  select.value = hasPrevious ? previous : fallbackId;
}

function renderRecentProjects() {
  const preferred = state.project?.id || els.recentProjects.value || "";
  els.recentProjects.replaceChildren();

  if (state.projects.length === 0) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "No recent projects";
    els.recentProjects.append(option);
    return;
  }

  for (const project of state.projects) {
    const option = document.createElement("option");
    option.value = project.id;
    option.textContent = project.title || project.originalFilename || project.id;
    els.recentProjects.append(option);
  }

  const hasPreferred = state.projects.some((project) => project.id === preferred);
  els.recentProjects.value = hasPreferred ? preferred : state.projects[0].id;
}

function renderProjectHeader() {
  const project = state.project;
  if (!project) {
    els.projectTitle.textContent = "Waiting for audio";
    els.projectMeta.textContent = "Upload a WAV, MP3, or M4A file.";
    els.scoreSettings.textContent = "120 BPM / 4/4 / C / 1/16";
    return;
  }

  els.projectTitle.textContent = project.title;
  els.projectMeta.textContent = `${project.status} / ${project.originalFilename}`;
  const settings = currentScoreSettings();
  els.scoreSettings.textContent = `${settings.tempo} BPM / ${settings.timeSignature} / ${settings.keySignature} / ${settings.quantization}`;
}

function renderPlayback() {
  const notes = state.project?.notes || [];
  const windowRange = scoreWindowRange();
  const totalDuration = getNotesDuration(notes);

  if (!state.playback.isPlaying && notes.length > 0 && state.playback.startOffsetSec === 0) {
    state.playback.startOffsetSec = state.viewStartSec;
  }

  const currentSec = playbackPositionSec();
  els.viewWindowLabel.textContent = `${formatSeconds(windowRange.start)}-${formatSeconds(windowRange.end)}`;
  els.playbackTime.textContent = formatSeconds(currentSec);
  updatePlaybackPlayhead(currentSec);

  els.notePlayButton.textContent = state.playback.isPlaying ? "Pause" : "Play";
  els.notePlayButton.disabled = state.busy || notes.length === 0;
  els.noteStopButton.disabled = state.busy || notes.length === 0;
  els.viewPrevButton.disabled = state.busy || notes.length === 0 || windowRange.start <= 0;
  els.viewNextButton.disabled = state.busy || notes.length === 0 || windowRange.end >= totalDuration;
}

function renderScoreSettingsForm() {
  const settings = currentScoreSettings();
  els.scoreTempo.value = String(settings.tempo);
  els.scoreTimeSignature.value = settings.timeSignature;
  els.scoreKeySignature.value = settings.keySignature;
  els.scoreQuantization.value = settings.quantization;
}

function renderStems() {
  const project = state.project;
  const stems = project?.stems || [];
  els.stemStrip.replaceChildren();
  syncStemAudioElements();

  if (stems.length === 0) {
    const empty = document.createElement("div");
    empty.className = "stem-empty";
    empty.innerHTML = "<strong>No stems yet</strong><span>Run separation to create the first playable stem.</span>";
    els.stemStrip.append(empty);
    return;
  }

  for (const stem of stems) {
    const trackState = state.stemMixer.tracks[stem.id];
    const item = document.createElement("article");
    item.className = [
      "track-row",
      stem.id === state.selectedStemId ? "is-selected" : "",
      trackState.enabled ? "" : "is-muted",
    ].filter(Boolean).join(" ");
    item.setAttribute("aria-selected", stem.id === state.selectedStemId ? "true" : "false");

    const meter = document.createElement("div");
    meter.className = "track-meter";
    meter.style.transform = `scaleX(${trackState.enabled ? trackState.volume : 0})`;

    const identity = document.createElement("div");
    identity.className = "track-identity";

    const label = document.createElement("strong");
    label.textContent = stem.label;

    const engine = document.createElement("span");
    engine.textContent = stem.engine;

    identity.append(label, engine);

    const enabledLabel = document.createElement("label");
    enabledLabel.className = "track-toggle";

    const enabled = document.createElement("input");
    enabled.type = "checkbox";
    enabled.checked = trackState.enabled;
    enabled.setAttribute("aria-label", `Play ${stem.label}`);
    enabled.addEventListener("change", () => setStemEnabled(stem.id, enabled.checked));

    const enabledText = document.createElement("span");
    enabledText.textContent = "On";
    enabledLabel.append(enabled, enabledText);

    const volumeWrap = document.createElement("label");
    volumeWrap.className = "track-volume";

    const volumeLabel = document.createElement("span");
    volumeLabel.textContent = "Vol";

    const volume = document.createElement("input");
    volume.type = "range";
    volume.min = "0";
    volume.max = "1";
    volume.step = "0.01";
    volume.value = String(trackState.volume);
    volume.disabled = !trackState.enabled;
    volume.setAttribute("aria-label", `${stem.label} volume`);

    const volumeValue = document.createElement("output");
    volumeValue.textContent = `${Math.round(trackState.volume * 100)}%`;
    volume.addEventListener("input", () => {
      const nextVolume = setStemVolume(stem.id, Number(volume.value));
      volumeValue.textContent = `${Math.round(nextVolume * 100)}%`;
      meter.style.transform = `scaleX(${trackState.enabled ? nextVolume : 0})`;
    });
    volumeWrap.append(volumeLabel, volume, volumeValue);

    const selectButton = document.createElement("button");
    selectButton.type = "button";
    selectButton.className = "track-score-select";
    selectButton.textContent = stem.id === state.selectedStemId ? "Selected" : "Use for score";
    selectButton.addEventListener("click", () => selectStem(stem.id));

    const audio = state.stemMixer.audioElements.get(stem.id);
    if (audio) item.append(audio);

    item.append(meter, identity, enabledLabel, volumeWrap, selectButton);
    els.stemStrip.append(item);
  }
}

function renderStemMixerTransport() {
  const stems = state.project?.stems || [];
  const hasStems = stems.length > 0;
  const duration = getStemMixerDuration();
  const currentSec = currentStemPositionSec();
  const percent = duration > 0 ? clamp(currentSec / duration, 0, 1) * 100 : 0;

  els.stemPlayButton.textContent = state.stemMixer.isPlaying ? "Pause" : "Play";
  els.stemPlayButton.disabled = state.busy || !hasStems;
  els.stemStopButton.disabled = state.busy || !hasStems;
  els.stemTime.textContent = `${formatClock(currentSec)} / ${duration > 0 ? formatClock(duration) : "--:--"}`;
  els.stemPlayhead.style.width = `${percent}%`;
}

function syncStemAudioElements() {
  const project = state.project;
  const stems = project?.stems || [];
  const stemIds = new Set(stems.map((stem) => stem.id));

  for (const [stemId, audio] of state.stemMixer.audioElements) {
    if (!stemIds.has(stemId)) {
      audio.pause();
      state.stemMixer.audioElements.delete(stemId);
      delete state.stemMixer.tracks[stemId];
    }
  }

  for (const stem of stems) {
    if (!state.stemMixer.tracks[stem.id]) {
      state.stemMixer.tracks[stem.id] = { enabled: true, volume: 1 };
    }

    let audio = state.stemMixer.audioElements.get(stem.id);
    if (!audio) {
      audio = document.createElement("audio");
      audio.className = "stem-audio";
      audio.preload = "metadata";
      audio.addEventListener("loadedmetadata", () => renderStemMixerTransport());
      audio.addEventListener("timeupdate", () => {
        if (state.stemMixer.isPlaying) renderStemMixerTransport();
      });
      audio.addEventListener("ended", () => handleStemAudioEnded());
      state.stemMixer.audioElements.set(stem.id, audio);
    }

    const src = `/api/projects/${project.id}/files/${encodeURIComponent(stem.audio.path)}`;
    if (!audio.src.endsWith(src)) audio.src = src;
    updateStemAudioVolume(stem.id);
  }
}

function toggleStemPlayback() {
  if (state.stemMixer.isPlaying) {
    pauseStemPlayback();
  } else {
    startStemPlayback();
  }
}

async function startStemPlayback() {
  const stems = state.project?.stems || [];
  if (stems.length === 0) return;
  syncStemAudioElements();

  const activeAudios = activeStemAudioElements();
  if (activeAudios.length === 0) {
    setStatus("Enable at least one stem to play.");
    return;
  }

  const duration = getStemMixerDuration();
  const startSec = duration > 0
    ? clamp(state.stemMixer.currentTimeSec, 0, Math.max(0, duration - 0.02))
    : state.stemMixer.currentTimeSec;

  try {
    for (const audio of state.stemMixer.audioElements.values()) {
      audio.pause();
      setAudioCurrentTime(audio, startSec);
    }

    const results = await Promise.allSettled(activeAudios.map((audio) => audio.play()));
    const hasPlayback = results.some((result) => result.status === "fulfilled");
    if (!hasPlayback) {
      const reason = results.find((result) => result.status === "rejected")?.reason;
      throw new Error(reason?.message || "Browser blocked audio playback.");
    }

    state.stemMixer.isPlaying = true;
    state.stemMixer.currentTimeSec = startSec;
    tickStemPlayback();
    setStatus("Playing enabled stems.");
    renderStemMixerTransport();
    renderStems();
  } catch (error) {
    state.stemMixer.isPlaying = false;
    cancelStemPlaybackFrame();
    pauseAllStemAudio();
    setStatus(`Could not start stem playback: ${error.message}`);
    renderStemMixerTransport();
  }
}

function pauseStemPlayback() {
  if (!state.stemMixer.isPlaying) return;
  state.stemMixer.currentTimeSec = currentStemPositionSec();
  state.stemMixer.isPlaying = false;
  cancelStemPlaybackFrame();
  pauseAllStemAudio();
  setStatus("Stem playback paused.");
  renderStemMixerTransport();
  renderStems();
}

function stopStemPlayback() {
  state.stemMixer.isPlaying = false;
  state.stemMixer.currentTimeSec = 0;
  cancelStemPlaybackFrame();
  for (const audio of state.stemMixer.audioElements.values()) {
    audio.pause();
    setAudioCurrentTime(audio, 0);
  }
  setStatus("Stem playback stopped.");
  renderStemMixerTransport();
  renderStems();
}

function setStemEnabled(stemId, enabled) {
  const track = state.stemMixer.tracks[stemId];
  if (!track) return;
  track.enabled = enabled;
  const audio = state.stemMixer.audioElements.get(stemId);
  if (audio) {
    updateStemAudioVolume(stemId);
    if (state.stemMixer.isPlaying) {
      if (enabled) {
        setAudioCurrentTime(audio, currentStemPositionSec());
        audio.play().catch((error) => setStatus(`Could not add stem to playback: ${error.message}`));
      } else {
        audio.pause();
      }
    }
  }
  if (state.stemMixer.isPlaying && activeStemAudioElements().length === 0) pauseStemPlayback();
  renderStems();
  renderStemMixerTransport();
}

function setStemVolume(stemId, volume) {
  const track = state.stemMixer.tracks[stemId];
  if (!track) return 0;
  track.volume = clamp(volume, 0, 1);
  updateStemAudioVolume(stemId);
  return track.volume;
}

function updateStemAudioVolume(stemId) {
  const audio = state.stemMixer.audioElements.get(stemId);
  const track = state.stemMixer.tracks[stemId];
  if (!audio || !track) return;
  audio.volume = track.enabled ? track.volume : 0;
}

function tickStemPlayback() {
  if (!state.stemMixer.isPlaying) return;
  state.stemMixer.currentTimeSec = currentStemPositionSec();

  const duration = getStemMixerDuration();
  if (duration > 0 && state.stemMixer.currentTimeSec >= duration - 0.05) {
    stopStemPlayback();
    return;
  }

  renderStemMixerTransport();
  state.stemMixer.animationFrameId = window.requestAnimationFrame(tickStemPlayback);
}

function cancelStemPlaybackFrame() {
  if (state.stemMixer.animationFrameId) {
    window.cancelAnimationFrame(state.stemMixer.animationFrameId);
    state.stemMixer.animationFrameId = null;
  }
}

function handleStemAudioEnded() {
  if (!state.stemMixer.isPlaying) return;
  const stillPlaying = activeStemAudioElements().some((audio) => !audio.paused && !audio.ended);
  if (!stillPlaying) stopStemPlayback();
}

function pauseAllStemAudio() {
  for (const audio of state.stemMixer.audioElements.values()) {
    audio.pause();
  }
}

function activeStemAudioElements() {
  const stems = state.project?.stems || [];
  return stems
    .filter((stem) => state.stemMixer.tracks[stem.id]?.enabled)
    .map((stem) => state.stemMixer.audioElements.get(stem.id))
    .filter(Boolean);
}

function currentStemPositionSec() {
  if (!state.stemMixer.isPlaying) return state.stemMixer.currentTimeSec || 0;
  const clock = activeStemAudioElements().find((audio) => !audio.paused) || activeStemAudioElements()[0];
  return clock ? clock.currentTime : state.stemMixer.currentTimeSec || 0;
}

function getStemMixerDuration() {
  const durations = [...state.stemMixer.audioElements.values()]
    .map((audio) => audio.duration)
    .filter((duration) => Number.isFinite(duration) && duration > 0);
  return durations.length > 0 ? Math.max(...durations) : 0;
}

function setAudioCurrentTime(audio, seconds) {
  try {
    audio.currentTime = seconds;
  } catch (_error) {
    // Metadata may not be loaded yet; playback will still start from the browser's current position.
  }
}

function resetStemMixer() {
  state.stemMixer.isPlaying = false;
  state.stemMixer.currentTimeSec = 0;
  cancelStemPlaybackFrame();
  for (const audio of state.stemMixer.audioElements.values()) {
    audio.pause();
  }
  state.stemMixer.audioElements.clear();
  state.stemMixer.tracks = {};
}

function renderScore() {
  const notes = visibleNotes();
  const allNotes = state.project?.notes || [];
  const windowRange = scoreWindowRange();
  const windowDuration = Math.max(1, windowRange.end - windowRange.start);
  const staffTop = 72;
  const lineGap = 14;
  const staffLeft = 58;
  const staffRight = 872;
  const elements = [];

  for (let line = 0; line < 5; line += 1) {
    const y = staffTop + line * lineGap;
    elements.push(`<line x1="${staffLeft}" y1="${y}" x2="${staffRight}" y2="${y}" stroke="#475049" stroke-width="1.4" />`);
  }

  for (let beat = Math.ceil(windowRange.start); beat <= windowRange.end; beat += 1) {
    const x = staffLeft + ((beat - windowRange.start) / windowDuration) * (staffRight - staffLeft);
    elements.push(`<line x1="${x}" y1="50" x2="${x}" y2="166" stroke="#d0d8d2" stroke-width="1" />`);
  }

  elements.push(`<text x="${staffLeft}" y="32" fill="#69736c" font-size="13">${htmlEscape(String(notes.length))}/${htmlEscape(String(allNotes.length))} notes in window</text>`);

  notes.forEach((note) => {
    const x = staffLeft + ((note.startSec - windowRange.start) / windowDuration) * (staffRight - staffLeft);
    const y = pitchToStaffY(note.pitch, staffTop, lineGap);
    elements.push(`<ellipse class="score-note" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" rx="6.5" ry="4.8" transform="rotate(-16 ${x.toFixed(1)} ${y.toFixed(1)})" />`);
    if (notes.length <= 80) {
      elements.push(`<line class="score-stem" x1="${(x + 6).toFixed(1)}" y1="${y.toFixed(1)}" x2="${(x + 6).toFixed(1)}" y2="${(y - 32).toFixed(1)}" />`);
    }
  });

  if (allNotes.length === 0) {
    elements.push('<text x="58" y="210" fill="#69736c" font-size="18">No notes yet. Transcribe a stem to populate the score.</text>');
  } else if (notes.length === 0) {
    elements.push('<text x="58" y="210" fill="#69736c" font-size="18">No notes in this window.</text>');
  }

  els.scoreSvg.innerHTML = elements.join("");
}

function renderPianoRoll() {
  const notes = state.project?.notes || [];
  els.pianoRoll.replaceChildren();
  els.noteCount.textContent = `${notes.length} ${notes.length === 1 ? "note" : "notes"}`;

  if (notes.length === 0) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "Transcribed notes will appear here as editable time blocks.";
    els.pianoRoll.append(empty);
    return;
  }

  const maxEnd = getNotesDuration(notes);
  const trackWidth = Math.max(960, Math.ceil(maxEnd * PIANO_ROLL_PIXELS_PER_SECOND));
  const pitches = notes.map((note) => note.pitch);
  const maxPitch = Math.max(...pitches) + 2;
  const minPitch = Math.min(...pitches) - 2;
  const pitchSpan = Math.max(1, maxPitch - minPitch);
  const track = document.createElement("div");
  track.className = "piano-roll-track";
  track.style.width = `${trackWidth}px`;

  for (const note of notes) {
    const block = document.createElement("div");
    block.className = "roll-note";
    block.title = `MIDI ${note.pitch}`;
    block.style.left = `${note.startSec * PIANO_ROLL_PIXELS_PER_SECOND}px`;
    block.style.width = `${Math.max(10, (note.endSec - note.startSec) * PIANO_ROLL_PIXELS_PER_SECOND)}px`;
    block.style.top = `${8 + ((maxPitch - note.pitch) / pitchSpan) * 188}px`;
    track.append(block);
  }

  const playhead = document.createElement("div");
  playhead.className = "roll-playhead";
  playhead.style.left = `${playbackPositionSec() * PIANO_ROLL_PIXELS_PER_SECOND}px`;
  track.append(playhead);
  els.pianoRoll.append(track);
}

function renderNotesTable() {
  const notes = state.project?.notes || [];
  els.notesBody.replaceChildren();

  if (notes.length === 0) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 4;
    cell.className = "empty-state";
    cell.textContent = "No editable notes yet.";
    row.append(cell);
    els.notesBody.append(row);
    return;
  }

  notes.forEach((note, index) => {
    const row = document.createElement("tr");
    row.append(
      inputCell(note.pitch, "pitch", index, 1, 127),
      inputCell(note.startSec, "startSec", index, 0, 999),
      inputCell(note.endSec, "endSec", index, 0.01, 999),
      deleteCell(index),
    );
    els.notesBody.append(row);
  });
}

function inputCell(value, field, index, min, max) {
  const cell = document.createElement("td");
  const input = document.createElement("input");
  input.type = "number";
  input.min = String(min);
  input.max = String(max);
  input.step = field === "pitch" ? "1" : "0.01";
  input.value = field === "pitch" ? String(value) : Number(value).toFixed(2);
  input.addEventListener("change", () => {
    const next = Number(input.value);
    if (!Number.isFinite(next)) return;
    state.project.notes[index][field] = field === "pitch" ? Math.round(next) : next;
    if (state.project.notes[index].endSec <= state.project.notes[index].startSec) {
      state.project.notes[index].endSec = Number((state.project.notes[index].startSec + 0.1).toFixed(2));
    }
    renderScore();
    renderPianoRoll();
  });
  cell.append(input);
  return cell;
}

function deleteCell(index) {
  const cell = document.createElement("td");
  const button = document.createElement("button");
  button.type = "button";
  button.className = "delete-note";
  button.textContent = "x";
  button.setAttribute("aria-label", "Delete note");
  button.addEventListener("click", () => {
    state.project.notes.splice(index, 1);
    render();
  });
  cell.append(button);
  return cell;
}

function renderButtons() {
  const hasProject = Boolean(state.project);
  const hasStems = (state.project?.stems || []).length > 0;
  const hasNotes = (state.project?.notes || []).length > 0;
  const disabled = state.busy;

  els.recentProjects.disabled = disabled || state.projects.length === 0;
  els.openProjectButton.disabled = disabled || state.projects.length === 0 || !els.recentProjects.value;
  els.separationEngine.disabled = disabled || state.engines.length === 0;
  els.transcriptionEngine.disabled = disabled || state.engines.length === 0;
  els.separateButton.disabled = disabled || !hasProject;
  els.transcribeButton.disabled = disabled || !hasProject || !hasStems || !state.selectedStemId;
  els.scoreSettingsFieldset.disabled = disabled || !hasProject;
  els.stemPlayButton.disabled = disabled || !hasStems;
  els.stemStopButton.disabled = disabled || !hasStems;
  els.notePlayButton.disabled = disabled || !hasNotes;
  els.noteStopButton.disabled = disabled || !hasNotes;
  els.viewPrevButton.disabled = disabled || !hasNotes || state.viewStartSec <= 0;
  els.viewNextButton.disabled = disabled || !hasNotes || scoreWindowRange().end >= getNotesDuration(state.project?.notes || []);
  els.saveNotes.disabled = disabled || !hasProject || !hasNotes;
  els.exportMidi.disabled = disabled || !hasProject || !hasNotes;
  els.exportMusicxml.disabled = disabled || !hasProject || !hasNotes;
  els.exportPdf.disabled = disabled || !hasProject || !hasNotes;
}

function download(format) {
  if (!state.project) return;
  window.location.href = `/api/projects/${state.project.id}/export/${format}`;
}

async function startPlayback() {
  const notes = state.project?.notes || [];
  if (notes.length === 0) return;

  try {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) {
      setStatus("This browser does not support Web Audio playback.");
      return;
    }

    if (!state.playback.audioContext) {
      state.playback.audioContext = new AudioContextClass();
      state.playback.masterGain = state.playback.audioContext.createGain();
      state.playback.masterGain.gain.value = 0.22;
      state.playback.masterGain.connect(state.playback.audioContext.destination);
    }

    await state.playback.audioContext.resume();
    clearScheduledPlayback();

    const totalDuration = getNotesDuration(notes);
    let startOffset = clamp(
      state.playback.startOffsetSec || state.viewStartSec,
      0,
      totalDuration,
    );
    if (startOffset >= totalDuration) startOffset = state.viewStartSec;

    state.playback.startOffsetSec = startOffset;
    state.playback.startedAtSec = state.playback.audioContext.currentTime - startOffset;
    state.playback.isPlaying = true;
    schedulePlaybackNotes(startOffset);
    tickPlayback();
    setStatus("Playing transcribed notes.");
    renderPlayback();
    renderPianoRoll();
  } catch (error) {
    state.playback.isPlaying = false;
    clearScheduledPlayback();
    cancelPlaybackFrame();
    setStatus(`Could not start note playback: ${error.message}`);
    renderPlayback();
  }
}

function pausePlayback() {
  if (!state.playback.isPlaying) return;
  state.playback.startOffsetSec = playbackPositionSec();
  state.playback.isPlaying = false;
  clearScheduledPlayback();
  cancelPlaybackFrame();
  setStatus("Playback paused.");
  renderPlayback();
  renderPianoRoll();
}

function stopPlayback(resetToViewStart = false) {
  state.playback.isPlaying = false;
  clearScheduledPlayback();
  cancelPlaybackFrame();
  state.playback.startOffsetSec = resetToViewStart ? state.viewStartSec : 0;
  setStatus("Playback stopped.");
  renderPlayback();
  renderPianoRoll();
}

function schedulePlaybackNotes(startOffsetSec) {
  const context = state.playback.audioContext;
  const masterGain = state.playback.masterGain;
  if (!context || !masterGain) return;

  const now = context.currentTime + 0.04;
  for (const note of state.project?.notes || []) {
    if (note.endSec <= startOffsetSec) continue;
    const relativeStart = Math.max(0, note.startSec - startOffsetSec);
    const duration = Math.max(0.035, note.endSec - Math.max(note.startSec, startOffsetSec));
    const when = now + relativeStart;
    const oscillator = context.createOscillator();
    const envelope = context.createGain();
    const volume = Math.max(0.03, Math.min(0.28, (note.velocity || 90) / 127 * 0.28));

    oscillator.type = "triangle";
    oscillator.frequency.value = midiToFrequency(note.pitch);
    envelope.gain.setValueAtTime(0.0001, when);
    envelope.gain.exponentialRampToValueAtTime(volume, when + 0.012);
    envelope.gain.setTargetAtTime(0.0001, when + Math.max(0.02, duration - 0.035), 0.025);
    oscillator.connect(envelope);
    envelope.connect(masterGain);
    oscillator.start(when);
    oscillator.stop(when + duration + 0.08);
    state.playback.scheduledNodes.push(oscillator, envelope);
  }
}

function clearScheduledPlayback() {
  for (const node of state.playback.scheduledNodes) {
    try {
      if (typeof node.stop === "function") node.stop();
      if (typeof node.disconnect === "function") node.disconnect();
    } catch (_error) {
      // Nodes may already be stopped by the Web Audio clock.
    }
  }
  state.playback.scheduledNodes = [];
}

function tickPlayback() {
  if (!state.playback.isPlaying) return;
  const currentSec = playbackPositionSec();
  const totalDuration = getNotesDuration(state.project?.notes || []);
  if (currentSec >= totalDuration) {
    stopPlayback(true);
    return;
  }

  if (currentSec >= state.viewStartSec + SCORE_WINDOW_SECONDS) {
    state.viewStartSec = clamp(
      Math.floor(currentSec / SCORE_WINDOW_SECONDS) * SCORE_WINDOW_SECONDS,
      0,
      Math.max(0, totalDuration - SCORE_WINDOW_SECONDS),
    );
    renderScore();
    renderPlayback();
    renderButtons();
  }

  els.playbackTime.textContent = formatSeconds(currentSec);
  updatePlaybackPlayhead(currentSec);
  updateRollPlayhead(currentSec);
  state.playback.animationFrameId = window.requestAnimationFrame(tickPlayback);
}

function cancelPlaybackFrame() {
  if (state.playback.animationFrameId) {
    window.cancelAnimationFrame(state.playback.animationFrameId);
    state.playback.animationFrameId = null;
  }
}

function playbackPositionSec() {
  if (!state.playback.isPlaying || !state.playback.audioContext) {
    return state.playback.startOffsetSec || 0;
  }
  return Math.max(0, state.playback.audioContext.currentTime - state.playback.startedAtSec);
}

function updatePlaybackPlayhead(currentSec) {
  const totalDuration = getNotesDuration(state.project?.notes || []);
  const percent = totalDuration > 0 ? clamp(currentSec / totalDuration, 0, 1) * 100 : 0;
  els.playbackPlayhead.style.width = `${percent}%`;
}

function updateRollPlayhead(currentSec) {
  const playhead = els.pianoRoll.querySelector(".roll-playhead");
  if (!playhead) return;
  playhead.style.left = `${currentSec * PIANO_ROLL_PIXELS_PER_SECOND}px`;
}

function advanceViewWindow(direction) {
  const notes = state.project?.notes || [];
  if (notes.length === 0) return;
  const totalDuration = getNotesDuration(notes);
  state.viewStartSec = clamp(
    state.viewStartSec + direction * SCORE_WINDOW_SECONDS,
    0,
    Math.max(0, totalDuration - SCORE_WINDOW_SECONDS),
  );
  if (!state.playback.isPlaying) {
    state.playback.startOffsetSec = state.viewStartSec;
  }
  renderPlayback();
  renderScore();
  renderPianoRoll();
  renderButtons();
}

function setProject(project, preferredStemId = null) {
  const projectChanged = state.project?.id !== project?.id;
  const stemsChanged = projectChanged || !sameStemIds(state.project?.stems || [], project?.stems || []);
  const previousStemId = !projectChanged ? state.selectedStemId : null;
  if (projectChanged) {
    state.viewStartSec = 0;
    state.playback.startOffsetSec = 0;
    state.playback.isPlaying = false;
    clearScheduledPlayback();
    cancelPlaybackFrame();
  }
  if (stemsChanged) {
    resetStemMixer();
  }
  state.project = project;

  const stems = project?.stems || [];
  const candidateStemId = preferredStemId || previousStemId;
  if (stems.length === 0) {
    state.selectedStemId = null;
    return;
  }

  state.selectedStemId = stems.some((stem) => stem.id === candidateStemId) ? candidateStemId : stems[0].id;
}

function rememberProject(project) {
  if (!project) return;
  state.projects = [project, ...state.projects.filter((candidate) => candidate.id !== project.id)];
}

function sameStemIds(left, right) {
  if (left.length !== right.length) return false;
  return left.every((stem, index) => stem.id === right[index]?.id && stem.audio.path === right[index]?.audio.path);
}

function selectStem(stemId) {
  state.selectedStemId = stemId;
  renderStems();
  renderButtons();
}

function currentScoreSettings() {
  return state.project?.scoreSettings || {
    tempo: 120,
    timeSignature: "4/4",
    keySignature: "C",
    quantization: "1/16",
  };
}

function scoreSettingsBody() {
  return {
    tempo: Number(els.scoreTempo.value),
    timeSignature: els.scoreTimeSignature.value,
    keySignature: els.scoreKeySignature.value,
    quantization: els.scoreQuantization.value,
  };
}

function visibleNotes() {
  const notes = state.project?.notes || [];
  const windowRange = scoreWindowRange();
  const inWindow = notes.filter(
    (note) => note.endSec >= windowRange.start && note.startSec <= windowRange.end,
  );
  if (inWindow.length <= MAX_SCORE_NOTES) return inWindow;

  const stride = Math.ceil(inWindow.length / MAX_SCORE_NOTES);
  return inWindow.filter((_note, index) => index % stride === 0).slice(0, MAX_SCORE_NOTES);
}

function scoreWindowRange() {
  const notes = state.project?.notes || [];
  const totalDuration = getNotesDuration(notes);
  const maxStart = Math.max(0, totalDuration - SCORE_WINDOW_SECONDS);
  const start = clamp(state.viewStartSec, 0, maxStart);
  state.viewStartSec = start;
  return {
    start,
    end: Math.min(totalDuration, start + SCORE_WINDOW_SECONDS),
  };
}

function getNotesDuration(notes) {
  return Math.max(0, ...notes.map((note) => note.endSec || 0));
}

function midiToFrequency(pitch) {
  return 440 * 2 ** ((pitch - 69) / 12);
}

function formatSeconds(seconds) {
  return `${Number(seconds || 0).toFixed(2)}s`;
}

function formatClock(seconds) {
  const safeSeconds = Math.max(0, Number(seconds || 0));
  const minutes = Math.floor(safeSeconds / 60);
  const wholeSeconds = Math.floor(safeSeconds % 60);
  return `${minutes}:${String(wholeSeconds).padStart(2, "0")}`;
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function htmlEscape(value) {
  return value.replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[character]);
}

function pitchToStaffY(pitch, staffTop, lineGap) {
  const bottomLine = staffTop + lineGap * 4;
  const y = bottomLine - (pitch - 64) * 3.5;
  return Math.max(38, Math.min(178, y));
}

render();
