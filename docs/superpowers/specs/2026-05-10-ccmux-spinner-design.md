<!-- markdownlint-disable MD024 -->

# ccmux-spinner design

- **Date**: 2026-05-10
- **Repo**: `ccmux-spinner` (new, succeeds and replaces `ccmux-state`)
- **Status**: design draft, awaiting user review

## Context

`ccmux-state` was originally responsible for the entire session-state
view (`Idle / Working / Blocked / Dead`) by combining tmux pane text
with a claude-tap `EventStream` consumer. With `claude-tap` v0.2 now
exposing both an `EventStream` and a `MessageStream` that together
let any consumer derive session state directly from hooks +
transcript, `ccmux-state`'s state-machine layer became redundant.

What does **not** become redundant, however, is the live spinner
text rendered into the tmux pane between hook fires:

* Active row: `Thinking… (16s · ↑ 827 tokens)`
* Completion summary (post-turn, before next prompt):
  `✻ Churned for 55s`

Neither has a hook source — both are pane-only artifacts. Capturing
them is the only piece of `ccmux-state`'s old surface that genuinely
required pane reading and that no claude-tap layer can replicate.

This spec is for `ccmux-spinner`: a clean-slate library narrowly
scoped to that role.

## Why a new repo

`ccmux-state` carries a state-machine vocabulary, a tap-event
consumer, and a body of tests built around the four-state model.
None of that survives the scope reduction. The user has confirmed
no current consumer depends on `ccmux-state`, so a clean new repo
is preferable to a v2.0 in-place rewrite that would inherit irrelevant
git history and naming.

## Goals (v0.1)

1. Capture a tmux pane and parse out the spinner row or the
   post-turn completion summary, returning a typed snapshot.
2. Be **robust against UI overlays** rendered between the spinner
   row and the input chrome: footer tips, session-rating modal,
   TodoWrite checkbox lists, and their overflow tail line. The
   `ccmux-state` parser bailed on the first non-blank row above
   chrome and consequently mis-classified Working as Idle whenever
   any of these overlays appeared. ccmux-spinner does not.
3. Provide an async iterator (`SpinnerMonitor`) that yields the
   latest snapshot as the pane changes.
4. Offer a tiny `ccmux-spinner watch <tmux-session>` CLI for
   live inspection.
5. Take **no runtime dependencies**. Everything is pane text +
   regex; same lean philosophy as claude-tap.

## Non-goals (v0.1)

- **No state machine**. ccmux-spinner does not produce
  `Idle / Working / Blocked / Dead`. Consumers compose those
  themselves from claude-tap's hook stream + ccmux-spinner's pane
  snapshots; see [Composition](#composition) below.
- **No claude-tap event consumption**. ccmux-spinner reads the
  pane and nothing else. Removing the `EventStream` dependency
  simplifies its responsibilities and lets it run standalone.
- **No multi-window / multi-session orchestration**. One
  `SpinnerMonitor` watches exactly one tmux session (its window 0
  pane). Consumers spawn multiple monitors if they want multi.
- **No history or replay**. Snapshots reflect the current pane;
  there is no log of past spinner states.
- **No automatic tmux discovery**. The caller passes a tmux session
  name. If the session does not exist or the pane vanishes, the
  monitor raises (or yields a terminal signal — see [Failure
  modes](#failure-modes)).

## Data model

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class Spinner:
    """Active spinner row above the input chrome.

    Identified by a leading spinner glyph (one of `· ✻ ✽ ✶ * ✳ ✢`)
    AND the presence of `…` in the text — Claude Code uses the
    ellipsis to mark "still running". The full row text (sans the
    leading glyph and surrounding whitespace) is carried as-is.
    Consumers that want sub-fields like elapsed seconds or token
    counts parse the text themselves; the v0.1 parser does not
    decompose the row because the format varies across CC versions
    and most consumers only need "is it working, and show me what
    it's doing".
    """
    text: str


@dataclass(frozen=True)
class IdleDecoration:
    """Post-turn completion summary above the input chrome.

    Identified by a leading spinner glyph but no `…` — Claude Code
    drops the ellipsis on completion summaries like
    `Churned for 55s`. Text is carried verbatim, same as Spinner.
    """
    text: str


# `None` means: chrome is present but no spinner / decoration above it,
# OR no chrome at all (e.g. session at a bash prompt).
Activity = Spinner | IdleDecoration | None
```

## Parser algorithm

```
find_chrome(lines): index of the input-chrome separator (the
                    horizontal-rule row that bounds the prompt box)
                    in the bottom 20 lines. None if no chrome.

if find_chrome(lines) is None:
    return None       # no chrome → not classifiable

i = chrome_idx - 1
while i >= 0 and (chrome_idx - i) <= STATUS_SCAN_WINDOW:
    line = lines[i]
    stripped = line.strip()
    if stripped == "":
        i -= 1
        continue
    if matches_overlay(line):
        i -= 1                       ← key fix vs ccmux-state
        continue
    # First "real" content line above chrome.
    if starts_with_spinner_glyph(stripped):
        body = stripped[1:].strip()
        if "…" in body:
            return parse_spinner(body)
        else:
            return IdleDecoration(text=body)
    return None                      # unrecognized → don't guess
return None
```

Where `matches_overlay(line)` returns True for any of:

| Pattern | Source |
|---|---|
| `^\s*⎿\s+Tip:\s+` | Footer tip lines |
| `^\s*●\s*How is Claude doing this session\?` | Score modal title |
| `^\s*\d+:\s*(Bad\|OK\|Good\|Excellent)\b` | Score options |
| `^\s*[◼◻☐☒✔✓]` | TodoWrite checkbox row |
| `^\s*⎿\s+[◼◻☐☒✔✓]` | TodoWrite first row with elbow |
| `^\s*…\s*\+\d+\b` | TodoWrite overflow tail |

Patterns are inlined as compiled `re.Pattern` constants in
`parser.py`. `claude-code-state` has the same set in its config; we
do not depend on `claude-code-state` because the rest of that
package is unrelated to this scope.

No sub-field parsing in v0.1. The body becomes the dataclass's
`text`; downstream consumers can run their own regexes if they
want elapsed seconds, token counts, or `thought for Ns` extracted.

## API

```python
from ccmux_spinner import (
    SpinnerMonitor,
    Spinner,
    IdleDecoration,
    Activity,
    parse_pane,            # pure: pane_text -> Activity
)


async with SpinnerMonitor(
    tmux_session="ccmux",
    poll_interval=0.5,     # falls back to CCMUX_SPINNER_POLL_INTERVAL
) as mon:
    async for activity in mon:
        ...
```

`SpinnerMonitor` polls `tmux capture-pane` at `poll_interval`. It
yields **on change** — repeated identical snapshots are coalesced —
so a long-running spinner does not flood consumers with every poll.

`parse_pane(pane_text: str) -> Activity` is the pure function the
monitor wraps; exposed for tests and one-off scripts.

## Composition

ccmux-spinner does not derive session state. A consumer that wants
the old `Idle / Working / Blocked` view composes:

* `claude-tap` `EventStream`: hook events (`pre_tool_use`,
  `post_tool_use`, `stop`, `permission_request`, `session_end`).
  Coarse state transitions: Stop → Idle, PreToolUse →
  Working-with-tool, PermissionRequest → Blocked, etc.
* `ccmux-spinner` `SpinnerMonitor`: live activity indicator while a
  turn is in progress (so the consumer can render "still thinking,
  16s elapsed" instead of just "Working" with no detail).

The consumer iterates both async iterators (`asyncio.gather` /
`asyncio.wait`) and merges them into whatever shape it needs.
v0.1 does not ship a composition helper; if multiple consumers end
up writing the same merge pattern, a `ccmux-compose` helper can
land later.

A consumer that ONLY needs spinner activity (e.g. a status-bar HUD)
uses ccmux-spinner alone, ignoring claude-tap.

## Module layout

```
src/ccmux_spinner/
  __init__.py     — re-exports SpinnerMonitor, Spinner, IdleDecoration, Activity, parse_pane
  pane.py         — tmux capture-pane + chrome detection + scan helpers (port from ccmux-state)
  parser.py       — overlay patterns + parse_pane(), parse_spinner_body()
  monitor.py      — SpinnerMonitor async iterator
  config.py       — settings.env loader (mirror of claude-tap pattern)
  cli.py          — `ccmux-spinner watch <session>` debug entrypoint
  errors.py       — TmuxResolutionError, PaneCaptureError (port)
```

Estimated total: ~500 lines including tests. Lean.

## Failure modes

| Condition | Behavior |
|---|---|
| `tmux` binary missing | `TmuxResolutionError` raised on `__aenter__`. |
| Session does not exist / no window 0 | `TmuxResolutionError` on `__aenter__`. |
| `capture-pane` fails mid-run (pane killed) | Iterator yields one final `None` and terminates. |
| Pane text but no recognizable chrome | Snapshot is `None`. |
| Chrome present but only overlays above (e.g. score modal at top) | `None` — there's no spinner row to surface. |
| Status row whose glyph is not in `_STATUS_SPINNERS` | `None`. New CC frames go into a drift log (mirror of claude-tap drift mechanism); see `parser.py`. |

The `tap_consumer_crashed` / `pane_lost` recovery contract from
`ccmux-state.SessionMonitor` is simplified to "yield None then end"
because there is no longer a state machine to keep in sync.

## Settings

`config.py` mirrors `claude_tap.config`'s settings.env approach:

* `CCMUX_SPINNER_DIR` — state directory (default `~/.ccmux-spinner`).
  Reserved for future log files; v0.1 does not write anything there
  except to load `settings.env` from it.
* `CCMUX_SPINNER_POLL_INTERVAL` — pane poll cadence (s), default 0.5.

`settings.env` lookup order: cwd `./settings.env` then
`$CCMUX_SPINNER_DIR/settings.env`. Shell exports always win.
The parser is the same ~25-line key=value/comment/quote handler as
claude-tap; copied, not depended on (no cross-package dependency).

## Testing

* **`parser.py`** — table-driven cases:
  * Plain spinner above chrome → `Spinner(...)`
  * Completion summary above chrome → `IdleDecoration(...)`
  * No chrome → `None`
  * Each overlay type between spinner and chrome → still finds spinner
  * Multiple stacked overlays → still finds spinner
  * Unrecognized non-overlay non-spinner content above chrome → `None`
  * Empty pane → `None`

* **`pane.py`** — mock subprocess; assert command shape and
  argument quoting; verify exception types.

* **`monitor.py`** — feed synthetic pane text via patched
  `capture_pane`; assert change-coalescing, assert clean termination
  on `PaneCaptureError`.

* **`cli.py`** — invoke watch with a fake monitor; assert printed
  lines.

## Release plan

1. Branch `dev` from `main` (after initial commit).
2. Implement in order: `errors.py` → `pane.py` → `parser.py` →
   `monitor.py` → `config.py` → `cli.py` → `__init__.py`.
3. Tests alongside each module.
4. Open PR to `dev`; verify CI green.
5. Tag `v0.1.0` after merge to `main`.

No existing-consumer migration step is required (no consumers).

## Future work (deferred)

- `ccmux-compose`: a small helper that merges
  `claude_tap.EventStream` + `ccmux_spinner.SpinnerMonitor` into a
  single `(state, spinner_text)` async iterator. Wait until two or
  more consumers ask for it.
- Drift logger for unknown spinner glyphs / pane patterns, mirroring
  `claude_tap.drift`. Probably worth doing soon — pane TUI is the
  most fragile surface.
- inotify-based pane-change detection instead of polling.
