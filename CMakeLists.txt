cmake_minimum_required(VERSION 3.5)

project(sdr_usb_gadget LANGUAGES C)

# Options
option(GENERATE_STATS "Generate and output runtime stats" OFF)
option(BUILD_HOST_TESTS "Build host-only protocol and metadata tests" OFF)

# From: https://www.mattkeeter.com/blog/2018-01-06-versioning/
execute_process(COMMAND git log --pretty=format:'%h' -n 1
                OUTPUT_VARIABLE GIT_REV
                ERROR_QUIET)
if ("${GIT_REV}" STREQUAL "")
    set(GIT_REV "N/A")
    set(GIT_DIFF "")
else()
    execute_process(
        COMMAND bash -c "git diff --quiet --exit-code || echo +"
        OUTPUT_VARIABLE GIT_DIFF)

    string(STRIP "${GIT_REV}" GIT_REV)
    #string(SUBSTRING "${GIT_REV}" 1 7 GIT_REV)
    string(STRIP "${GIT_DIFF}" GIT_DIFF)
endif()
set(GIT_VERSION "${GIT_REV}${GIT_DIFF}")

if (NOT "${GIT_VERSION_OVERRIDE}" STREQUAL "")
    # Use provided override if package isn't being built within git repo
    set(GIT_VERSION "${GIT_VERSION_OVERRIDE}")
endif()

add_executable(sdr_usb_gadget
    main.c
    usb_descriptors.c
    epoll_loop.c
    ring_buffer.c
    thread_read.c
    thread_write.c
    spf_gain_read.c
    spf_rssi_read.c
    spf_control_policy.c
    spf_runtime_status.c
    spf_thread_join.c
    utils.c
)
target_link_libraries(sdr_usb_gadget
    pthread
    aio
    iio
)
target_compile_definitions(sdr_usb_gadget PRIVATE
    PROGRAM_VERSION="${GIT_VERSION}"
    STATS_PERIOD_SECS=2)
if (GENERATE_STATS)
target_compile_definitions(sdr_usb_gadget PRIVATE GENERATE_STATS=1)
endif(GENERATE_STATS)

install(TARGETS sdr_usb_gadget RUNTIME DESTINATION sbin)

if (BUILD_HOST_TESTS)
    enable_testing()

    add_executable(test_spf_gain_metadata test_spf_gain_metadata.c)
    add_test(NAME spf_gain_metadata_v1 COMMAND test_spf_gain_metadata)

    add_executable(test_spf_radio_metadata_v2 test_spf_radio_metadata_v2.c)
    add_test(NAME spf_radio_metadata_v2 COMMAND test_spf_radio_metadata_v2)

    add_executable(test_spf_gain_read
        test_spf_gain_read.c
        spf_gain_read.c)
    target_link_libraries(test_spf_gain_read iio)
    add_test(NAME spf_gain_read COMMAND test_spf_gain_read)

    add_executable(test_spf_rssi_read
        test_spf_rssi_read.c
        spf_rssi_read.c)
    target_link_libraries(test_spf_rssi_read iio)
    add_test(NAME spf_rssi_read COMMAND test_spf_rssi_read)

    add_executable(test_sdr_usb_gadget_protocol
        test_sdr_usb_gadget_protocol.c)
    add_test(NAME sdr_usb_gadget_protocol COMMAND test_sdr_usb_gadget_protocol)

    add_executable(test_spf_buffer_policy test_spf_buffer_policy.c)
    add_test(NAME spf_buffer_policy COMMAND test_spf_buffer_policy)

    add_executable(test_spf_cleanup_plan test_spf_cleanup_plan.c)
    add_test(NAME spf_cleanup_plan COMMAND test_spf_cleanup_plan)

    add_executable(test_spf_runtime_status
        test_spf_runtime_status.c
        spf_runtime_status.c)
    target_link_libraries(test_spf_runtime_status pthread)
    add_test(NAME spf_runtime_status COMMAND test_spf_runtime_status)

    add_executable(test_spf_thread_join
        test_spf_thread_join.c
        spf_thread_join.c)
    target_link_libraries(test_spf_thread_join pthread)
    add_test(NAME spf_thread_join COMMAND test_spf_thread_join)

    add_executable(test_spf_control_policy
        test_spf_control_policy.c
        spf_control_policy.c)
    add_test(NAME spf_control_policy COMMAND test_spf_control_policy)
endif()
