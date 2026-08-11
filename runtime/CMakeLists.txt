# Tandem AGC runtime. The lifecycle is deliberately a pure state machine with
# no syscalls and no hardware access, so it builds and tests natively on the
# host exactly as RC17's spf_ip_rx_lifecycle does -- that factoring is what
# makes every failure path reachable in a unit test.
cmake_minimum_required(VERSION 3.13)
project(spf_tandem_runtime C)

set(CMAKE_C_STANDARD 99)
add_compile_options(-Wall -Wextra -Werror)

add_library(spf_tandem_lifecycle STATIC spf_tandem_lifecycle.c spf_tandem_ctl.c)
target_include_directories(spf_tandem_lifecycle PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})

if(BUILD_TESTING)
  enable_testing()
  add_executable(test_spf_tandem_lifecycle test_spf_tandem_lifecycle.c)
  target_link_libraries(test_spf_tandem_lifecycle spf_tandem_lifecycle)
  add_test(NAME spf_tandem_lifecycle COMMAND test_spf_tandem_lifecycle)

  add_executable(test_spf_tandem_ctl test_spf_tandem_ctl.c)
  target_link_libraries(test_spf_tandem_ctl spf_tandem_lifecycle)
  add_test(NAME spf_tandem_ctl COMMAND test_spf_tandem_ctl)
endif()
