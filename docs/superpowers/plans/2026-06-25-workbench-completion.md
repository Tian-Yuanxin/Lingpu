# Lingpu Workbench Completion Plan

> REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

## Goal

Turn the current Lingpu MVP into a complete local workbench loop:

- Upload audio and create a project.
- Reopen recent projects from local storage.
- Separate stems and explicitly choose which stem to transcribe.
- Persist score settings used by preview/export workflows.
- Edit notes and export MIDI, MusicXML, or PDF.
- Start the app from the verified `lingpu311` conda runtime with one script.

## Assumptions

- "Complete project" means a usable local MVP, not hosted auth, accounts, cloud jobs, or collaborative editing.
- Existing Demucs/audio-separator/Basic Pitch adapters stay as the model boundary for this iteration.
- `AGENTS.md` is user-local guidance and is not staged unless explicitly requested.

## Tasks

1. Backend project lifecycle
   - Add `GET /api/projects` for recent local projects.
   - Add `PATCH /api/projects/{project_id}/score-settings`.
   - Verify with API and store tests.

2. Frontend workbench loop
   - Add recent-project loading and reopen controls.
   - Add real selected-stem state and use it for transcription.
   - Add score settings controls and save flow.
   - Verify with static frontend tests and API smoke tests.

3. Local deployment polish
   - Add a PowerShell launcher for the `lingpu311` conda deployment.
   - Update README commands to match the launcher.
   - Verify tests and a basic server import/startup path.

## Verification

- Run the full pytest suite in `D:\Anaconda\envs\lingpu311`.
- Confirm static frontend tests cover new DOM/API hooks.
- Keep `git status` clean except intentionally untracked user files.
