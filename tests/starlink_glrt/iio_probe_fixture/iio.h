/* Test-only subset of libiio 0.x. The production build uses the real header. */
#include <stdbool.h>
#include <stddef.h>
#include <sys/types.h>
struct iio_context;
struct iio_device;
struct iio_channel;
struct iio_buffer;
struct iio_data_format {
    unsigned length,bits,shift;
    bool is_signed,is_fully_defined,is_be,with_scale;
    double scale;
    unsigned repeat;
};
struct iio_context *iio_create_local_context(void);
void iio_context_destroy(struct iio_context *);
const char *iio_context_get_attr_value(const struct iio_context *,const char *);
int iio_context_set_timeout(struct iio_context *,unsigned);
struct iio_device *iio_context_find_device(const struct iio_context *,const char *);
struct iio_channel *iio_device_find_channel(const struct iio_device *,const char *,bool);
unsigned iio_device_get_channels_count(const struct iio_device *);
struct iio_channel *iio_device_get_channel(const struct iio_device *,unsigned);
ssize_t iio_device_get_sample_size(const struct iio_device *);
ssize_t iio_device_attr_read(const struct iio_device *,const char *,char *,size_t);
int iio_device_attr_write_longlong(const struct iio_device *,const char *,long long);
int iio_device_set_kernel_buffers_count(const struct iio_device *,unsigned);
void iio_channel_disable(struct iio_channel *);
void iio_channel_enable(struct iio_channel *);
bool iio_channel_is_scan_element(const struct iio_channel *);
bool iio_channel_is_output(const struct iio_channel *);
long iio_channel_get_index(const struct iio_channel *);
const struct iio_data_format *iio_channel_get_data_format(const struct iio_channel *);
ssize_t iio_channel_attr_read(const struct iio_channel *,const char *,char *,size_t);
struct iio_buffer *iio_device_create_buffer(const struct iio_device *,size_t,bool);
void iio_buffer_destroy(struct iio_buffer *);
int iio_buffer_set_blocking_mode(struct iio_buffer *,bool);
ssize_t iio_buffer_refill(struct iio_buffer *);
ptrdiff_t iio_buffer_step(const struct iio_buffer *);
void *iio_buffer_start(const struct iio_buffer *);
void *iio_buffer_end(const struct iio_buffer *);
