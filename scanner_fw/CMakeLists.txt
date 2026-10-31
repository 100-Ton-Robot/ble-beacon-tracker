cmake_minimum_required(VERSION 3.20.0)

# The board's OpenOCD load (nrf54l-load) turns on the RRAM write buffer and
# never commits it, so the image's last partial buffer is lost and the app
# crashes in bt_enable. Load unbuffered instead (RRAMC CONFIG = WEN only).
# Must be defined before find_package: board.cmake finalizes runner args there.
set(SCANNER_FW_DIR ${CMAKE_CURRENT_LIST_DIR})
macro(app_set_runner_args)
  board_runner_args(openocd
    "--cmd-pre-init=source {${SCANNER_FW_DIR}/support/scanner-load.tcl}"
    "--cmd-load=scanner-load"
  )
endmacro()

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(scanner_fw)

target_sources(app PRIVATE src/main.c)
