# Eyelash Sofle — ZMK configuration

Personal firmware configuration for an **Eyelash Sofle**: a 58-key split
keyboard running [ZMK](https://zmk.dev), with a rotary encoder on the left half,
a 5-way navigation switch in the middle, per-key backlight, RGB underglow, and a
[nice!view](https://nicekeyboards.com/nice-view/) display on each half.

You do not need a local toolchain. GitHub Actions builds the firmware on every
push and attaches the result to the workflow run.

- **[docs/hardware.md](docs/hardware.md)** — verified facts about this board:
  key positions, display geometry, which half does what.
- **[docs/soflectl.md](docs/soflectl.md)** — using the keyboard as a control
  surface for Claude Code: what the display shows, and what the 5-way switch
  approves.
- **[docs/upstream.md](docs/upstream.md)** — the original vendor's changelog and
  contact details, kept from the repository this was forked from.

## Current keymap

<img src="keymap-drawer/sofle.svg">

This image is regenerated automatically by the "Draw Keymap" workflow whenever
`config/` changes, so it always matches the firmware.

## Layers

Layers are held, not toggled — the keyboard returns to the base layer when you
let go.

| # | Name | Held with | What it gives you |
|---|---|---|---|
| 0 | Base | *(default)* | QWERTY. Encoder turns volume up/down. Nav switch is arrow keys, pressing it in is Enter. |
| 1 | Nav & Mouse | left thumb (`&mo 1`) | F1–F12, mouse buttons, Home/End/PgUp/PgDn, arrow cluster on the right hand, RGB underglow controls. Encoder scrolls. Nav switch moves the mouse pointer. |
| 2 | System | right thumb (`&mo 2`) | Bluetooth profile select and clear, USB/Bluetooth output switching, bootloader, reset, soft-off. Encoder scrolls. |
| 3 | Agent & Media | right-hand bottom row (`&mo 3`) | Screen brightness, play/pause, next/previous track, volume. While held, the 5-way switch drives Claude Code — see [docs/soflectl.md](docs/soflectl.md). |

## Build and flash

### Getting the firmware

1. Push a change, or open the **Actions** tab and run **Build ZMK firmware**
   manually.
2. Open the finished run and download the **firmware** artifact.
3. Unzip it. You get one `.uf2` per image:

   | File | Flash it to | When |
   |---|---|---|
   | `eyelash_sofle_left.uf2` | left half | every keymap or config change |
   | `eyelash_sofle_right.uf2` | right half | only for board or display changes |
   | `eyelash_sofle_reset_left.uf2` | left half | recovery only, see below |
   | `eyelash_sofle_reset_right.uf2` | right half | recovery only, see below |

### Flashing a half

1. Plug that half into USB.
2. Double-tap the reset button. A USB drive called `NICENANO` appears.
3. Drag the `.uf2` onto it. The drive disconnects on its own — that means it
   worked.

Because the left half is the central and holds the whole keymap, **routine
keymap edits only need the left half reflashed.**

## Editing the keymap

Three options, in rough order of convenience:

- **[ZMK Studio](https://zmk.studio)** — plug the left half in over USB and edit
  the keymap live in a browser, no rebuild and no reflash. Enabled in this build
  (that is what the `studio-rpc-usb-uart` snippet in `build.yaml` is for).
  Changes made here live in the keyboard's own settings, not in this repository.
- **[keymap-editor](https://nickcoutsos.github.io/keymap-editor/)** — a visual
  editor that commits straight back to this repository, using
  `config/eyelash_sofle.json` for the physical layout. Note that it rewrites
  `config/eyelash_sofle.keymap` wholesale, which discards any comments in that
  file.
- **Editing `config/eyelash_sofle.keymap` by hand** — full control, and the only
  way to use behaviours the editors do not expose. Push, wait for the build,
  flash the left half.

## Repository layout

```
build.yaml                     Which firmware images CI builds. Commented.
config/
  west.yml                     Pinned external dependencies (ZMK, Mario display)
  eyelash_sofle.keymap         The keymap: layers, encoder, behaviours
  eyelash_sofle.conf           Kconfig settings shared by both halves. Commented.
  eyelash_sofle.json           Physical layout, used by keymap-editor
boards/arm/eyelash_sofle/
                               Board definition: pins, matrix, encoder, displays.
                               Comes from the vendor; you rarely touch this.
agentctl/                      Firmware for the Claude Code control surface.
daemon/                        The soflectl host daemon, and its tests.
scripts/                       Helpers for setting soflectl up.
claude/                        Paste-able Claude Code hook configuration.
keymap-drawer/                 Auto-generated keymap images. Do not edit by hand.
docs/                          Hardware reference, soflectl guide, upstream notes.
.github/workflows/             Build and keymap-drawing automation.
```

## Troubleshooting

**The halves will not connect to each other.** Flash `eyelash_sofle_reset_left.uf2`
and `eyelash_sofle_reset_right.uf2` to their respective halves, then flash the
normal images again. This clears the stored pairing so the two halves rediscover
each other.

**Only one half types.** The right half has no keymap and cannot reach your
computer on its own — if the left half is unpowered or unflashed, nothing works.
Check the left half first.

**The keyboard stops responding after being left alone.** That is deep sleep,
after one hour idle. Press any key. To change the delay, or disable it, see
`CONFIG_ZMK_SLEEP` in `config/eyelash_sofle.conf`.

**A build fails after you changed nothing.** It should not — `config/west.yml`
pins every dependency to an exact commit. If it happens anyway, check that
nobody changed those revisions.

## Credits

Forked from the vendor configuration for the Eyelash Sofle. The board definition
under `boards/` and the original documentation are theirs; see
[docs/upstream.md](docs/upstream.md).

Built on [ZMK](https://zmk.dev). The right-hand display animation comes from
[GPeye/mario-peripheral-animation](https://github.com/GPeye/mario-peripheral-animation).
