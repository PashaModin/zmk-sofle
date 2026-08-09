# Builds the agentctl sources. Everything here is inert unless CONFIG_AGENTCTL
# is set, so the peripheral half and the settings_reset images are unaffected.

if(CONFIG_AGENTCTL)
  zephyr_library_named(agentctl)
  zephyr_library_include_directories(agentctl/include)
  zephyr_library_include_directories(${ZEPHYR_BASE}/../zmk/app/include)

  zephyr_library_sources(agentctl/src/protocol.c)
  zephyr_library_sources(agentctl/src/input.c)
  zephyr_library_sources(agentctl/src/widget.c)
  zephyr_library_sources(agentctl/src/status_screen.c)
endif()
