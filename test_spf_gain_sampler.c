#include "spf_gain_sampler.h"

#include <assert.h>
#include <string.h>
#include <time.h>

static void *announce_observation(void *opaque)
{
	spf_gain_sampler_t *sampler = opaque;
	const struct timespec delay = {.tv_sec = 0, .tv_nsec = 1000000};
	nanosleep(&delay, NULL);
	pthread_mutex_lock(&sampler->mutex);
	sampler->observations_started++;
	pthread_cond_broadcast(&sampler->credit_cond);
	pthread_mutex_unlock(&sampler->mutex);
	return NULL;
}

int main(void)
{
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
	spf_gain_sampler_limit(&sampler, UINT64_C(4096));
	assert(sampler.bounded);
	assert(sampler.sample_credit == UINT64_C(4096));
	spf_gain_sampler_add_credit(&sampler, UINT64_C(2048));
	assert(sampler.sample_credit == UINT64_C(6144));
	pthread_t announcer;
	assert(pthread_create(&announcer, NULL, announce_observation, &sampler) == 0);
	assert(spf_gain_sampler_limit_and_wait_started(
		&sampler, UINT64_C(2048), UINT32_C(100)));
	assert(pthread_join(announcer, NULL) == 0);
	assert(sampler.sample_credit == UINT64_C(2048));
	assert(!spf_gain_sampler_limit_and_wait_started(
		&sampler, UINT64_C(2048), UINT32_C(1)));
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
