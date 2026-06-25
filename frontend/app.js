const state = {
  project: null,
  projects: [],
  engines: [],
  busy: false,
  selectedStemId: null,
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

  if (stems.length === 0) {
    const empty = document.createElement("div");
    empty.className = "stem-item";
    empty.innerHTML = "<strong>No stems yet</strong><span>Run separation to create the first playable stem.</span>";
    els.stemStrip.append(empty);
    return;
  }

  for (const stem of stems) {
    const item = document.createElement("article");
    item.className = stem.id === state.selectedStemId ? "stem-item is-selected" : "stem-item";
    item.setAttribute("aria-selected", stem.id === state.selectedStemId ? "true" : "false");

    const label = document.createElement("strong");
    label.textContent = stem.label;

    const engine = document.createElement("span");
    engine.textContent = stem.engine;

    const audio = document.createElement("audio");
    audio.controls = true;
    audio.src = `/api/projects/${project.id}/files/${encodeURIComponent(stem.audio.path)}`;

    const selectButton = document.createElement("button");
    selectButton.type = "button";
    selectButton.className = "stem-select";
    selectButton.textContent = stem.id === state.selectedStemId ? "Selected" : "Select";
    selectButton.addEventListener("click", () => selectStem(stem.id));

    item.append(label, engine, audio, selectButton);
    els.stemStrip.append(item);
  }
}

function renderScore() {
  const notes = state.project?.notes || [];
  const maxEnd = getMaxEnd(notes);
  const staffTop = 72;
  const lineGap = 14;
  const staffLeft = 58;
  const staffRight = 872;
  const elements = [];

  for (let line = 0; line < 5; line += 1) {
    const y = staffTop + line * lineGap;
    elements.push(`<line x1="${staffLeft}" y1="${y}" x2="${staffRight}" y2="${y}" stroke="#475049" stroke-width="1.4" />`);
  }

  for (let beat = 0; beat <= maxEnd; beat += 1) {
    const x = staffLeft + (beat / maxEnd) * (staffRight - staffLeft);
    elements.push(`<line x1="${x}" y1="50" x2="${x}" y2="166" stroke="#d0d8d2" stroke-width="1" />`);
  }

  notes.forEach((note) => {
    const x = staffLeft + (note.startSec / maxEnd) * (staffRight - staffLeft);
    const y = pitchToStaffY(note.pitch, staffTop, lineGap);
    elements.push(`<ellipse class="score-note" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" rx="10" ry="7" transform="rotate(-16 ${x.toFixed(1)} ${y.toFixed(1)})" />`);
    elements.push(`<line class="score-stem" x1="${(x + 9).toFixed(1)}" y1="${y.toFixed(1)}" x2="${(x + 9).toFixed(1)}" y2="${(y - 44).toFixed(1)}" />`);
  });

  if (notes.length === 0) {
    elements.push('<text x="58" y="210" fill="#69736c" font-size="18">No notes yet. Transcribe a stem to populate the score.</text>');
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

  const maxEnd = getMaxEnd(notes);
  const pitches = notes.map((note) => note.pitch);
  const maxPitch = Math.max(...pitches) + 2;
  const minPitch = Math.min(...pitches) - 2;
  const pitchSpan = Math.max(1, maxPitch - minPitch);

  for (const note of notes) {
    const block = document.createElement("div");
    block.className = "roll-note";
    block.title = `MIDI ${note.pitch}`;
    block.style.left = `${(note.startSec / maxEnd) * 100}%`;
    block.style.width = `${Math.max(1.5, ((note.endSec - note.startSec) / maxEnd) * 100)}%`;
    block.style.top = `${8 + ((maxPitch - note.pitch) / pitchSpan) * 188}px`;
    els.pianoRoll.append(block);
  }
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
  els.saveNotes.disabled = disabled || !hasProject || !hasNotes;
  els.exportMidi.disabled = disabled || !hasProject || !hasNotes;
  els.exportMusicxml.disabled = disabled || !hasProject || !hasNotes;
  els.exportPdf.disabled = disabled || !hasProject || !hasNotes;
}

function download(format) {
  if (!state.project) return;
  window.location.href = `/api/projects/${state.project.id}/export/${format}`;
}

function setProject(project, preferredStemId = null) {
  const previousStemId = state.project?.id === project?.id ? state.selectedStemId : null;
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

function getMaxEnd(notes) {
  return Math.max(4, ...notes.map((note) => Math.ceil(note.endSec)));
}

function pitchToStaffY(pitch, staffTop, lineGap) {
  const bottomLine = staffTop + lineGap * 4;
  const y = bottomLine - (pitch - 64) * 3.5;
  return Math.max(38, Math.min(178, y));
}

render();
