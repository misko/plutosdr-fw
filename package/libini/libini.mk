################################################################################
#
# libini
#
################################################################################

LIBINI_VERSION = a467418
LIBINI_SITE = https://github.com/pcercuei/libini.git
LIBINI_SITE_METHOD = git

LIBINI_INSTALL_STAGING = YES
LIBINI_LICENSE = LGPLv2.1+
LIBINI_LICENSE_FILES = LICENSE.txt
# libini predates CMake 3.5.  CMake 4 requires the compatibility policy
# floor to be selected explicitly for otherwise unchanged legacy projects.
LIBINI_CONF_OPTS = -DCMAKE_POLICY_VERSION_MINIMUM=3.5

$(eval $(cmake-package))
