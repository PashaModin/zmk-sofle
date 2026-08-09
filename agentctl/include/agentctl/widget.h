/*
 * SPDX-License-Identifier: MIT
 */

#pragma once

#include <lvgl.h>
#include <zephyr/kernel.h>

#include "agentctl/protocol.h"

#define AGENTCTL_CANVAS_SIZE 68

struct zmk_widget_agentctl {
    sys_snode_t node;
    lv_obj_t   *obj;
    lv_obj_t   *canvas[AGENTCTL_BANDS];
    lv_color_t  cbuf[AGENTCTL_CANVAS_SIZE * AGENTCTL_CANVAS_SIZE];
    lv_color_t  cbuf2[AGENTCTL_CANVAS_SIZE * AGENTCTL_CANVAS_SIZE];
};

int zmk_widget_agentctl_init(struct zmk_widget_agentctl *widget, lv_obj_t *parent);
lv_obj_t *zmk_widget_agentctl_obj(struct zmk_widget_agentctl *widget);
