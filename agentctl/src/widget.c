/*
 * The agent status widget.
 *
 * Geometry follows ZMK's own nice_view widget: the panel's framebuffer is
 * 160x68, but it is mounted sideways, so content is drawn into square 68x68
 * canvases in reading orientation and each is rotated 90 degrees before being
 * placed across the framebuffer's long axis. Two canvases give 136 of the 160
 * readable pixels; see agentctl/include/agentctl/protocol.h for why we stop at
 * two rather than three.
 *
 * LVGL is not thread safe here. Nothing in this file may be called from an
 * event listener directly - agentctl_notify_widget() bounces the repaint onto
 * the display work queue.
 *
 * SPDX-License-Identifier: MIT
 */

#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <stdio.h>
#include <string.h>

#include <lvgl.h>
#include <zmk/display.h>

#include "agentctl/protocol.h"
#include "agentctl/widget.h"

LOG_MODULE_DECLARE(agentctl, CONFIG_AGENTCTL_LOG_LEVEL);

#define CANVAS_SIZE 68
#define ROW_H       8

/* The nice!view is black on white by default; invert for the pending state. */
#define COLOR_BG lv_color_white()
#define COLOR_FG lv_color_black()

static sys_slist_t widgets = SYS_SLIST_STATIC_INIT(&widgets);

static void rotate_canvas(lv_obj_t *canvas, lv_color_t cbuf[]) {
    static lv_color_t cbuf_tmp[CANVAS_SIZE * CANVAS_SIZE];

    memcpy(cbuf_tmp, cbuf, sizeof(cbuf_tmp));

    lv_img_dsc_t img;
    img.data = (void *)cbuf_tmp;
    img.header.cf = LV_IMG_CF_TRUE_COLOR;
    img.header.w = CANVAS_SIZE;
    img.header.h = CANVAS_SIZE;

    lv_canvas_transform(canvas, &img, 900, LV_IMG_ZOOM_NONE, -1, 0, CANVAS_SIZE / 2,
                        CANVAS_SIZE / 2, true);
}

static void draw_band(lv_obj_t *canvas, lv_color_t cbuf[], const struct agentctl_state *st,
                      int first_row, bool inverted) {
    lv_color_t bg = inverted ? COLOR_FG : COLOR_BG;
    lv_color_t fg = inverted ? COLOR_BG : COLOR_FG;

    lv_canvas_fill_bg(canvas, bg, LV_OPA_COVER);

    lv_draw_label_dsc_t label_dsc;
    lv_draw_label_dsc_init(&label_dsc);
    label_dsc.color = fg;
    label_dsc.font = &lv_font_montserrat_8;
    label_dsc.align = LV_TEXT_ALIGN_LEFT;

    for (int i = 0; i < AGENTCTL_ROWS_PER_BAND; i++) {
        int row = first_row + i;
        if (row >= AGENTCTL_ROWS) {
            break;
        }

        const char *text = st->frame[row];
        /* Skip blank rows so LVGL does not spend time laying out spaces. */
        if (text[strspn(text, " ")] == '\0') {
            continue;
        }

        lv_canvas_draw_text(canvas, 0, i * ROW_H, CANVAS_SIZE, &label_dsc, (char *)text);
    }

    rotate_canvas(canvas, cbuf);
}

static void repaint(struct zmk_widget_agentctl *widget) {
    struct agentctl_state st;
    agentctl_state_copy(&st);

    /* The host stops sending when it dies. Say so rather than showing a frame
     * that has quietly stopped being true. */
    bool stale = st.ever_rx && (k_uptime_get() - st.last_rx_ms) > CONFIG_AGENTCTL_STALE_MS;

    if (!st.ever_rx || stale) {
        memset(st.frame, 0, sizeof(st.frame));
        snprintf(st.frame[0], AGENTCTL_COLS + 1, "soflectl");
        snprintf(st.frame[1], AGENTCTL_COLS + 1, "%s", stale ? "host offline" : "waiting...");
        st.mode = 0;
    }

    bool inverted = (st.mode == 1);

    draw_band(widget->canvas[0], widget->cbuf, &st, 0, inverted);
    draw_band(widget->canvas[1], widget->cbuf2, &st, AGENTCTL_ROWS_PER_BAND, inverted);
}

static void repaint_work_cb(struct k_work *work) {
    ARG_UNUSED(work);

    struct zmk_widget_agentctl *widget;
    SYS_SLIST_FOR_EACH_CONTAINER(&widgets, widget, node) { repaint(widget); }
}

static K_WORK_DELAYABLE_DEFINE(s_repaint_work, repaint_work_cb);

void agentctl_notify_widget(void) {
    if (!zmk_display_is_initialized()) {
        return;
    }

    /*
     * Coalesce repaints. PostToolUse fires on every single tool call, and a
     * memory-LCD repaint is not free; ~10Hz is plenty for a status display and
     * keeps the display thread from competing with key scanning.
     */
    k_work_reschedule_for_queue(zmk_display_work_q(), &s_repaint_work, K_MSEC(100));
}

int zmk_widget_agentctl_init(struct zmk_widget_agentctl *widget, lv_obj_t *parent) {
    widget->obj = lv_obj_create(parent);
    lv_obj_set_size(widget->obj, 160, 68);

    widget->canvas[0] = lv_canvas_create(widget->obj);
    lv_obj_align(widget->canvas[0], LV_ALIGN_TOP_RIGHT, 0, 0);
    lv_canvas_set_buffer(widget->canvas[0], widget->cbuf, CANVAS_SIZE, CANVAS_SIZE,
                         LV_IMG_CF_TRUE_COLOR);

    widget->canvas[1] = lv_canvas_create(widget->obj);
    lv_obj_align(widget->canvas[1], LV_ALIGN_TOP_LEFT, 24, 0);
    lv_canvas_set_buffer(widget->canvas[1], widget->cbuf2, CANVAS_SIZE, CANVAS_SIZE,
                         LV_IMG_CF_TRUE_COLOR);

    sys_slist_append(&widgets, &widget->node);

    repaint(widget);

    return 0;
}

lv_obj_t *zmk_widget_agentctl_obj(struct zmk_widget_agentctl *widget) { return widget->obj; }
