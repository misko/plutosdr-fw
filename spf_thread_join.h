#ifndef __SPF_THREAD_JOIN_H__
#define __SPF_THREAD_JOIN_H__

#include <pthread.h>
#include <stdint.h>

typedef enum
{
	SPF_THREAD_JOIN_OK = 0,
	SPF_THREAD_JOIN_TIMEOUT = 1,
	SPF_THREAD_JOIN_ERROR = 2,
} spf_thread_join_result_t;

spf_thread_join_result_t spf_thread_join_bounded(
	pthread_t thread,
	uint32_t timeout_ms,
	int *error_number);

#endif
