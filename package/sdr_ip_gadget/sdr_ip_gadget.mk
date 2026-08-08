SDR_IP_GADGET_SITE = https://github.com/misko/plutosdr-fw.git
SDR_IP_GADGET_SITE_METHOD = git
SDR_IP_GADGET_VERSION = 4cf0df9259fe52e17d6ffbc1e9afa0b77c74861c
SDR_IP_GADGET_DEPENDENCIES = libiio sdr_usb_gadget zlib
SDR_IP_GADGET_CONF_OPTS = \
	-DGIT_VERSION_OVERRIDE=4cf0df9259fe52e17d6ffbc1e9afa0b77c74861c \
	-DGENERATE_STATS=OFF \
	-DSPF_COMMON_ROOT=$(STAGING_DIR)/usr

$(eval $(cmake-package))
