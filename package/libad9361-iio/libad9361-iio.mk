################################################################################
#
# libad9361-iio
#
################################################################################
LIBAD9361_IIO_VERSION = 0.2
LIBAD9361_IIO_SITE = $(call github,analogdevicesinc,libad9361-iio,v$(LIBAD9361_IIO_VERSION))

LIBAD9361_IIO_INSTALL_STAGING = YES
LIBAD9361_IIO_LICENSE = LGPL-2.1+
LIBAD9361_IIO_LICENSE_FILES = LICENSE
LIBAD9361_IIO_DEPENDENCIES = libiio
# libad9361-iio 0.2 predates CMake 3.5.  CMake 4 removed implicit
# compatibility with older policy versions, so select the minimum policy
# version explicitly without changing the package's own build files.
LIBAD9361_IIO_CONF_OPTS = -DCMAKE_POLICY_VERSION_MINIMUM=3.5

$(eval $(cmake-package))
