#include "spf_gain_sampler.h"

#include <assert.h>
#include <string.h>

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
	pthread_mutex_destroy(&sampler.mutex);
	return 0;
}
