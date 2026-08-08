#ifndef SPF_GAIN_SAMPLER_H
#define SPF_GAIN_SAMPLER_H

#include "spf_gain_metadata.h"

#include <pthread.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>

#define SPF_ADC_SAMPLE_COUNTER_LOW_REG UINT32_C(0x800000B8)
#define SPF_ADC_TIMESTAMP_CONTROL_REG UINT32_C(0x800000BC)
#define SPF_GAIN_SAMPLER_RING_CAPACITY 1024U

typedef struct
{
	pthread_t thread;
	pthread_mutex_t mutex;
	atomic_bool stop_requested;
	bool mutex_initialized;
	bool thread_started;
	atomic_bool ready;
	atomic_bool failed;
	uint32_t interval_samples;
	uint32_t count;
	uint32_t overflow_count;
	spf_gain_observation_v3_t records[SPF_GAIN_SAMPLER_RING_CAPACITY];
} spf_gain_sampler_t;

bool spf_gain_sampler_start(
	spf_gain_sampler_t *sampler,
	uint32_t interval_samples);
void spf_gain_sampler_stop(spf_gain_sampler_t *sampler);

/*
 * Copy ordered observations overlapping [frame_start, frame_start+samples).
 * Low-32 counter values are extended around the exact 64-bit inline frame
 * timestamp. Records older than the frame are retired from the bounded ring.
 */
uint16_t spf_gain_sampler_collect(
	spf_gain_sampler_t *sampler,
	uint64_t frame_start,
	uint32_t samples,
	spf_gain_observation_v3_t *destination,
	uint16_t capacity,
	uint32_t *overflow_count);

#endif
