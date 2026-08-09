#
# Copyright (c) 2024 The ZMK Contributors
# SPDX-License-Identifier: MIT
#

# Suppresses duplicate unit-address warnings at build time for the nRF52840's
# power, clock, acl and flash-controller nodes.
# https://docs.zephyrproject.org/latest/build/dts/intro-input-output.html

list(APPEND EXTRA_DTC_FLAGS "-Wno-unique_unit_address_if_enabled")
