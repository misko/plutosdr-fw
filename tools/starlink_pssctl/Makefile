HOST_CC ?= cc
CROSS_CC ?= ../../buildroot/output/host/bin/arm-linux-gnueabihf-gcc
CFLAGS ?= -O2 -g
WARNINGS := -std=c11 -Wall -Wextra -Werror -Wpedantic
BUILD := build
COEFFICIENT_FIXTURE := ../../hdl/library/starlink_pss_raw_correlator/tb/upper_minus100k_coefficients_q15.mem
PACKET_FIXTURE := ../../hdl/library/axi_starlink_pss_tracker/tb/real_071200_wrapper_packets.mem
INJECTION_FIXTURE := ../../hdl/library/axi_starlink_pss_tracker/tb/real_071200_window0_samples_ci16.mem

.PHONY: all test arm check clean

all: test arm

$(BUILD):
	mkdir -p $@

$(BUILD)/test_starlink_pss_hw: starlink_pss_hw.c starlink_pss_hw.h test_starlink_pss_hw.c | $(BUILD)
	$(HOST_CC) $(CFLAGS) $(WARNINGS) starlink_pss_hw.c test_starlink_pss_hw.c -o $@

$(BUILD)/starlink_pssctl: starlink_pss_hw.c starlink_pss_hw.h starlink_pssctl.c | $(BUILD)
	$(CROSS_CC) $(CFLAGS) $(WARNINGS) -static starlink_pss_hw.c starlink_pssctl.c -o $@

test: $(BUILD)/test_starlink_pss_hw
	$(BUILD)/test_starlink_pss_hw $(COEFFICIENT_FIXTURE) $(PACKET_FIXTURE) $(INJECTION_FIXTURE)

arm: $(BUILD)/starlink_pssctl
	file $(BUILD)/starlink_pssctl

check: test arm

clean:
	rm -f $(BUILD)/test_starlink_pss_hw $(BUILD)/starlink_pssctl
