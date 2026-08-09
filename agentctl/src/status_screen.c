/*
 * Supplies zmk_display_status_screen() for the central half.
 *
 * ZMK allows exactly one definition of this symbol. The nice_view shield
 * normally provides it, so config/eyelash_sofle_left.conf sets
 * CONFIG_NICE_VIEW_WIDGET_STATUS=n to stand its version down; without that the
 * two definitions collide at link time.
 *
 * SPDX-License-Identifier: MIT
 */

#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>

#include <lvgl.h>

#include "agentctl/widget.h"

LOG_MODULE_DECLARE(agentctl, CONFIG_AGENTCTL_LOG_LEVEL);

static struct zmk_widget_agentctl agent_widget;

lv_obj_t *zmk_display_status_screen(void) {
    lv_obj_t *screen = lv_obj_create(NULL);

    zmk_widget_agentctl_init(&agent_widget, screen);
    lv_obj_align(zmk_widget_agentctl_obj(&agent_widget), LV_ALIGN_TOP_LEFT, 0, 0);

    return screen;
}
