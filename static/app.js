"use strict";

const STATUS_POLL_MS = 10000;
const ERROR_KEYS = [
  "source",
  "content_style",
  "guest_voices",
  "tone",
  "depth",
  "length_minutes",
  "notes",
];

const NEVER_OFFER = new Set(["carter", "hugh", "elliot"]);

const state = {
  books: [],
  booksError: "",
  booksTruncated: false,
  voices: [],
  choices: [],
  selectedFiles: [],
  selectedVoices: [],
  dryRun: false,
  pollTimer: null,
  stopped: false,
};

let statusInFlight = false;

function init() {
  bindStatic();
  updateTopicCount();
  loadOptions();
  startPolling();
}

function bindStatic() {
  document.getElementById("topic").addEventListener("input", () => {
    updateTopicCount();
    setFieldError("source", "");
  });
  document.getElementById("research").addEventListener("change", () => {
    setFieldError("source", "");
  });
  document.getElementById("books-toggle").addEventListener("click", toggleBooks);
  document.getElementById("brief-form").addEventListener("submit", onSubmit);
  document.getElementById("stop-btn").addEventListener("click", onStop);
  document.getElementById("check-now").addEventListener("click", () => {
    refreshStatus();
  });
  document.getElementById("retry-btn").addEventListener("click", () => {
    loadOptions();
  });
  document.addEventListener("click", (event) => {
    const dropdown = document.getElementById("books-dropdown");
    if (!dropdown.contains(event.target)) closeBooks();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeBooks();
  });
}

async function loadOptions() {
  const submit = document.getElementById("submit-btn");
  submit.disabled = true;
  try {
    const response = await fetch("/api/options", { cache: "no-store" });
    const data = await readJson(response);
    if (!response.ok || !data.ok) {
      showLoadError(data.error || "The desk couldn't load its configuration.");
      return;
    }
    hideLoadError();
    state.books = Array.isArray(data.books) ? data.books : [];
    state.booksError = data.books_error || "";
    state.booksTruncated = Boolean(data.books_truncated);
    state.choices = voiceChoices(data).filter((choice) => {
      return !NEVER_OFFER.has(String(choice.name).toLowerCase());
    });
    state.voices = state.choices.filter((choice) => choice.ready).map((choice) => choice.name);
    state.selectedFiles = [];
    state.selectedVoices = [];
    state.dryRun = Boolean(data.dry_run);
    document.getElementById("host-name").textContent = data.host || "Carter";
    document.getElementById("meta-books").textContent = data.books_dir || "";
    document.getElementById("meta-briefs").textContent = data.briefs_dir || "";
    document.getElementById("status-path").textContent = data.status_file || "";
    const ribbon = document.getElementById("dry-run-ribbon");
    ribbon.hidden = !state.dryRun;
    if (state.dryRun) {
      submit.textContent = "Write brief";
      document.getElementById("submit-hint").textContent =
        "Dry run. The pipeline will not be started.";
    } else {
      submit.textContent = "Write brief and launch";
      document.getElementById("submit-hint").textContent =
        "Writes a brief, then starts the pipeline.";
    }
    renderBooks();
    renderVoices();
    if (state.voices.length < 1) {
      setFieldError(
        "guest_voices",
        "No guest voices are available. Check voices, banned_voices, and not_ready_voices in config.json."
      );
      submit.disabled = true;
    } else if (!state.stopped) {
      submit.disabled = false;
    }
  } catch (err) {
    showLoadError("Couldn't reach the desk.");
  }
}

function renderBooks() {
  const panel = document.getElementById("books-panel");
  const hint = document.getElementById("books-hint");
  panel.replaceChildren();
  hint.textContent = booksHint();
  hint.classList.toggle("is-bad", Boolean(state.booksError));

  const filter = document.createElement("input");
  filter.type = "search";
  filter.id = "books-filter";
  filter.placeholder = "Filter titles";
  filter.autocomplete = "off";
  filter.setAttribute("aria-label", "Filter titles");
  panel.appendChild(filter);

  const noMatch = document.createElement("p");
  noMatch.className = "empty";
  noMatch.hidden = true;
  noMatch.textContent = "Nothing matches that filter.";

  if (!state.books.length) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = state.booksError
      ? "The shelf could not be read."
      : "No pdf, epub, txt, or md files in the books folder.";
    panel.appendChild(empty);
    updateBooksSummary();
    return;
  }

  const rows = [];
  for (const book of state.books) {
    const label = document.createElement("label");
    label.className = "option";
    label.dataset.rel = book.rel;
    const box = document.createElement("input");
    box.type = "checkbox";
    box.value = book.rel;
    box.addEventListener("change", () => onBookToggle(box));
    const name = document.createElement("span");
    name.textContent = book.rel;
    label.append(box, name);
    panel.appendChild(label);
    rows.push(label);
  }
  panel.appendChild(noMatch);

  filter.addEventListener("keydown", (event) => {
    if (event.key === "Enter") event.preventDefault();
  });
  filter.addEventListener("input", () => {
    const query = filter.value.trim().toLowerCase();
    let visible = 0;
    for (const row of rows) {
      const rel = (row.dataset.rel || "").toLowerCase();
      const hide = query !== "" && !rel.includes(query);
      row.hidden = hide;
      if (!hide) visible += 1;
    }
    noMatch.hidden = visible !== 0;
  });
  updateBooksSummary();
}

function booksHint() {
  if (state.booksError) return state.booksError;
  const noun = state.books.length === 1 ? "file" : "files";
  let text =
    state.books.length +
    " " +
    noun +
    " on the shelf. Optional, up to two. pdf, epub, txt, or md.";
  if (state.booksTruncated) text += " Showing the first 2000.";
  return text;
}

function onBookToggle(box) {
  if (box.checked) {
    if (state.selectedFiles.length >= 2) {
      box.checked = false;
      setFieldError("source", "Pick at most two books.");
      return;
    }
    state.selectedFiles.push(box.value);
  } else {
    state.selectedFiles = state.selectedFiles.filter((value) => value !== box.value);
  }
  setFieldError("source", "");
  updateBooksSummary();
}

function updateBooksSummary() {
  const summary = document.getElementById("books-summary");
  const count = state.selectedFiles.length;
  if (count === 0) summary.textContent = "Optional: up to two books";
  else if (count === 1) summary.textContent = state.selectedFiles[0];
  else summary.textContent = state.selectedFiles[0] + " + " + (count - 1) + " more";
}

function voiceChoices(data) {
  if (Array.isArray(data.voice_choices)) {
    return data.voice_choices
      .filter((choice) => choice && typeof choice.name === "string")
      .map((choice) => ({
        name: choice.name,
        ready: choice.ready !== false,
        note: typeof choice.note === "string" ? choice.note : "",
      }));
  }
  return (Array.isArray(data.voices) ? data.voices : []).map((name) => ({
    name: String(name),
    ready: true,
    note: "",
  }));
}

function renderVoices() {
  const box = document.getElementById("voices");
  box.replaceChildren();
  for (const choice of state.choices) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "voice";
    button.dataset.voice = choice.name;
    if (!choice.ready) {
      button.disabled = true;
      button.classList.add("is-waiting");
      button.title = choice.note;
      const name = document.createElement("span");
      name.className = "voice-name";
      name.textContent = choice.name;
      const note = document.createElement("span");
      note.className = "voice-note";
      note.textContent = choice.note;
      button.append(name, note);
      box.appendChild(button);
      continue;
    }
    button.textContent = choice.name;
    button.setAttribute("aria-pressed", "false");
    button.addEventListener("click", () => onVoiceToggle(button));
    box.appendChild(button);
  }
}

function onVoiceToggle(button) {
  const name = button.dataset.voice;
  if (state.selectedVoices.includes(name)) {
    state.selectedVoices = state.selectedVoices.filter((voice) => voice !== name);
    button.setAttribute("aria-pressed", "false");
    setFieldError("guest_voices", "");
    return;
  }
  if (state.selectedVoices.length >= 2) {
    setFieldError("guest_voices", "Pick one or two guest voices.");
    return;
  }
  state.selectedVoices.push(name);
  button.setAttribute("aria-pressed", "true");
  setFieldError("guest_voices", "");
}

function updateTopicCount() {
  const topic = document.getElementById("topic");
  document.getElementById("topic-count").textContent = topic.value.length + "/600";
}

function toggleBooks() {
  const panel = document.getElementById("books-panel");
  if (panel.hidden) openBooks();
  else closeBooks();
}

function openBooks() {
  document.getElementById("books-panel").hidden = false;
  document.getElementById("books-toggle").setAttribute("aria-expanded", "true");
  const filter = document.getElementById("books-filter");
  if (filter) filter.focus();
}

function closeBooks() {
  const panel = document.getElementById("books-panel");
  if (!panel || panel.hidden) return;
  panel.hidden = true;
  document.getElementById("books-toggle").setAttribute("aria-expanded", "false");
}

function selectedLength() {
  const picked = document.querySelector('input[name="length"]:checked');
  return picked ? Number(picked.value) : 40;
}

function collectPayload() {
  const topic = document.getElementById("topic").value.replace(/\s+/g, " ").trim();
  return {
    topic: topic,
    files: state.selectedFiles.slice(),
    research: document.getElementById("research").checked,
    content_style: document.getElementById("content_style").value,
    length_minutes: selectedLength(),
    guest_voices: state.selectedVoices.slice(),
    tone: document.getElementById("tone").value,
    depth: document.getElementById("depth").value,
    notes: document.getElementById("notes").value,
  };
}

function clientErrors(payload) {
  const errors = {};
  if (!payload.topic) errors.source = "Enter a topic.";
  else if (payload.topic.length > 600) errors.source = "Keep the topic under 600 characters.";
  else if (payload.files.length > 2) errors.source = "Pick at most two books.";
  else if (state.booksError && payload.files.length > 0) {
    errors.source = "The books folder is not available.";
  } else if (!payload.research && payload.files.length < 1) {
    errors.source = "Attach a book or PDF, or turn on web research.";
  }
  if (!["v2.5", "v2.3"].includes(payload.content_style)) {
    errors.content_style = "Choose a script style.";
  }
  if (payload.guest_voices.length < 1 || payload.guest_voices.length > 2) {
    errors.guest_voices = "Pick one or two guest voices.";
  }
  if (![20, 30, 40].includes(payload.length_minutes)) {
    errors.length_minutes = "Length must be 20, 30, or 40 minutes.";
  }
  if (!payload.tone) errors.tone = "Choose a tone.";
  if (!payload.depth) errors.depth = "Choose a depth.";
  if (payload.notes.trim().length > 4000) errors.notes = "Keep notes under 4000 characters.";
  return errors;
}

async function onSubmit(event) {
  event.preventDefault();
  if (state.stopped) return;
  clearErrors();
  const payload = collectPayload();
  const errors = clientErrors(payload);
  if (Object.keys(errors).length) {
    showErrors(errors);
    return;
  }
  const submit = document.getElementById("submit-btn");
  const previous = submit.textContent;
  submit.disabled = true;
  submit.textContent = "Writing…";
  try {
    const response = await fetch("/api/brief", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      cache: "no-store",
      body: JSON.stringify(payload),
    });
    const data = await readJson(response);
    if (!response.ok || !data.ok) {
      if (data.brief_written && data.brief_path) {
        showBanner(
          "bad",
          "The brief was written, but the pipeline did not start.\n" +
            data.brief_path +
            (data.error ? "\n" + data.error : ""),
          true
        );
      } else if (data.errors) {
        showErrors(data.errors);
      } else {
        showBanner("bad", data.error || "The brief was not written.", true);
      }
      return;
    }
    const lines = ["Brief written.", data.brief_path || data.brief_id || ""];
    if (data.dry_run) lines.push("Dry run: the pipeline was not started.");
    else if (data.launched) {
      lines.push("Pipeline started" + (data.pid ? " (pid " + data.pid + ")." : "."));
    }
    showBanner("good", lines.filter(Boolean).join("\n"), true);
    refreshStatus();
  } catch (err) {
    showBanner("bad", "Couldn't reach the desk.", true);
  } finally {
    submit.textContent = previous;
    submit.disabled = state.stopped || state.voices.length < 1;
  }
}

async function onStop() {
  const confirmed = window.confirm(
    "Stop the episode desk? A pipeline that already started keeps running."
  );
  if (!confirmed) return;
  const button = document.getElementById("stop-btn");
  button.disabled = true;
  try {
    const response = await fetch("/api/stop", { method: "POST", cache: "no-store" });
    const data = await readJson(response);
    if (!response.ok || !data.ok) {
      button.disabled = false;
      showBanner("bad", data.error || "The server did not stop.", true);
      return;
    }
    state.stopped = true;
    if (state.pollTimer) window.clearInterval(state.pollTimer);
    document.getElementById("submit-btn").disabled = true;
    document.getElementById("status-text").textContent =
      "Server stopping. You can close this tab.";
    showBanner("good", "Server stopping. You can close this tab.", true);
  } catch (err) {
    button.disabled = false;
    showBanner("bad", "Couldn't reach the desk.", true);
  }
}

function startPolling() {
  refreshStatus();
  state.pollTimer = window.setInterval(refreshStatus, STATUS_POLL_MS);
}

async function refreshStatus() {
  if (state.stopped || statusInFlight) return;
  statusInFlight = true;
  try {
    const response = await fetch("/api/status", { cache: "no-store" });
    renderStatus(await readJson(response));
  } catch (err) {
    renderStatus({ ok: false, error: "Couldn't reach the desk." });
  } finally {
    statusInFlight = false;
    if (!state.stopped) markChecked();
  }
}

function renderStatus(data) {
  const pre = document.getElementById("status-text");
  const path = document.getElementById("status-path");
  if (data.path) path.textContent = data.path;
  if (!data.ok) {
    pre.textContent = data.error || "Couldn't read the status file.";
    return;
  }
  if (!data.exists) {
    pre.textContent = "No status file at that path yet. The pipeline creates it when it runs.";
    return;
  }
  if (!data.text) {
    pre.textContent = "The status file is empty.";
    return;
  }
  const text = formatStatusText(data.text);
  pre.textContent = data.truncated ? text + "\n\nShowing the first 16 KB." : text;
}

function formatStatusText(text) {
  return text
    .split(/\r?\n/)
    .map((line) => {
      if (line.includes("ABORT research too thin")) return line;
      if (/\bstep=gen research\b/.test(line)) return "Researching the web...";
      return line;
    })
    .join("\n");
}

function markChecked() {
  document.getElementById("status-checked").textContent =
    "Checked " + new Date().toLocaleTimeString();
}

function showErrors(errors) {
  for (const [key, message] of Object.entries(errors)) {
    if (document.getElementById("error-" + key)) setFieldError(key, message);
    else showBanner("bad", message, false);
  }
}

function clearErrors() {
  hideBanner();
  for (const key of ERROR_KEYS) setFieldError(key, "");
}

function setFieldError(key, message) {
  const node = document.getElementById("error-" + key);
  if (node) node.textContent = message || "";
  const field = document.getElementById("field-" + key);
  if (field) field.classList.toggle("has-error", Boolean(message));
}

function showBanner(kind, message, moveFocus) {
  const banner = document.getElementById("banner");
  banner.hidden = false;
  banner.className = "banner " + kind;
  banner.textContent = message;
  if (moveFocus) {
    banner.tabIndex = -1;
    banner.focus();
  }
}

function hideBanner() {
  const banner = document.getElementById("banner");
  banner.hidden = true;
  banner.textContent = "";
}

function showLoadError(message) {
  const node = document.getElementById("load-error");
  node.hidden = false;
  node.textContent = message;
  document.getElementById("retry-btn").hidden = false;
  document.getElementById("submit-btn").disabled = true;
}

function hideLoadError() {
  document.getElementById("load-error").hidden = true;
  document.getElementById("retry-btn").hidden = true;
}

async function readJson(response) {
  const text = await response.text();
  if (!text) return { ok: false, error: "The desk returned an empty response." };
  try {
    return JSON.parse(text);
  } catch (err) {
    return { ok: false, error: "The desk returned something that was not JSON." };
  }
}

init();
