################################################################################
#
# spf_gainctl
#
################################################################################

SPF_GAINCTL_SITE = https://github.com/misko/plutosdr-fw.git
SPF_GAINCTL_SITE_METHOD = git
SPF_GAINCTL_VERSION = 27490b63f600c059ca9aa143e52e5f0af8ea62f3
# The CMake project lives in runtime/, not at the repository root.
SPF_GAINCTL_SUBDIR = runtime
SPF_GAINCTL_DEPENDENCIES = libiio
SPF_GAINCTL_LICENSE = GPL-2.0
# Tests are host-side and native; building them for the target would only add
# binaries nobody runs there.
SPF_GAINCTL_CONF_OPTS = -DBUILD_TESTING=OFF

$(eval $(cmake-package))
