/*
 * Reports the 5-way navigation switch and the encoder to the host.
 *
 * Both are read as raw events rather than as keymap behaviours. Key positions
 * are relayed from the peripheral to the central automatically, so this works
 * even though the 5-way is physically on the right half while raw HID only
 * exists on the left.
 *
 * Everything here is gated on the agent layer being active. On every other
 * layer the events bubble through untouched, so the 5-way stays arrow keys and
 * mouse movement exactly as before.
 *
 * SPDX-License-Identifier: MIT
 */

#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>

#include <zmk/event_manager.h>
#include <zmk/events/position_state_changed.h>
#include <zmk/events/sensor_event.h>
#include <zmk/keymap.h>
#include <zmk/sensors.h>

#include "agentctl/protocol.h"

LOG_MODULE_DECLARE(agentctl, CONFIG_AGENTCTL_LOG_LEVEL);

/* Key positions of the 5-way switch, in UP DOWN LEFT RIGHT CENTER order.
 * See docs/hardware.md for how these were derived. */
static const uint32_t POS[5] = {
    CONFIG_AGENTCTL_POS_UP,   CONFIG_AGENTCTL_POS_DOWN,  CONFIG_AGENTCTL_POS_LEFT,
    CONFIG_AGENTCTL_POS_RIGHT, CONFIG_AGENTCTL_POS_CENTER,
};

static int64_t s_press_at[5];
static uint8_t s_down_mask;

static int8_t pos_to_btn(uint32_t position) {
    for (int i = 0; i < 5; i++) {
        if (POS[i] == position) {
            return (int8_t)i;
        }
    }
    return -1;
}

static bool agent_layer_active(void) {
    return zmk_keymap_layer_active((zmk_keymap_layer_id_t)CONFIG_AGENTCTL_LAYER);
}

static int position_listener(const zmk_event_t *eh) {
    const struct zmk_position_state_changed *ev = as_zmk_position_state_changed(eh);
    if (!ev) {
        return ZMK_EV_EVENT_BUBBLE;
    }

    int8_t btn = pos_to_btn(ev->position);
    if (btn < 0) {
        return ZMK_EV_EVENT_BUBBLE; /* not one of ours */
    }

    if (!agent_layer_active()) {
        /* Make sure a press that started on the agent layer and was released
         * after leaving it cannot report later. */
        s_down_mask &= (uint8_t)~(1u << btn);
        return ZMK_EV_EVENT_BUBBLE;
    }

    if (ev->state) {
        s_down_mask |= (uint8_t)(1u << btn);
        s_press_at[btn] = ev->timestamp;
        return ZMK_EV_EVENT_HANDLED;
    }

    uint8_t mask_at_release = s_down_mask;
    s_down_mask &= (uint8_t)~(1u << btn);

    if (!(mask_at_release & (1u << btn))) {
        /* Released without a matching press on this layer. Swallow it so the
         * keymap does not see a stray release. */
        return ZMK_EV_EVENT_HANDLED;
    }

    /* A 5-way switch can bridge two contacts when pushed diagonally. Two or
     * more down at once is ambiguous, so report nothing rather than guess. */
    if (mask_at_release & (mask_at_release - 1)) {
        LOG_DBG("ignoring co-actuated press, mask 0x%02x", mask_at_release);
        return ZMK_EV_EVENT_HANDLED;
    }

    int64_t held = ev->timestamp - s_press_at[btn];
    uint8_t action = (held >= CONFIG_AGENTCTL_HOLD_MS) ? AC_ACT_HOLD : AC_ACT_TAP;

    agentctl_send(AC_EV_BUTTON, (uint8_t)btn, action, 0);

    return ZMK_EV_EVENT_HANDLED;
}

ZMK_LISTENER(agentctl_pos, position_listener);
ZMK_SUBSCRIPTION(agentctl_pos, zmk_position_state_changed);

/*
 * Encoder. Reported only while the agent layer is held, and deliberately
 * bubbled rather than consumed: ZMK does not guarantee listener ordering
 * against the keymap's own sensor handling, so consuming here would work by
 * accident at best. The agent layer therefore binds the encoder to mouse
 * scroll, which is harmless to trigger alongside focus cycling.
 */
static int sensor_listener(const zmk_event_t *eh) {
    const struct zmk_sensor_event *ev = as_zmk_sensor_event(eh);
    if (!ev || !agent_layer_active()) {
        return ZMK_EV_EVENT_BUBBLE;
    }

    if (ev->channel_data_size < 1) {
        return ZMK_EV_EVENT_BUBBLE;
    }

    /* Rotation is reported as a signed value; only the direction matters. */
    const struct sensor_value *value = &ev->channel_data[0].value;
    int32_t delta = value->val1;
    if (delta == 0) {
        delta = value->val2;
    }
    if (delta == 0) {
        return ZMK_EV_EVENT_BUBBLE;
    }

    agentctl_send(AC_EV_ENCODER, ev->sensor_index, delta > 0 ? 1 : 0, 0);

    return ZMK_EV_EVENT_BUBBLE;
}

ZMK_LISTENER(agentctl_sensor, sensor_listener);
ZMK_SUBSCRIPTION(agentctl_sensor, zmk_sensor_event);
