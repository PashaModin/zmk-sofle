/*
 * agentctl wire protocol - keyboard side.
 *
 * The host daemon mirrors these constants in daemon/soflectl/protocol.py, and
 * daemon/tests/test_protocol.py parses this header to prove the two agree.
 * If you change an opcode here, that test fails until the daemon matches.
 *
 * SPDX-License-Identifier: MIT
 */

#pragma once

#include <zephyr/kernel.h>

/* Report size is fixed by the raw HID module (CONFIG_RAW_HID_REPORT_SIZE). */
#define AGENTCTL_REPORT_SIZE CONFIG_RAW_HID_REPORT_SIZE

/*
 * Text frame geometry.
 *
 * The nice!view is a 160x68 panel mounted sideways, so the readable area is
 * 68 wide by 160 tall. Content is drawn into square 68x68 canvases which are
 * then rotated, exactly as ZMK's own nice_view widget does.
 *
 * Two canvases cover 136 of the 160 readable pixels; the remaining 24 are left
 * unused rather than adding a third canvas that would be partly off-screen.
 * At 8px per row that is 8 rows per canvas, 16 rows total.
 *
 * Columns are approximate: lv_font_montserrat_8 is proportional, so 16 is a
 * budget rather than a guarantee. Labels clip at the canvas edge, so an
 * over-long line is truncated on screen rather than corrupting the layout.
 */
#define AGENTCTL_ROWS          16
#define AGENTCTL_COLS          16
#define AGENTCTL_ROWS_PER_BAND 8
#define AGENTCTL_BANDS         2

#define AGENTCTL_LABEL_LEN 12

/* Status values shared with the daemon. Keep in step with protocol.py. */
enum agentctl_status {
    AC_IDLE = 0,
    AC_THINKING,
    AC_TOOL,
    AC_WAITING,
    AC_DONE,
    AC_ERROR,
    AC_OFFLINE,
};

/* host -> keyboard */
enum {
    AC_SET_LINE = 0x01,
    AC_SET_SYNC = 0x02,
    AC_CLEAR    = 0x03,
    AC_PING     = 0x04,
    AC_SET_MODE = 0x05,
};

/* keyboard -> host */
enum {
    AC_EV_BUTTON  = 0x81,
    AC_EV_ENCODER = 0x82,
    AC_EV_HELLO   = 0x83,
    AC_EV_PONG    = 0x84,
};

enum {
    AC_BTN_UP = 0,
    AC_BTN_DOWN,
    AC_BTN_LEFT,
    AC_BTN_RIGHT,
    AC_BTN_CENTER,
};

enum {
    AC_ACT_TAP  = 0,
    AC_ACT_HOLD = 1,
};

#define AGENTCTL_PROTO_VERSION 1

/* Compact per-session summary. Sent as the payload of AC_SET_SYNC. */
struct agentctl_sync {
    uint8_t status;
    uint8_t badge;
    uint8_t session_idx;
    uint8_t session_count;
    char    label0[AGENTCTL_LABEL_LEN];
    char    label1[AGENTCTL_LABEL_LEN];
} __packed;

BUILD_ASSERT(sizeof(struct agentctl_sync) == 28, "sync struct size drifted");
BUILD_ASSERT(1 + sizeof(struct agentctl_sync) <= AGENTCTL_REPORT_SIZE,
             "sync payload does not fit in one report");

struct agentctl_state {
    struct agentctl_sync sync;
    char    frame[AGENTCTL_ROWS][AGENTCTL_COLS + 1];
    uint8_t mode; /* 0 normal, 1 approval pending */
    int64_t last_rx_ms;
    bool    ever_rx;
};

/* Snapshot of the state, safe to call from any thread. */
void agentctl_state_copy(struct agentctl_state *out);

/* Queue one packet to the host. Safe to call from an event listener: the
 * actual HID write happens on a work queue. */
void agentctl_send(uint8_t op, uint8_t a, uint8_t b, uint8_t c);

/* Ask the widget to repaint. Safe from any thread. */
void agentctl_notify_widget(void);
