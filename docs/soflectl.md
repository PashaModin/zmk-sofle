# soflectl — the keyboard as a Claude Code control surface

The left half's display shows what your Claude Code sessions are doing. The
5-way navigation switch, held on the agent layer, approves or denies whatever
one of them is waiting on.

Two pieces:

- **`agentctl`** — firmware, in `agentctl/`. It renders bytes it is given and
  reports which control moved. No decisions are made on the keyboard.
- **`soflectl`** — a Python daemon, in `daemon/`. It receives Claude Code's
  hooks over HTTP, decides what to display, and answers permission requests
  with whatever button you pressed.

Everything stays on `127.0.0.1`. Nothing leaves the machine.

## How it fits together

```
Claude Code sessions
        |  hooks, type "http"
        |  POST http://127.0.0.1:8787/hook
        v
   soflectl daemon
        |  raw HID, 32-byte reports, usage page 0xFF60
        v
   Sofle LEFT half (central)  -- display + raw HID
        ^
        |  split BLE, key positions relayed automatically
   Sofle RIGHT half (peripheral) -- the 5-way switch lives here
```

The 5-way is physically on the right half, which can never talk to your
computer. That does not matter: ZMK relays key positions to the central for
free, so the presses arrive on the left half, which owns the HID link.

## If the daemon is not running

Nothing happens. A failed or timed-out HTTP hook is a non-blocking error in
Claude Code — execution continues exactly as if no hook were configured. The
keyboard stays a keyboard and Claude Code prompts you on screen as usual.
That is the whole failure story, and it is why every hook except
`PermissionRequest` has a 2–3 second timeout.

## Setup

### 1. Flash the firmware

Push, wait for the build, and flash `eyelash_sofle_left.uf2` to the left half
(see the main README). agentctl is enabled by `config/eyelash_sofle_left.conf`
and only affects the left half.

Note that this file sets `CONFIG_ZMK_SLEEP=n`. Deep sleep switches the display
off and drops the HID link, which defeats the purpose of a status display — at
the cost of battery life. If the keyboard is usually on USB anyway, that cost
is nil.

### 2. Check the keyboard is exposing raw HID

```bash
pip install hidapi
python3 scripts/find-device.py
```

You want the line marked `<-- raw HID`, on usage page `0xff60`, usage `0x61`.
If nothing matches, the left half either is not plugged in over USB or is not
running an agentctl build. On Linux you may also need a udev rule to open
`hidraw` devices without root.

### 3. Install and run the daemon

```bash
cd daemon
pip install -e .
soflectl            # add -v for detail
```

Or, with no keyboard attached at all:

```bash
soflectl --fake-hid
```

which draws the frames in your terminal and reads button names from stdin
(`UP`, `DOWN`, `LEFT`, `RIGHT`, `CENTER`, optionally `CENTER hold`, plus `CW`
and `CCW`). This is the fastest way to work on rendering — the alternative is
reflashing to test a text change.

### 4. Register the hooks

Merge the `hooks` object from `claude/settings.hooks.json` into
`~/.claude/settings.json`. Then run `/hooks` inside a session to confirm they
registered, and check `curl -s localhost:8787/health`.

If `allowedHttpHookUrls` is set anywhere in your settings hierarchy, add
`http://127.0.0.1:8787/hook` to it or the hooks will not run.

## Using it

Hold the layer-3 thumb key. While it is held the 5-way drives the agent:

| Control | Action |
|---|---|
| `RIGHT` | approve the pending request |
| `LEFT` | deny it |
| `UP` / `DOWN` | previous / next session |
| `UP` held | cycle the detail line: tool, working directory, title |
| `CENTER` | acknowledge — clear a finished or errored session |
| `CENTER` held | halt the focused session at its next checkpoint |
| encoder | previous / next session |

Release the layer and the 5-way is arrow keys again.

These are daemon-side bindings (`Config.bindings`), not firmware. Changing what
a button does needs a daemon restart, not a reflash.

## The approval model

A physical approve button is an approval-fatigue machine, and a 16-character
screen cannot show you a reviewable command. The rules are deliberately narrow:

1. **Allowlist by tool.** `Config.hardware_approvable` lists what a button may
   approve: `Read`, `Grep`, `Glob`, `WebSearch`, `WebFetch`, `Edit`, `Write`,
   `NotebookEdit`. Anything else gets no decision from the daemon and appears
   as a normal terminal prompt.
2. **`Bash` is not on that list.** Only commands matching one of
   `Config.bash_prefix_allow` are eligible, compared after stripping leading
   `VAR=value` assignments, and rejected outright if they contain any shell
   metacharacter. `git diff && rm -rf /` starts with an allowed prefix and is
   not allowed.
3. **Timing out never approves.** After 90 seconds the daemon defers, and
   Claude Code prompts you normally. There is no auto-approve, no approve-all,
   and no hold-to-approve-repeatedly.
4. **Focus follows the request.** The daemon moves focus to the waiting session
   *before* repainting, so the button always acts on what is on screen. Without
   that you would eventually approve session B's write while reading session A.
5. **Summaries truncate from the left.** `rm -rf /very/long/path` cut to 16
   characters reads `rm -rf /very/lon`, which tells you what you need. Cut from
   the other end it reads `/long/path`, which tells you nothing.
6. **Every hardware decision is logged** to
   `~/.local/state/soflectl/decisions.jsonl`, with the full untruncated tool
   input. The screen only ever showed you a summary, so the log holds the rest.
   This is what lets you answer "what did I approve at 2am".

Widening `hardware_approvable` to include `Bash` wholesale would rebuild
`--dangerously-skip-permissions` with extra steps. The point of this design is
that the common case (approving a `Read`) is frictionless while the dangerous
case stays exactly as slow as it is today.

### `halt` is not immediate

There is no channel to a session between hook calls, so a halt is recorded and
delivered on the next hook that session happens to fire. It stops at the next
checkpoint, not now.

## Development

```bash
cd daemon
pip install -e '.[dev]'
python3 -m pytest
```

`tests/test_protocol.py` parses `agentctl/include/agentctl/protocol.h` and
asserts the C and Python constants agree, so the two halves of the wire format
cannot drift apart silently.

`python3 scripts/replay-hooks.py` POSTs a scripted session at a running daemon,
so you can exercise the whole path without Claude Code. Capture real payloads
and replay those when you can — a recorded `PermissionRequest` body is worth
more than any schema transcribed by hand.

## Limits worth knowing

- **One screen, the left one.** ZMK has no generic way to push data from the
  central to a peripheral, so the right half keeps its Mario animation. Getting
  the compact view onto it needs a custom GATT service sideloaded into the
  split connection; `SET_SYNC` already carries the data for when that happens.
- **The display is 68px wide.** That is about 16 characters at
  `lv_font_montserrat_8`, which is proportional — 16 is a budget, not a
  guarantee, and over-long lines clip rather than wrap.
- **The encoder is reported but not consumed.** ZMK does not guarantee listener
  ordering against the keymap's own sensor handling, so the agent layer binds
  the encoder to mouse scroll: turning it cycles sessions and also scrolls.
- **Subagent tool calls roll up into their parent session** rather than getting
  their own row.
