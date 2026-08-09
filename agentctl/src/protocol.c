/*
 * Inbound raw HID packet handling, and the outbound send path.
 *
 * SPDX-License-Identifier: MIT
 */

#include <zephyr/kernel.h>
#include <zephyr/init.h>
#include <zephyr/logging/log.h>
#include <string.h>

#include <zmk/event_manager.h>
#include <raw_hid/events.h>

#include "agentctl/protocol.h"

LOG_MODULE_REGISTER(agentctl, CONFIG_AGENTCTL_LOG_LEVEL);

static struct agentctl_state s_state;
static K_MUTEX_DEFINE(s_lock);

void agentctl_state_copy(struct agentctl_state *out) {
    k_mutex_lock(&s_lock, K_FOREVER);
    *out = s_state;
    k_mutex_unlock(&s_lock);
}

/* ------------------------------------------------------------------ */
/* Outbound                                                            */
/* ------------------------------------------------------------------ */

/*
 * raise_raw_hid_sent_event() runs its listeners synchronously on the calling
 * thread, and the USB listener blocks for up to 30ms waiting on the HID
 * endpoint semaphore. Calling it straight from a key event listener would
 * stall key scanning for that long, so outbound packets go through a small
 * ring buffer drained by a dedicated work item on the system work queue.
 */
#define TX_SLOTS 8

struct tx_packet {
    uint8_t data[AGENTCTL_REPORT_SIZE];
};

static struct tx_packet s_tx[TX_SLOTS];
static uint8_t s_tx_head;
static uint8_t s_tx_tail;
static K_MUTEX_DEFINE(s_tx_lock);

static void tx_work_cb(struct k_work *work) {
    ARG_UNUSED(work);

    for (;;) {
        struct tx_packet pkt;

        k_mutex_lock(&s_tx_lock, K_FOREVER);
        if (s_tx_head == s_tx_tail) {
            k_mutex_unlock(&s_tx_lock);
            return;
        }
        pkt = s_tx[s_tx_tail];
        s_tx_tail = (s_tx_tail + 1) % TX_SLOTS;
        k_mutex_unlock(&s_tx_lock);

        raise_raw_hid_sent_event((struct raw_hid_sent_event){
            .data = pkt.data,
            .length = sizeof(pkt.data),
        });
    }
}

static K_WORK_DEFINE(s_tx_work, tx_work_cb);

void agentctl_send(uint8_t op, uint8_t a, uint8_t b, uint8_t c) {
    k_mutex_lock(&s_tx_lock, K_FOREVER);

    uint8_t next = (uint8_t)((s_tx_head + 1) % TX_SLOTS);
    if (next == s_tx_tail) {
        /* Queue full: drop the oldest rather than the newest, so a burst of
         * button presses reports the most recent intent. */
        s_tx_tail = (uint8_t)((s_tx_tail + 1) % TX_SLOTS);
        LOG_WRN("tx queue full, dropped a packet");
    }

    struct tx_packet *pkt = &s_tx[s_tx_head];
    memset(pkt->data, 0, sizeof(pkt->data));
    pkt->data[0] = op;
    pkt->data[1] = a;
    pkt->data[2] = b;
    pkt->data[3] = c;
    s_tx_head = next;

    k_mutex_unlock(&s_tx_lock);

    k_work_submit(&s_tx_work);
}

/* ------------------------------------------------------------------ */
/* Inbound                                                             */
/* ------------------------------------------------------------------ */

static void blank_frame(void) {
    for (int r = 0; r < AGENTCTL_ROWS; r++) {
        memset(s_state.frame[r], ' ', AGENTCTL_COLS);
        s_state.frame[r][AGENTCTL_COLS] = '\0';
    }
}

static void handle_packet(const uint8_t *d, size_t len) {
    if (len < 1) {
        return;
    }

    bool repaint = true;

    k_mutex_lock(&s_lock, K_FOREVER);

    s_state.last_rx_ms = k_uptime_get();
    s_state.ever_rx = true;

    switch (d[0]) {
    case AC_SET_LINE: {
        if (len < 3) {
            break;
        }
        uint8_t row = d[1];
        uint8_t n = d[2];
        if (row >= AGENTCTL_ROWS) {
            break;
        }
        if (n > AGENTCTL_COLS) {
            n = AGENTCTL_COLS;
        }
        if (len < (size_t)3 + n) {
            break;
        }
        memset(s_state.frame[row], ' ', AGENTCTL_COLS);
        for (uint8_t i = 0; i < n; i++) {
            uint8_t ch = d[3 + i];
            /* Anything outside printable ASCII would render as a missing
             * glyph, so substitute rather than trust the host. */
            s_state.frame[row][i] = (ch >= 0x20 && ch < 0x7F) ? (char)ch : '?';
        }
        s_state.frame[row][AGENTCTL_COLS] = '\0';
        break;
    }

    case AC_SET_SYNC:
        if (len < 1 + sizeof(struct agentctl_sync)) {
            break;
        }
        memcpy(&s_state.sync, &d[1], sizeof(struct agentctl_sync));
        /* v1 shows this on the central only. Forwarding it to the peripheral
         * would need a custom GATT service; see docs/soflectl.md. */
        break;

    case AC_CLEAR:
        memset(&s_state.sync, 0, sizeof(s_state.sync));
        s_state.mode = 0;
        blank_frame();
        break;

    case AC_PING:
        if (len >= 5) {
            /* Echo the first three timestamp bytes; enough for the daemon to
             * match a reply to its request. */
            agentctl_send(AC_EV_PONG, d[1], d[2], d[3]);
        }
        repaint = false;
        break;

    case AC_SET_MODE:
        if (len >= 2) {
            s_state.mode = d[1];
        }
        break;

    default:
        LOG_WRN("unknown opcode 0x%02x", d[0]);
        repaint = false;
        break;
    }

    k_mutex_unlock(&s_lock);

    if (repaint) {
        agentctl_notify_widget();
    }
}

static int raw_hid_listener(const zmk_event_t *eh) {
    struct raw_hid_received_event *ev = as_raw_hid_received_event(eh);

    if (ev && ev->data) {
        handle_packet(ev->data, ev->length);
    }

    return ZMK_EV_EVENT_BUBBLE;
}

ZMK_LISTENER(agentctl_raw_hid, raw_hid_listener);
ZMK_SUBSCRIPTION(agentctl_raw_hid, raw_hid_received_event);

/* ------------------------------------------------------------------ */
/* Startup                                                             */
/* ------------------------------------------------------------------ */

/*
 * Announce ourselves once the USB/BLE stack has had a chance to come up. The
 * daemon treats HELLO as "the keyboard rebooted, resend everything".
 */
static void hello_cb(struct k_work *work) {
    ARG_UNUSED(work);
    agentctl_send(AC_EV_HELLO, AGENTCTL_PROTO_VERSION, AGENTCTL_ROWS, AGENTCTL_COLS);
}

static K_WORK_DELAYABLE_DEFINE(s_hello_work, hello_cb);

static int agentctl_init(void) {
    k_mutex_lock(&s_lock, K_FOREVER);
    blank_frame();
    k_mutex_unlock(&s_lock);

    k_work_schedule(&s_hello_work, K_SECONDS(3));
    return 0;
}

SYS_INIT(agentctl_init, APPLICATION, CONFIG_APPLICATION_INIT_PRIORITY);
