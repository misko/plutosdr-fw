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

# The metadata path: encoding a controller record into the protocol-v3 wire
# record, draining the FIFO into a frame, and reconstructing the per-sample gain
# series. Separate from the lifecycle library because the gadget links this and
# not the control layer.
add_library(spf_tandem_meta STATIC spf_tandem_event.c spf_tandem_drain.c spf_tandem_fifo.c)
target_include_directories(spf_tandem_meta PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})

# the CLI links the iio backend only where libiio exists; the library and its
# tests never do, which is what keeps the transaction logic host-testable
find_library(IIO_LIBRARY iio)
find_path(IIO_INCLUDE_DIR iio.h)
add_executable(spf-gainctl spf_gainctl.c)
target_link_libraries(spf-gainctl spf_tandem_lifecycle)
if(IIO_LIBRARY AND IIO_INCLUDE_DIR)
  target_sources(spf-gainctl PRIVATE spf_tandem_iio.c)
  target_compile_definitions(spf-gainctl PRIVATE SPF_TANDEM_HAVE_IIO)
  target_include_directories(spf-gainctl PRIVATE ${IIO_INCLUDE_DIR})
  target_link_libraries(spf-gainctl ${IIO_LIBRARY})
  message(STATUS "spf-gainctl: libiio found, real backend enabled")
else()
  message(STATUS "spf-gainctl: no libiio, building without a backend")
endif()

if(BUILD_TESTING)
  enable_testing()
  add_executable(test_spf_tandem_lifecycle test_spf_tandem_lifecycle.c)
  target_link_libraries(test_spf_tandem_lifecycle spf_tandem_lifecycle)
  add_test(NAME spf_tandem_lifecycle COMMAND test_spf_tandem_lifecycle)

  add_executable(test_spf_tandem_ctl test_spf_tandem_ctl.c)
  target_link_libraries(test_spf_tandem_ctl spf_tandem_lifecycle)
  add_test(NAME spf_tandem_ctl COMMAND test_spf_tandem_ctl)

  add_executable(test_spf_tandem_event test_spf_tandem_event.c)
  target_link_libraries(test_spf_tandem_event spf_tandem_meta)
  add_test(NAME spf_tandem_event COMMAND test_spf_tandem_event)

  add_executable(test_spf_tandem_drain test_spf_tandem_drain.c)
  target_link_libraries(test_spf_tandem_drain spf_tandem_meta)
  add_test(NAME spf_tandem_drain COMMAND test_spf_tandem_drain)

  add_executable(test_spf_tandem_fifo test_spf_tandem_fifo.c)
  target_link_libraries(test_spf_tandem_fifo spf_tandem_meta)
  add_test(NAME spf_tandem_fifo COMMAND test_spf_tandem_fifo)
endif()
