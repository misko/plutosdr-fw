################################################################################
#
# spf_metadata_source
#
################################################################################

SPF_METADATA_SOURCE_VERSION = c11d5715cb89408c25bed14a5ae8d7848f96c293
SPF_METADATA_SOURCE_SITE = $(call github,misko,plutosdr-fw,$(SPF_METADATA_SOURCE_VERSION))
SPF_METADATA_SOURCE_INSTALL_STAGING = YES
SPF_METADATA_SOURCE_LICENSE = MIT
SPF_METADATA_SOURCE_LICENSE_FILES = LICENSE

SPF_METADATA_SOURCE_FILES = \
	spf_gain_metadata.h \
	spf_gain_read.c \
	spf_gain_read.h \
	spf_gain_sampler.c \
	spf_gain_sampler.h \
	spf_radio_frame_v3.c \
	spf_radio_frame_v3.h \
	spf_rssi_read.c \
	spf_rssi_read.h

define SPF_METADATA_SOURCE_INSTALL_STAGING_CMDS
	mkdir -p $(STAGING_DIR)/usr/include/spf
	mkdir -p $(STAGING_DIR)/usr/share/spf-metadata-source
	$(foreach file,$(filter %.h,$(SPF_METADATA_SOURCE_FILES)),\
		$(INSTALL) -m 0644 $(@D)/$(file) $(STAGING_DIR)/usr/include/spf/$(file)$(sep))
	$(foreach file,$(filter %.c,$(SPF_METADATA_SOURCE_FILES)),\
		$(INSTALL) -m 0644 $(@D)/$(file) $(STAGING_DIR)/usr/share/spf-metadata-source/$(file)$(sep))
endef

$(eval $(generic-package))
