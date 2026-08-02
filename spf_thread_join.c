#define _GNU_SOURCE

#include "spf_thread_join.h"

#include <errno.h>
#include <time.h>

spf_thread_join_result_t spf_thread_join_bounded(
	pthread_t thread,
	uint32_t timeout_ms,
	int *error_number)
{
	struct timespec deadline = {0, 0};
	if (clock_gettime(CLOCK_REALTIME, &deadline) != 0)
	{
		if (error_number)
			*error_number = errno;
		return SPF_THREAD_JOIN_ERROR;
	}
	deadline.tv_sec += (time_t)(timeout_ms / UINT32_C(1000));
	deadline.tv_nsec +=
		(long)(timeout_ms % UINT32_C(1000)) * 1000000L;
	if (deadline.tv_nsec >= 1000000000L)
	{
		deadline.tv_sec++;
		deadline.tv_nsec -= 1000000000L;
	}

	const int result = pthread_timedjoin_np(thread, NULL, &deadline);
	if (result == 0)
	{
		if (error_number)
			*error_number = 0;
		return SPF_THREAD_JOIN_OK;
	}
	if (error_number)
		*error_number = result;
	return result == ETIMEDOUT
		? SPF_THREAD_JOIN_TIMEOUT
		: SPF_THREAD_JOIN_ERROR;
}
