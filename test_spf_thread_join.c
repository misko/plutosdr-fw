#define _DEFAULT_SOURCE

#include "spf_thread_join.h"

#include <assert.h>
#include <errno.h>
#include <unistd.h>

static void *short_worker(void *argument)
{
	const useconds_t delay_us = *(const useconds_t *)argument;
	usleep(delay_us);
	return NULL;
}

int main(void)
{
	pthread_t thread;
	int error_number = -1;
	useconds_t delay_us = 10000;
	assert(pthread_create(&thread, NULL, short_worker, &delay_us) == 0);
	assert(spf_thread_join_bounded(thread, 500, &error_number) ==
		SPF_THREAD_JOIN_OK);
	assert(error_number == 0);

	delay_us = 200000;
	assert(pthread_create(&thread, NULL, short_worker, &delay_us) == 0);
	assert(spf_thread_join_bounded(thread, 20, &error_number) ==
		SPF_THREAD_JOIN_TIMEOUT);
	assert(error_number == ETIMEDOUT);
	/* A timeout never cancels or detaches the worker behind the caller's back. */
	assert(pthread_join(thread, NULL) == 0);
	return 0;
}
