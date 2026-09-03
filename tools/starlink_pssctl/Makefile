HOST_CC ?= cc
CROSS_CC ?= ../../buildroot/output/host/bin/arm-linux-gnueabihf-gcc
CFLAGS ?= -O2 -g
WARNINGS := -std=c11 -Wall -Wextra -Werror -Wpedantic
BUILD := build
COEFFICIENT_FIXTURE := ../../hdl/library/starlink_pss_raw_correlator/tb/upper_minus100k_coefficients_q15.mem
PACKET_FIXTURE := ../../hdl/library/axi_starlink_pss_tracker/tb/real_071200_wrapper_packets.mem
INJECTION_FIXTURE := ../../hdl/library/axi_starlink_pss_tracker/tb/real_071200_window0_samples_ci16.mem

.PHONY: all arm check clean sanitize test

all: test arm

$(BUILD):
	mkdir -p $@

$(BUILD)/test_starlink_pss_hw: starlink_pss_hw.c starlink_pss_hw.h test_starlink_pss_hw.c | $(BUILD)
	$(HOST_CC) $(CFLAGS) $(WARNINGS) starlink_pss_hw.c test_starlink_pss_hw.c -o $@

$(BUILD)/test_starlink_pss_acquisition: starlink_pss_acquisition.c starlink_pss_acquisition.h test_starlink_pss_acquisition.c | $(BUILD)
	$(HOST_CC) $(CFLAGS) $(WARNINGS) starlink_pss_acquisition.c test_starlink_pss_acquisition.c -lm -o $@

$(BUILD)/test_starlink_pss_acquisition_sanitize: starlink_pss_acquisition.c starlink_pss_acquisition.h test_starlink_pss_acquisition.c | $(BUILD)
	$(HOST_CC) -O1 -g $(WARNINGS) -fsanitize=address,undefined -fno-omit-frame-pointer starlink_pss_acquisition.c test_starlink_pss_acquisition.c -lm -o $@

$(BUILD)/starlink_pss_acqctl-host: starlink_pss_acquisition.c starlink_pss_acquisition.h starlink_pss_acqctl.c | $(BUILD)
	$(HOST_CC) $(CFLAGS) $(WARNINGS) starlink_pss_acquisition.c starlink_pss_acqctl.c -lm -o $@

$(BUILD)/starlink_pssctl: starlink_pss_hw.c starlink_pss_hw.h starlink_pssctl.c | $(BUILD)
	$(CROSS_CC) $(CFLAGS) $(WARNINGS) -static starlink_pss_hw.c starlink_pssctl.c -o $@

$(BUILD)/starlink_pss_acqctl: starlink_pss_acquisition.c starlink_pss_acquisition.h starlink_pss_acqctl.c | $(BUILD)
	$(CROSS_CC) $(CFLAGS) $(WARNINGS) -static starlink_pss_acquisition.c starlink_pss_acqctl.c -lm -o $@

test: $(BUILD)/test_starlink_pss_hw $(BUILD)/test_starlink_pss_acquisition $(BUILD)/starlink_pss_acqctl-host
	$(BUILD)/test_starlink_pss_hw $(COEFFICIENT_FIXTURE) $(PACKET_FIXTURE) $(INJECTION_FIXTURE)
	$(BUILD)/test_starlink_pss_acquisition
	$(BUILD)/starlink_pss_acqctl-host --help >/dev/null

arm: $(BUILD)/starlink_pssctl $(BUILD)/starlink_pss_acqctl
	file $(BUILD)/starlink_pssctl
	file $(BUILD)/starlink_pss_acqctl

sanitize: $(BUILD)/test_starlink_pss_acquisition_sanitize
	ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 UBSAN_OPTIONS=halt_on_error=1 $(BUILD)/test_starlink_pss_acquisition_sanitize

check: test arm

clean:
	rm -f $(BUILD)/test_starlink_pss_hw $(BUILD)/test_starlink_pss_acquisition
	rm -f $(BUILD)/test_starlink_pss_acquisition_sanitize
	rm -f $(BUILD)/starlink_pssctl $(BUILD)/starlink_pss_acqctl
	rm -f $(BUILD)/starlink_pss_acqctl-host
