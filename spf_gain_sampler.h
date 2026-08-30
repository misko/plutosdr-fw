#ifndef SPF_GAIN_SAMPLER_H
#define SPF_GAIN_SAMPLER_H

#include "spf_gain_metadata.h"
#include "spf_rssi_read.h"

#include <pthread.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>

#define SPF_ADC_SAMPLE_COUNTER_LOW_REG UINT32_C(0x800000B8)
#define SPF_ADC_TIMESTAMP_CONTROL_REG UINT32_C(0x800000BC)
#define SPF_GAIN_SAMPLER_RING_CAPACITY 1024U
#define SPF_GAIN_STARTUP_DISCARD_LIMIT 64U
#define SPF_GAIN_SAMPLER_POLL_MIN_NS UINT32_C(100000)
#define SPF_GAIN_SAMPLER_POLL_MAX_NS UINT32_C(50000000)

typedef enum
{
	SPF_GAIN_FRAME_ACCEPT = 0,
	SPF_GAIN_FRAME_DISCARD_STARTUP,
	SPF_GAIN_FRAME_REJECT,
} spf_gain_frame_decision_t;

typedef struct
{
	uint64_t sample_sequence_before;
	uint64_t sample_sequence_after;
	spf_rssi_pair_t value;
} spf_rssi_observation_t;

typedef struct
{
	pthread_t thread;
	pthread_mutex_t mutex;
	pthread_cond_t credit_cond;
	atomic_bool stop_requested;
	bool mutex_initialized;
	bool credit_cond_initialized;
	bool thread_started;
	atomic_bool ready;
	atomic_bool failed;
	atomic_bool idle;
	atomic_bool force_observation;
	bool bounded;
	uint64_t sample_credit;
	uint64_t capture_requested;
	uint64_t capture_started;
	uint64_t capture_finished;
	uint64_t capture_observed;
	uint32_t interval_samples;
	uint32_t count;
	uint32_t overflow_count;
	spf_gain_observation_v3_t records[SPF_GAIN_SAMPLER_RING_CAPACITY];
	uint32_t rssi_count;
	uint32_t rssi_overflow_count;
	spf_rssi_observation_t rssi_records[SPF_GAIN_SAMPLER_RING_CAPACITY];
} spf_gain_sampler_t;

bool spf_gain_sampler_start(
	spf_gain_sampler_t *sampler,
	uint32_t interval_samples);
void spf_gain_sampler_stop(spf_gain_sampler_t *sampler);

/*
 * Convert a running sampler to bounded operation.  The sampler polls for at
 * most samples more ADC samples and then sleeps without touching IIO until
 * more capture credit is granted.  This is used by request-driven transports
 * after their initial kernel DMA queue has been armed.
 */
void spf_gain_sampler_limit(
	spf_gain_sampler_t *sampler,
	uint64_t samples);

/*
 * Keep sampling continuously until the owner explicitly bounds the sampler
 * again. Buffered transports use this for their whole DMA-buffer lifetime so
 * host-side copy or ring backpressure cannot open a coverage gap behind the
 * kernel queue.
 */
void spf_gain_sampler_unlimit(spf_gain_sampler_t *sampler);

/*
 * Wait until an observation has started without changing the sampler's credit
 * policy. This gives continuously sampled buffered transports the same exact
 * refill fence as request-bounded transports.
 */
bool spf_gain_sampler_wait_started(
	spf_gain_sampler_t *sampler,
	uint32_t timeout_ms);

/*
 * Replace the current credit and wait until the sampler has started a fresh
 * observation.  Request-driven IIO uses this immediately before re-enqueuing
 * a delivered DMA block, ensuring capture begins while gain/RSSI reads are
 * already in flight instead of racing the sampler's scheduler wakeup.
 */
bool spf_gain_sampler_limit_and_wait_started(
	spf_gain_sampler_t *sampler,
	uint64_t samples,
	uint32_t timeout_ms);

/* Finish the active capture fence and wait for its counter-after record. */
bool spf_gain_sampler_finish_capture(
	spf_gain_sampler_t *sampler,
	uint32_t timeout_ms);

/* Grant polling coverage for newly re-enqueued DMA capture work. */
void spf_gain_sampler_add_credit(
	spf_gain_sampler_t *sampler,
	uint64_t samples);

/* True while a bounded sampler is asleep with no capture credit. */
bool spf_gain_sampler_is_idle(const spf_gain_sampler_t *sampler);

/* Consume a refill fence's immediate-observation request, or apply the
 * ordinary counter interval. This keeps refill admission independent of a
 * deliberately sparse HOLD observation cadence. */
bool spf_gain_sampler_observation_due(
	spf_gain_sampler_t *sampler,
	uint32_t current_sample,
	uint32_t last_sampled);

/*
 * Wait for half the estimated samples remaining until the next observation,
 * bounded between 100 us and 50 ms. The wait is interrupted by refill-fence
 * or stop notifications, so its upper bound no longer determines control
 * latency. Halving the remaining interval tolerates sample-clock estimation
 * error without polling the synchronized counter every millisecond.
 */
uint32_t spf_gain_sampler_poll_delay_ns(
	uint32_t interval_samples,
	uint32_t current_sample,
	uint32_t last_sampled,
	uint32_t sample_rate_hz);

#ifdef SPF_GAIN_SAMPLER_TESTING
/* Host-test seam for the private interruptible deadline wait. */
bool spf_gain_sampler_wait_interruptible(
	spf_gain_sampler_t *sampler,
	uint32_t delay_ns);
#endif

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

/*
 * Select the first and last valid RSSI observations whose counter brackets
 * overlap the exact frame sample range. Old observations are retired with the
 * same bounded-ledger rule as gain observations.
 */
bool spf_gain_sampler_collect_rssi(
	spf_gain_sampler_t *sampler,
	uint64_t frame_start,
	uint32_t samples,
	spf_rssi_pair_t *rssi_start,
	spf_rssi_pair_t *rssi_end,
	uint32_t *overflow_count);

/*
 * Fail closed on a frame without gain observations.  Before sequence zero has
 * been exposed, transports may discard a bounded number of timestamp-aligned
 * startup frames while the first local gain read completes.  Once streaming
 * has begun, missing observations are a discontinuity and must be rejected.
 */
spf_gain_frame_decision_t spf_gain_frame_decide(
	uint64_t buffer_sequence,
	uint16_t observation_count,
	uint32_t startup_frames_discarded);

#endif
