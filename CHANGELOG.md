# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.1] - 2026-05-11

### Added

- `SpinnerMonitor.current` property: the most recently classified
  `Activity` from the poll loop, regardless of whether it was
  emitted to the iterator (the iterator coalesces unchanged
  classifications). Useful for one-shot "what's the spinner state
  right now" queries.
- `SpinnerMonitor.last_pane_change_at` property: Unix epoch of the
  most recent poll where the raw captured pane text differed from
  the previous poll. Finer-grained than Activity-change emission;
  consumers can use `time.time() - last_pane_change_at` to detect
  static panes during periods when no Activity transition fired.

Both fields are additive — existing consumers (only the
`ccmux-spinner watch` CLI as of this writing) ignore them.

Motivation: ccmux-core's grace timer needs to distinguish "spinner
absent because pane is streaming new content" (don't fire) from
"spinner absent and pane is static" (fire interrupted). Activity
classification alone cannot — both cases yield `None`. The new
`last_pane_change_at` signal closes that gap by exposing whether
the underlying pane is changing at all.

## [0.2.0] - 2026-05-10

### Changed (BREAKING)

- `SpinnerMonitor(tmux_session: str)` is now
  `SpinnerMonitor(pane_id: str)`. Callers must pass the tmux pane id
  directly. Use the new `resolve_active_pane_id(tmux_session)` helper
  if you need to resolve from a session name.
- `resolve_pane_id(tmux_session: str) -> str` is **removed**.
  Replacement: `resolve_active_pane_id(tmux_session: str) -> str`,
  which prefers the **active** pane (no `:0` window suffix) and
  falls back to window 0's first pane when the active lookup is
  empty or fails. The old behavior of hard-coding window 0 was a
  bug for any session with multiple windows.

### Added

- `resolve_active_pane_id` is exported from the top-level
  `ccmux_spinner` package as a public helper.

### Migration

`ccmux-spinner` v0.1 had no published consumers. Internal call
sites (the `ccmux-spinner watch` CLI and the test suite) are
updated in this release. Downstream packages (notably
`ccmux-core` v0.1) declare `ccmux-spinner >= 0.2.0`.

## [0.1.1] - 2026-05-10

### Fixed

- `parse_pane`: require a whitespace character after the spinner
  glyph before classifying. Without this, any line beginning with
  one of the spinner glyphs would match — most notably a markdown
  `**bold**` line streamed into the terminal during a turn would
  render above the chrome and get mis-classified as an
  `IdleDecoration` (because the leading `*` is a spinner glyph in
  CC's 5-frame cycle, but a markdown bold's second char is another
  `*`, not whitespace). The new check also rejects `*item` /
  `··` / similar artifacts. Real status rows are always
  `<glyph> <body>` with a space between, so this discriminator
  is exact.

## [0.1.0] - 2026-05-10

### Added

- Initial release. Successor to `ccmux-state`.
- `SpinnerMonitor`: async iterator over `Activity = Spinner |
  IdleDecoration | None` snapshots for one tmux session.
- Parser anchored from the input-chrome separator that scans
  upward, **skipping known overlay rows** (tip lines,
  session-rating modal, TodoWrite checkboxes and their overflow
  tail) before classifying the spinner row. This fixes the
  ccmux-state regression where any of those overlays between the
  spinner and the chrome forced an Idle mis-classification.
- `ccmux-spinner watch <tmux-session>` CLI for quick inspection.
- `settings.env` support for `CCMUX_SPINNER_POLL_INTERVAL` (mirror
  of claude-tap's settings.env mechanism, no external dep).
- Spec at
  `docs/superpowers/specs/2026-05-10-ccmux-spinner-design.md`.

### Removed (vs. ccmux-state)

- `Idle / Working / Blocked / Dead` state machine — these are now
  derivable from claude-tap's hook stream by the consumer.
- Subscription to claude-tap `EventStream`. ccmux-spinner is a pure
  pane-text watcher with no event-stream dependency.

### Note

`Spinner` and `IdleDecoration` carry the spinner row as `text` and
any TodoWrite checklist rendered between it and the input chrome
as `todos: tuple[str, ...]` (visual top-to-bottom order, raw pane
lines rstripped only). Sub-field parsing of the spinner row
(elapsed seconds, token counts, "thought for Ns") was prototyped
against live data but removed for v0.1 — the CC spinner format
varies across versions (`(23s · ...)` vs `(2m 34s · ↓ 9.2k
tokens · thought for 8s)`), and most consumers only need "is it
working, and what does the row say". Parse in the consumer if
you need specific fields.

### Watch output

`ccmux-spinner watch <session>` defaults to a claude-tap-style
block per change: separator with embedded UTC emit time, then
`[ working ]` / `[ idle ]` + main text, then **one raw line per
TodoWrite row** when the todo list is in scope. No JSON wrapping
of the todo list — each row prints verbatim (the row already
carries Claude Code's `⎿` / spacing). The visual width of the
separator and the per-line trim cap are both controlled by the
single ``CCMUX_SPINNER_PRETTY_WIDTH`` setting (default 100).
``--json`` switches to one JSON object per snapshot.
