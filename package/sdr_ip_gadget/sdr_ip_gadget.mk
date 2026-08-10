SDR_IP_GADGET_SITE = https://github.com/misko/plutosdr-fw.git
SDR_IP_GADGET_SITE_METHOD = git
SDR_IP_GADGET_VERSION = 7cae12eb62cfb2fb656169bd1cfe7da2a0aff583
SDR_IP_GADGET_DEPENDENCIES = libiio sdr_usb_gadget zlib
SDR_IP_GADGET_CONF_OPTS = \
	-DGIT_VERSION_OVERRIDE=7cae12eb62cfb2fb656169bd1cfe7da2a0aff583 \
	-DGENERATE_STATS=OFF \
	-DSPF_COMMON_ROOT=$(STAGING_DIR)/usr

$(eval $(cmake-package))
