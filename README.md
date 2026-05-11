# ccmux-spinner

Watch the live spinner / completion summary on a Claude Code tmux
pane and emit it as a structured stream.

The spinner row (`Thinking… (16s · ↑ 827 tokens)`) and the
post-turn idle decoration (`✻ Churned for 55s`) are the only pieces
of session-level information that **cannot** be derived from the
[claude-tap](https://github.com/wuwenrui555/claude-tap) hook event
stream — both are rendered into the tmux pane TUI by Claude Code
between hook fires. ccmux-spinner is a narrow library that captures
exactly those, nothing else.

## Status

v0.1 alpha.

Successor to and rewrite of `ccmux-state`. The state-machine layer
(`Idle / Working / Blocked / Dead`) has moved out: those states are
all derivable from claude-tap's `EventStream` / `MessageStream`.
What remained was the pane-text spinner detection, and that is what
ccmux-spinner now does — correctly, including the case where tips,
session-rating modals, or TodoWrite overlays render between the
spinner row and the input chrome (which the old ccmux-state
mis-classified as Idle).

## Use

```python
from ccmux_spinner import SpinnerMonitor, Spinner, IdleDecoration

async with SpinnerMonitor(tmux_session="ccmux") as mon:
    async for activity in mon:
        match activity:
            case Spinner(text=t):
                print(f"working: {t}")
            case IdleDecoration(text=t):
                print(f"just finished: {t}")
            case None:
                print("(no spinner, no decoration)")
```

CLI smoke test:

```bash
ccmux-spinner watch <tmux-session>
```

## Composition with claude-tap

ccmux-spinner intentionally has no opinion about overall session
state. Consumers that want a `(Idle | Working | Blocked | Dead)`
view compose claude-tap's hook stream with ccmux-spinner's pane
stream themselves; see
`docs/superpowers/specs/2026-05-10-ccmux-spinner-design.md` for the
contract and a sample composition pattern.

## License

Apache 2.0.
