#include "spf_gain_sampler.h"

#include <assert.h>
#include <string.h>
#include <time.h>

typedef struct
{
	spf_gain_sampler_t *sampler;
	uint32_t delay_ns;
	uint64_t elapsed_ns;
	bool interrupted;
} interruptible_wait_test_t;

static uint64_t elapsed_ns(
	const struct timespec *start,
	const struct timespec *end)
{
	return ((uint64_t)end->tv_sec * UINT64_C(1000000000) +
		(uint64_t)end->tv_nsec) -
		((uint64_t)start->tv_sec * UINT64_C(1000000000) +
		(uint64_t)start->tv_nsec);
}

static void *run_interruptible_wait(void *opaque)
{
	interruptible_wait_test_t *test = opaque;
	struct timespec start;
	struct timespec end;
	assert(clock_gettime(CLOCK_MONOTONIC, &start) == 0);
	test->interrupted = spf_gain_sampler_wait_interruptible(
		test->sampler, test->delay_ns);
	assert(clock_gettime(CLOCK_MONOTONIC, &end) == 0);
	test->elapsed_ns = elapsed_ns(&start, &end);
	return NULL;
}

static void *announce_observation(void *opaque)
{
	spf_gain_sampler_t *sampler = opaque;
	const struct timespec delay = {.tv_sec = 0, .tv_nsec = 1000000};
	nanosleep(&delay, NULL);
	pthread_mutex_lock(&sampler->mutex);
	sampler->capture_started = sampler->capture_requested;
	pthread_cond_broadcast(&sampler->credit_cond);
	while (sampler->capture_finished < sampler->capture_started)
		pthread_cond_wait(&sampler->credit_cond, &sampler->mutex);
	sampler->capture_observed = sampler->capture_started;
	pthread_cond_broadcast(&sampler->credit_cond);
	pthread_mutex_unlock(&sampler->mutex);
	return NULL;
}

int main(void)
{
	assert(spf_gain_sampler_poll_delay_ns(0, 0, 0, UINT32_C(20000000)) == 0);
	assert(spf_gain_sampler_poll_delay_ns(
		UINT32_C(262144), 0, 0, UINT32_C(20000000)) ==
		UINT32_C(6553600));
	assert(spf_gain_sampler_poll_delay_ns(
		UINT32_C(1048576), 0, 0, UINT32_C(20000000)) ==
		UINT32_C(26214400));
	assert(spf_gain_sampler_poll_delay_ns(
		UINT32_C(4000000), 0, 0, UINT32_C(1000000)) ==
		SPF_GAIN_SAMPLER_POLL_MAX_NS);
	assert(spf_gain_sampler_poll_delay_ns(
		UINT32_C(32768), 0, 0, UINT32_C(61440000)) == UINT32_C(266666));
	assert(spf_gain_sampler_poll_delay_ns(
		UINT32_C(32768), UINT32_C(31744), 0, UINT32_C(61440000)) ==
		SPF_GAIN_SAMPLER_POLL_MIN_NS);
	assert(spf_gain_sampler_poll_delay_ns(
		UINT32_C(512), UINT32_C(256), UINT32_C(0xFFFFFF00),
		UINT32_C(20000000)) == 0);
	assert(spf_gain_frame_decide(0, 1, 0) == SPF_GAIN_FRAME_ACCEPT);
	assert(spf_gain_frame_decide(27, 1, 0) == SPF_GAIN_FRAME_ACCEPT);
	assert(spf_gain_frame_decide(0, 0, 0) ==
		SPF_GAIN_FRAME_DISCARD_STARTUP);
	assert(spf_gain_frame_decide(
		0, 0, SPF_GAIN_STARTUP_DISCARD_LIMIT - 1) ==
		SPF_GAIN_FRAME_DISCARD_STARTUP);
	assert(spf_gain_frame_decide(
		0, 0, SPF_GAIN_STARTUP_DISCARD_LIMIT) == SPF_GAIN_FRAME_REJECT);
	assert(spf_gain_frame_decide(1, 0, 0) == SPF_GAIN_FRAME_REJECT);

	spf_gain_sampler_t sampler;
	memset(&sampler, 0, sizeof(sampler));
	assert(pthread_mutex_init(&sampler.mutex, NULL) == 0);
	sampler.mutex_initialized = true;
	assert(pthread_cond_init(&sampler.credit_cond, NULL) == 0);
	sampler.credit_cond_initialized = true;
	atomic_init(&sampler.idle, false);
	atomic_init(&sampler.failed, false);
	atomic_init(&sampler.stop_requested, false);
	atomic_init(&sampler.force_observation, false);
	interruptible_wait_test_t wait_test = {
		.sampler = &sampler,
		.delay_ns = UINT32_C(500000000),
	};
	pthread_t waiter;
	assert(pthread_create(&waiter, NULL, run_interruptible_wait, &wait_test) == 0);
	const struct timespec wake_delay = {.tv_sec = 0, .tv_nsec = 1000000};
	nanosleep(&wake_delay, NULL);
	pthread_mutex_lock(&sampler.mutex);
	atomic_store_explicit(
		&sampler.force_observation, true, memory_order_release);
	pthread_cond_broadcast(&sampler.credit_cond);
	pthread_mutex_unlock(&sampler.mutex);
	assert(pthread_join(waiter, NULL) == 0);
	assert(wait_test.interrupted);
	assert(wait_test.elapsed_ns < UINT64_C(250000000));
	atomic_store(&sampler.force_observation, false);
	wait_test = (interruptible_wait_test_t){
		.sampler = &sampler,
		.delay_ns = UINT32_C(20000000),
	};
	assert(pthread_create(&waiter, NULL, run_interruptible_wait, &wait_test) == 0);
	nanosleep(&wake_delay, NULL);
	pthread_mutex_lock(&sampler.mutex);
	pthread_cond_broadcast(&sampler.credit_cond);
	pthread_mutex_unlock(&sampler.mutex);
	assert(pthread_join(waiter, NULL) == 0);
	assert(!wait_test.interrupted);
	assert(wait_test.elapsed_ns >= UINT64_C(10000000));
	sampler.interval_samples = UINT32_C(250000);
	assert(!spf_gain_sampler_observation_due(
		&sampler, UINT32_C(1000), UINT32_C(900)));
	atomic_store(&sampler.force_observation, true);
	assert(spf_gain_sampler_observation_due(
		&sampler, UINT32_C(1000), UINT32_C(900)));
	assert(!atomic_load(&sampler.force_observation));
	assert(spf_gain_sampler_observation_due(
		&sampler, UINT32_C(251000), UINT32_C(1000)));
	sampler.interval_samples = UINT32_C(512);
	assert(spf_gain_sampler_observation_due(
		&sampler, UINT32_C(256), UINT32_C(0xFFFFFF00)));
	sampler.interval_samples = UINT32_C(250000);
	spf_gain_sampler_limit(&sampler, UINT64_C(4096));
	assert(sampler.bounded);
	assert(sampler.sample_credit == UINT64_C(4096));
	spf_gain_sampler_add_credit(&sampler, UINT64_C(2048));
	assert(sampler.sample_credit == UINT64_C(6144));
	pthread_t announcer;
	assert(pthread_create(&announcer, NULL, announce_observation, &sampler) == 0);
	assert(spf_gain_sampler_limit_and_wait_started(
		&sampler, UINT64_C(2048), UINT32_C(100)));
	assert(atomic_load(&sampler.force_observation));
	atomic_store(&sampler.force_observation, false);
	assert(spf_gain_sampler_finish_capture(&sampler, UINT32_C(100)));
	assert(pthread_join(announcer, NULL) == 0);
	assert(sampler.sample_credit == UINT64_C(2048));
	assert(!spf_gain_sampler_limit_and_wait_started(
		&sampler, UINT64_C(2048), UINT32_C(1)));
	assert(!atomic_load(&sampler.force_observation));
	assert(!spf_gain_sampler_is_idle(&sampler));
	sampler.count = 2;
	sampler.records[0] = (spf_gain_observation_v3_t){
		.sample_sequence_before = UINT32_C(0xFFFFFF00),
		.sample_sequence_after = UINT32_C(0xFFFFFFF0),
		.flags = SPF_GAIN_OBSERVATION_SAMPLE_INTERVAL_VALID,
	};
	sampler.records[1] = (spf_gain_observation_v3_t){
		.sample_sequence_before = UINT32_C(0x00000010),
		.sample_sequence_after = UINT32_C(0x00001000),
		.flags = SPF_GAIN_OBSERVATION_SAMPLE_INTERVAL_VALID,
	};
	spf_gain_observation_v3_t output[2];
	uint32_t overflow = 0;
	const uint16_t count = spf_gain_sampler_collect(
		&sampler,
		UINT64_C(0x1FFFFFF80),
		UINT32_C(0x2000),
		output,
		2,
		&overflow);
	assert(count == 2);
	assert(output[0].sample_sequence_before == UINT64_C(0x1FFFFFF00));
	assert(output[1].sample_sequence_before == UINT64_C(0x200000010));
	assert(overflow == 0);

	sampler.rssi_count = 2;
	sampler.rssi_records[0] = (spf_rssi_observation_t){
		.sample_sequence_before = UINT32_C(0xFFFFFF80),
		.sample_sequence_after = UINT32_C(0xFFFFFF90),
		.value = {.rx1_qdb = 400, .rx2_qdb = 404, .valid = true},
	};
	sampler.rssi_records[1] = (spf_rssi_observation_t){
		.sample_sequence_before = UINT32_C(0x00000100),
		.sample_sequence_after = UINT32_C(0x00000110),
		.value = {.rx1_qdb = 408, .rx2_qdb = 412, .valid = true},
	};
	spf_rssi_pair_t rssi_start;
	spf_rssi_pair_t rssi_end;
	assert(spf_gain_sampler_collect_rssi(
		&sampler,
		UINT64_C(0x1FFFFFF80),
		UINT32_C(0x400),
		&rssi_start,
		&rssi_end,
		&overflow));
	assert(rssi_start.rx1_qdb == 400);
	assert(rssi_end.rx1_qdb == 408);
	assert(overflow == 0);
	pthread_cond_destroy(&sampler.credit_cond);
	pthread_mutex_destroy(&sampler.mutex);
	return 0;
}
