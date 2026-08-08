cmake_minimum_required(VERSION 3.9.4)

project(sdr_ip_gadget LANGUAGES C)

include(CTest)

# Options
option(GENERATE_STATS "Generate and output runtime stats" OFF)

set(SPF_COMMON_ROOT "" CACHE PATH
    "Prefix containing the SPF gain-observation and frame libraries")
find_path(SPF_COMMON_INCLUDE_DIR spf/spf_radio_frame_v3.h
    HINTS "${SPF_COMMON_ROOT}/include")
find_library(SPF_RADIO_FRAME_LIBRARY spf_radio_frame_v3
    HINTS "${SPF_COMMON_ROOT}/lib")
find_library(SPF_GAIN_OBSERVATION_LIBRARY spf_gain_observation
    HINTS "${SPF_COMMON_ROOT}/lib")
if(NOT SPF_COMMON_INCLUDE_DIR OR NOT SPF_RADIO_FRAME_LIBRARY OR
   NOT SPF_GAIN_OBSERVATION_LIBRARY)
    message(FATAL_ERROR
        "SPF common v3 libraries are required; set SPF_COMMON_ROOT")
endif()

# Check if link time optimisation is supported
include(CheckIPOSupported)
check_ipo_supported(RESULT lto_supported OUTPUT lto_error)

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

add_executable(sdr_ip_gadget
    main.c
    epoll_loop.c
    thread_read.c
	thread_read_v3.c
    thread_write.c
    utils.c
	spf_ip_protocol.c
)
target_link_libraries(sdr_ip_gadget
    pthread
    iio
	z
	${SPF_RADIO_FRAME_LIBRARY}
	${SPF_GAIN_OBSERVATION_LIBRARY}
)
target_include_directories(sdr_ip_gadget PRIVATE ${SPF_COMMON_INCLUDE_DIR})
target_compile_definitions(sdr_ip_gadget PRIVATE
    PROGRAM_VERSION="${GIT_VERSION}"
    STATS_PERIOD_SECS=2)
if (GENERATE_STATS)
target_compile_definitions(sdr_ip_gadget PRIVATE GENERATE_STATS=1)
endif(GENERATE_STATS)

if(lto_supported)
    message(STATUS "LTO enabled")
    set_property(TARGET sdr_ip_gadget PROPERTY INTERPROCEDURAL_OPTIMIZATION TRUE)
else()
    message(STATUS "LTO not supported: <${lto_error}>")
endif()

if(BUILD_TESTING)
	add_executable(test_spf_ip_protocol
		test_spf_ip_protocol.c
		spf_ip_protocol.c
	)
	target_link_libraries(test_spf_ip_protocol z)
	add_test(NAME spf_ip_protocol COMMAND test_spf_ip_protocol)

	add_executable(test_spf_ip_frame_pipeline
		test_spf_ip_frame_pipeline.c
		spf_ip_protocol.c)
	target_include_directories(test_spf_ip_frame_pipeline PRIVATE
		${SPF_COMMON_INCLUDE_DIR})
	target_link_libraries(test_spf_ip_frame_pipeline
		z
		${SPF_RADIO_FRAME_LIBRARY})
	add_test(NAME spf_ip_frame_pipeline COMMAND test_spf_ip_frame_pipeline)
endif()

install(TARGETS sdr_ip_gadget RUNTIME DESTINATION sbin)
