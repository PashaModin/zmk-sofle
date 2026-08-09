# Hardware reference

Facts about this specific keyboard, each verified against the board definition
in `boards/arm/eyelash_sofle/` or against ZMK v0.3.0 itself.
Written down
because most of them are not obvious from the outside and several differ from
what generic Sofle guides assume.

## Controllers and roles

Both halves run an **nRF52840** (nice!nano-class). ZMK splits are not symmetric:

| | Left half | Right half |
|---|---|---|
| Split role | **Central** | Peripheral |
| USB | enabled | disabled |
| Bluetooth to your computer | yes | never |
| Holds the keymap | yes | no |
| Rotary encoder | yes | - |
| 5-way nav switch | - | **yes** |

Set in `Kconfig.defconfig` (`ZMK_SPLIT_ROLE_CENTRAL default y` for the left
board) and the two `_defconfig` files.

The consequence worth remembering: **the right half can only talk to the left
half, never to your computer.** It sends its key presses over Bluetooth to the
left half, which owns the keymap and sends the actual HID reports. So a keymap
change only requires reflashing the left half.

## Key positions

ZMK identifies keys by their index in the `bindings` array of a layer, counting
from 0, left to right and top to bottom. The 5-way nav switch in the middle of
the board sits at these indices:

| Direction | Position | Half | Base-layer binding |
|---|---|---|---|
| Up | **6** | right | `&kp UP_ARROW` |
| Down | **19** | right | `&kp DOWN_ARROW` |
| Left | **32** | right | `&kp LEFT_ARROW` |
| Right | **45** | right | `&kp RIGHT_ARROW` |
| Centre (press in) | **58** | right | `&kp ENTER` |

The encoder's push-button is position **52** (`&kp C_MUTE`), on the left half.

All five nav contacts are wired to column 7, which is the right half's first
column - that is why they are peripheral-side even though they sit in the middle
of the board.

To re-derive these yourself, or to find any other position, either enable
`CONFIG_ZMK_USB_LOGGING=y` in `config/eyelash_sofle.conf` and watch the log
while pressing keys, or open the keyboard in [ZMK Studio](https://zmk.studio)
and hover a key.

## Displays

Both halves carry a **nice!view**, which is a Sharp memory LCD - not the small
OLED that most Sofle build guides describe. From `nice_view.overlay` in ZMK:

```
compatible = "sharp,ls0xx";  width = <160>;  height = <68>;
```

So the framebuffer is 160 x 68 pixels, 1 bit per pixel. But ZMK's stock widget
rotates everything 270 degrees before drawing (`rotate_canvas()` in
`nice_view/widgets/util.c`), because the panel is mounted sideways. **The area
you actually read is 68 pixels wide and 160 pixels tall - portrait.**

That width is the constraint that matters for anything you want to display:

| Font | Columns across 68 px | Rows down 160 px |
|---|---|---|
| `lv_font_unscii_8` (8x8, ZMK's only built-in monospace) | 8 | 20 |
| A 4x6 bitmap font (Tom Thumb style, would need generating) | 17 | 26 |

Eight characters is not enough for text. Anything text-heavy needs a narrower
font built with `lv_font_conv`.

Two more things about the display stack:

- ZMK's `nice_view` shield already defines `zmk_display_status_screen()`. Custom
  firmware that wants to draw its own screen must set
  `CONFIG_NICE_VIEW_WIDGET_STATUS=n`, or the two definitions collide at link
  time. Disabling it also drops the shield's `select LV_FONT_UNSCII_8` and
  `select ZMK_WPM`, which then have to be selected explicitly.
- **Never call LVGL from a ZMK event listener.** Listeners run on the event
  manager's thread and LVGL is not thread-safe here. Use the
  `ZMK_DISPLAY_WIDGET_LISTENER` macro from `zmk/display.h`, which moves the
  repaint onto the display work queue for you.

The right half currently runs `nice_view_custom` (the Mario animation) from the
`mario-peripheral-animation` module rather than ZMK's stock widget.

## How configuration files are resolved

ZMK searches `config/` for files matching the board and shield names
(`app/boards/post_boards_shields.cmake`). Two rules are easy to get wrong:

- **`.conf` files: every match is applied**, in order. So
  `config/eyelash_sofle.conf` (matched on the board *directory* name, shared by
  both halves) and `config/eyelash_sofle_left.conf` (matched on the specific
  board name) would both take effect on a left-half build. This is how you add
  central-only settings.
- **`.overlay` files: only the first match is applied**, and the search stops
  there. A `nice_view.overlay` would silently shadow an `eyelash_sofle.overlay`.

## Sleep

`CONFIG_ZMK_SLEEP=y` with `CONFIG_ZMK_IDLE_SLEEP_TIMEOUT=3600000` puts the
keyboard into deep sleep after an hour idle, which switches the displays off and
drops the Bluetooth link until the next keypress.

Note that `CONFIG_ZMK_IDLE_SLEEP_TIMEOUT` (deep sleep) and `CONFIG_ZMK_IDLE_TIMEOUT`
(the much shorter idle state, which only dims things) are different symbols and
are easy to confuse.

## Keeping ZMK's version consistent

Two places refer to ZMK, and **they must name the same release**:

- `config/west.yml` pins the firmware source (`zmk`, currently `v0.3.0`).
- `.github/workflows/build.yml` pins the reusable build workflow
  (`build-user-config.yml@v0.3.0`).

The reusable workflow and the firmware are one codebase. If the workflow tracks
`@main` while `west.yml` pins a release, you get a build script from a much
newer ZMK driving an older one, and it fails in a thoroughly misleading way.

That is exactly what this repository did, and it is worth recording because the
symptom points nowhere near the cause: the firmware **built and linked
perfectly**, producing a valid `.uf2` — and then the job failed in a check that
runs *after* the build. Newer ZMK looks for `CONFIG_ZMK_BOARD_COMPAT=y`, and
when it is missing runs `west boards --format "{qualifiers}"`. Zephyr 3.5 has no
`qualifiers` field, so `west` raises `KeyError: 'qualifiers'`, the step exits
non-zero, and CI never reaches the step that uploads the firmware. The build log
looks like a success followed by an unrelated crash.

Pinning both to the same release fixes it. When upgrading ZMK, change both.

## Board definition format

The board lives in `boards/arm/eyelash_sofle/` and uses Zephyr's **hardware
model v1**: `Kconfig.board`, plain `<board>.dts`, `<board>_defconfig`, and a
board target of just `eyelash_sofle_left`.

This is correct for ZMK v0.3.0, which is built on Zephyr 3.5 and whose own
boards are all v1 — there is not a single `board.yml` in its tree. Do not
"modernise" this to hardware model v2 while pinned to v0.3.0; Zephyr 3.5 does
not understand `board.yml` and will simply report

```
No board named 'eyelash_sofle_left/nrf52840/zmk' found.
```

Hardware model v2 — vendor directories, `board.yml`, qualified targets like
`eyelash_sofle_left/nrf52840/zmk` — becomes *required* only if you move to a ZMK
built on Zephyr 4.1 (currently `main`). That migration is a package deal: it
also moves LVGL 8 to LVGL 9, which breaks the `nice_view_custom` Mario shield,
since it still calls `lv_canvas_transform()` and `LV_IMG_ZOOM_NONE`. ZMK v0.3.0
is on LVGL 8, which is why that shield works today.

## Versions this was checked against

| Component | Revision |
|---|---|
| ZMK | `v0.3.0` (`edf5c08`) — Zephyr 3.5, LVGL 8, hardware model v1 |
| `mario-peripheral-animation` | `1aa3950`, last commit 2024-09-02 |

Both are pinned in `config/west.yml`, and the build workflow is pinned to the
same ZMK release in `.github/workflows/build.yml`. See the comments in both.
