################################################################################
#
# starlink_pssctl -- experimental do-not-merge firmware only
#
################################################################################

STARLINK_PSSCTL_SITE = $(TOPDIR)/../tools/starlink_pssctl
STARLINK_PSSCTL_SITE_METHOD = local
STARLINK_PSSCTL_LICENSE = GPL-2.0-or-later

define STARLINK_PSSCTL_BUILD_CMDS
	$(TARGET_CC) $(TARGET_CFLAGS) $(TARGET_LDFLAGS) \
		-std=c11 -Wall -Wextra -Werror -Wpedantic \
		$(@D)/starlink_pss_hw.c $(@D)/starlink_pssctl.c \
		-o $(@D)/starlink_pssctl
	$(TARGET_CC) $(TARGET_CFLAGS) $(TARGET_LDFLAGS) \
		-std=c11 -Wall -Wextra -Werror -Wpedantic \
		$(@D)/starlink_pss_acquisition.c $(@D)/starlink_pss_acqctl.c \
		-lm -o $(@D)/starlink_pss_acqctl
endef

define STARLINK_PSSCTL_INSTALL_TARGET_CMDS
	$(INSTALL) -D -m 0755 $(@D)/starlink_pssctl \
		$(TARGET_DIR)/usr/sbin/starlink_pssctl
	$(INSTALL) -D -m 0755 $(@D)/starlink_pss_acqctl \
		$(TARGET_DIR)/usr/sbin/starlink_pss_acqctl
	$(INSTALL) -D -m 0644 \
		$(TOPDIR)/../hdl/library/starlink_pss_raw_correlator/tb/upper_minus100k_coefficients_q15.mem \
		$(TARGET_DIR)/opt/starlink-pss/upper_minus100k_coefficients_q15.mem
	$(INSTALL) -D -m 0644 \
		$(TOPDIR)/../hdl/library/axi_starlink_pss_tracker/tb/real_071200_wrapper_replay_provenance.json \
		$(TARGET_DIR)/opt/starlink-pss/real_071200_wrapper_replay_provenance.json
	$(INSTALL) -D -m 0644 \
		$(TOPDIR)/../hdl/library/axi_starlink_pss_tracker/tb/real_071200_window0_samples_ci16.mem \
		$(TARGET_DIR)/opt/starlink-pss/real_071200_window0_samples_ci16.mem
endef

$(eval $(generic-package))
