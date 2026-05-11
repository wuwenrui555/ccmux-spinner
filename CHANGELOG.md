# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
