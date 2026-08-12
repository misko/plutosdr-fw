#define _GNU_SOURCE

#include "spf_gain_sampler.h"

#include "spf_gain_read.h"

#include <iio.h>
#include <inttypes.h>
#include <sched.h>
#include <stdio.h>
#include <string.h>
#include <time.h>

static void consume_credit_locked(spf_gain_sampler_t *sampler)
{
	if (!sampler->bounded)
		return;
	if (sampler->sample_credit <= sampler->interval_samples)
		sampler->sample_credit = 0;
	else
		sampler->sample_credit -= sampler->interval_samples;
}

static uint64_t extend_counter_near(uint64_t reference, uint32_t low)
{
	uint64_t candidate = (reference & UINT64_C(0xFFFFFFFF00000000)) | low;
	if (candidate < reference && reference - candidate > UINT64_C(0x80000000))
		candidate += UINT64_C(0x100000000);
	else if (candidate > reference &&
		candidate - reference > UINT64_C(0x80000000) &&
		candidate >= UINT64_C(0x100000000))
		candidate -= UINT64_C(0x100000000);
	return candidate;
}

static bool read_counter(struct iio_device *rx, uint32_t *value)
{
	return iio_device_reg_read(rx, SPF_ADC_SAMPLE_COUNTER_LOW_REG, value) == 0;
}

static void append_records(
	spf_gain_sampler_t *sampler,
	const spf_gain_observation_v3_t *gain_record,
	const spf_rssi_observation_t *rssi_record)
{
	pthread_mutex_lock(&sampler->mutex);
	if (sampler->count == SPF_GAIN_SAMPLER_RING_CAPACITY)
	{
		memmove(
			&sampler->records[0],
			&sampler->records[1],
			(SPF_GAIN_SAMPLER_RING_CAPACITY - 1) * sizeof(sampler->records[0]));
		sampler->count--;
		sampler->overflow_count++;
	}
	sampler->records[sampler->count++] = *gain_record;
	if (sampler->rssi_count == SPF_GAIN_SAMPLER_RING_CAPACITY)
	{
		memmove(
			&sampler->rssi_records[0],
			&sampler->rssi_records[1],
			(SPF_GAIN_SAMPLER_RING_CAPACITY - 1) *
				sizeof(sampler->rssi_records[0]));
		sampler->rssi_count--;
		sampler->rssi_overflow_count++;
	}
	sampler->rssi_records[sampler->rssi_count++] = *rssi_record;
	consume_credit_locked(sampler);
	pthread_mutex_unlock(&sampler->mutex);
}

static void *sampler_thread(void *opaque)
{
	spf_gain_sampler_t *sampler = opaque;
	/* Do not inherit the USB worker's real-time priority or CPU-0 affinity. */
	pthread_setname_np(pthread_self(), "SPF_GAIN_SAMPLE");
	struct sched_param normal_priority = {.sched_priority = 0};
	(void)pthread_setschedparam(pthread_self(), SCHED_OTHER, &normal_priority);
	cpu_set_t affinity;
	CPU_ZERO(&affinity);
	CPU_SET(1, &affinity);
	(void)pthread_setaffinity_np(pthread_self(), sizeof(affinity), &affinity);
	struct iio_context *context = iio_create_local_context();
	if (!context)
	{
		atomic_store(&sampler->failed, true);
		return NULL;
	}
	struct iio_device *rx = iio_context_find_device(context, "cf-ad9361-lpc");
	struct iio_device *phy = iio_context_find_device(context, "ad9361-phy");
	spf_gain_table_t table;
	memset(&table, 0, sizeof(table));
	if (!rx || !phy || !spf_gain_table_load(phy, &table))
	{
		atomic_store(&sampler->failed, true);
		iio_context_destroy(context);
		return NULL;
	}

	uint32_t first = 0;
	uint32_t second = 0;
	struct timespec settle = {.tv_sec = 0, .tv_nsec = 1000000};
	if (!read_counter(rx, &first))
	{
		atomic_store(&sampler->failed, true);
		iio_context_destroy(context);
		return NULL;
	}
	nanosleep(&settle, NULL);
	if (!read_counter(rx, &second) || second == first)
	{
		/* The required synchronized FPGA counter is absent or not advancing. */
		atomic_store(&sampler->failed, true);
		iio_context_destroy(context);
		return NULL;
	}
	uint32_t last_sampled = second - sampler->interval_samples;
	const struct timespec poll_delay = {.tv_sec = 0, .tv_nsec = 100000};

	while (!atomic_load_explicit(&sampler->stop_requested, memory_order_relaxed))
	{
		pthread_mutex_lock(&sampler->mutex);
		while (sampler->bounded && sampler->sample_credit == 0 &&
			!atomic_load_explicit(
				&sampler->stop_requested, memory_order_relaxed))
		{
			atomic_store_explicit(&sampler->idle, true, memory_order_release);
			pthread_cond_wait(&sampler->credit_cond, &sampler->mutex);
		}
		atomic_store_explicit(&sampler->idle, false, memory_order_release);
		const bool stop = atomic_load_explicit(
			&sampler->stop_requested, memory_order_relaxed);
		pthread_mutex_unlock(&sampler->mutex);
		if (stop)
			break;

		uint32_t current = 0;
		if (!read_counter(rx, &current))
		{
			atomic_store(&sampler->failed, true);
			break;
		}
		if ((uint32_t)(current - last_sampled) < sampler->interval_samples)
		{
			nanosleep(&poll_delay, NULL);
			continue;
		}

		spf_gain_observation_v3_t record;
		memset(&record, 0, sizeof(record));
		uint32_t before = 0;
		uint32_t after = 0;
		const bool before_valid = read_counter(rx, &before);
		pthread_mutex_lock(&sampler->mutex);
		sampler->observations_started++;
		pthread_cond_broadcast(&sampler->credit_cond);
		pthread_mutex_unlock(&sampler->mutex);
		spf_gain_pair_t gain = spf_gain_read_db_pair(phy, &table);
		spf_rssi_pair_t rssi = spf_rssi_read_pair(phy);
		const bool after_valid = read_counter(rx, &after);
		record.read_duration_ns = gain.duration_ns;
		record.rx1_gain_index = gain.valid ? gain.rx1 : SPF_GAIN_INDEX_INVALID;
		record.rx2_gain_index = gain.valid ? gain.rx2 : SPF_GAIN_INDEX_INVALID;
		record.rx1_gain_db = gain.valid ? gain.rx1_db : SPF_GAIN_DB_INVALID;
		record.rx2_gain_db = gain.valid ? gain.rx2_db : SPF_GAIN_DB_INVALID;
		if (gain.valid)
			record.flags |= SPF_GAIN_OBSERVATION_VALID;
		if (before_valid && after_valid)
		{
			record.sample_sequence_before = before;
			record.sample_sequence_after = after;
			record.flags |= SPF_GAIN_OBSERVATION_SAMPLE_INTERVAL_VALID;
		}
		spf_rssi_observation_t rssi_record = {
			.sample_sequence_before = before,
			.sample_sequence_after = after,
			.value = rssi,
		};
		if (!before_valid || !after_valid)
			rssi_record.value.valid = false;
		append_records(sampler, &record, &rssi_record);
		atomic_store(&sampler->ready, true);
		last_sampled = before_valid ? before : current;
	}

	iio_context_destroy(context);
	return NULL;
}

bool spf_gain_sampler_collect_rssi(
	spf_gain_sampler_t *sampler,
	uint64_t frame_start,
	uint32_t samples,
	spf_rssi_pair_t *rssi_start,
	spf_rssi_pair_t *rssi_end,
	uint32_t *overflow_count)
{
	if (!sampler || !rssi_start || !rssi_end || !overflow_count)
		return false;
	const uint64_t frame_end = frame_start + samples;
	uint32_t retained = 0;
	bool found = false;
	memset(rssi_start, 0, sizeof(*rssi_start));
	memset(rssi_end, 0, sizeof(*rssi_end));
	rssi_start->rx1_qdb = SPF_RSSI_QDB_INVALID;
	rssi_start->rx2_qdb = SPF_RSSI_QDB_INVALID;
	*rssi_end = *rssi_start;

	pthread_mutex_lock(&sampler->mutex);
	for (uint32_t index = 0; index < sampler->rssi_count; ++index)
	{
		spf_rssi_observation_t record = sampler->rssi_records[index];
		record.sample_sequence_before = extend_counter_near(
			frame_start, (uint32_t)record.sample_sequence_before);
		record.sample_sequence_after = extend_counter_near(
			frame_start, (uint32_t)record.sample_sequence_after);
		const bool overlaps = record.value.valid &&
			record.sample_sequence_after >= frame_start &&
			record.sample_sequence_before < frame_end;
		if (overlaps)
		{
			if (!found)
				*rssi_start = record.value;
			*rssi_end = record.value;
			found = true;
		}
		if (record.sample_sequence_after >= frame_end)
			sampler->rssi_records[retained++] = sampler->rssi_records[index];
	}
	sampler->rssi_count = retained;
	*overflow_count = sampler->rssi_overflow_count;
	sampler->rssi_overflow_count = 0;
	pthread_mutex_unlock(&sampler->mutex);
	return found;
}

bool spf_gain_sampler_start(
	spf_gain_sampler_t *sampler,
	uint32_t interval_samples)
{
	memset(sampler, 0, sizeof(*sampler));
	sampler->interval_samples = interval_samples;
	atomic_init(&sampler->stop_requested, false);
	atomic_init(&sampler->ready, false);
	atomic_init(&sampler->failed, false);
	atomic_init(&sampler->idle, false);
	if (pthread_mutex_init(&sampler->mutex, NULL) != 0)
		return false;
	sampler->mutex_initialized = true;
	if (pthread_cond_init(&sampler->credit_cond, NULL) != 0)
	{
		pthread_mutex_destroy(&sampler->mutex);
		sampler->mutex_initialized = false;
		return false;
	}
	sampler->credit_cond_initialized = true;
	if (pthread_create(&sampler->thread, NULL, sampler_thread, sampler) != 0)
	{
		pthread_cond_destroy(&sampler->credit_cond);
		sampler->credit_cond_initialized = false;
		pthread_mutex_destroy(&sampler->mutex);
		sampler->mutex_initialized = false;
		return false;
	}
	sampler->thread_started = true;

	/* Bound startup: the counter must prove it advances within 100 ms. */
	const struct timespec wait = {.tv_sec = 0, .tv_nsec = 1000000};
	for (unsigned int attempt = 0; attempt < 100; ++attempt)
	{
		if (atomic_load(&sampler->ready))
			return true;
		if (atomic_load(&sampler->failed))
			break;
		nanosleep(&wait, NULL);
	}
	spf_gain_sampler_stop(sampler);
	return false;
}

void spf_gain_sampler_stop(spf_gain_sampler_t *sampler)
{
	if (sampler->thread_started)
	{
		atomic_store_explicit(
			&sampler->stop_requested, true, memory_order_relaxed);
		pthread_mutex_lock(&sampler->mutex);
		pthread_cond_broadcast(&sampler->credit_cond);
		pthread_mutex_unlock(&sampler->mutex);
		pthread_join(sampler->thread, NULL);
		sampler->thread_started = false;
	}
	if (sampler->credit_cond_initialized)
	{
		pthread_cond_destroy(&sampler->credit_cond);
		sampler->credit_cond_initialized = false;
	}
	if (sampler->mutex_initialized)
	{
		pthread_mutex_destroy(&sampler->mutex);
		sampler->mutex_initialized = false;
	}
}

void spf_gain_sampler_limit(spf_gain_sampler_t *sampler, uint64_t samples)
{
	if (!sampler || !sampler->mutex_initialized)
		return;
	pthread_mutex_lock(&sampler->mutex);
	sampler->bounded = true;
	sampler->sample_credit = samples;
	pthread_cond_broadcast(&sampler->credit_cond);
	pthread_mutex_unlock(&sampler->mutex);
}

bool spf_gain_sampler_limit_and_wait_started(
	spf_gain_sampler_t *sampler,
	uint64_t samples,
	uint32_t timeout_ms)
{
	if (!sampler || !sampler->mutex_initialized || samples == 0 ||
		timeout_ms == 0)
		return false;
	struct timespec deadline;
	if (clock_gettime(CLOCK_REALTIME, &deadline) != 0)
		return false;
	deadline.tv_sec += timeout_ms / 1000U;
	deadline.tv_nsec += (long)(timeout_ms % 1000U) * 1000000L;
	if (deadline.tv_nsec >= 1000000000L)
	{
		deadline.tv_sec++;
		deadline.tv_nsec -= 1000000000L;
	}

	pthread_mutex_lock(&sampler->mutex);
	const uint64_t started_before = sampler->observations_started;
	sampler->bounded = true;
	sampler->sample_credit = samples;
	pthread_cond_broadcast(&sampler->credit_cond);
	int wait_result = 0;
	while (sampler->observations_started == started_before &&
		!atomic_load_explicit(&sampler->failed, memory_order_relaxed) &&
		!atomic_load_explicit(
			&sampler->stop_requested, memory_order_relaxed))
	{
		wait_result = pthread_cond_timedwait(
			&sampler->credit_cond, &sampler->mutex, &deadline);
		if (wait_result != 0)
			break;
	}
	const bool started = sampler->observations_started != started_before;
	pthread_mutex_unlock(&sampler->mutex);
	return started;
}

void spf_gain_sampler_add_credit(spf_gain_sampler_t *sampler, uint64_t samples)
{
	if (!sampler || !sampler->mutex_initialized || samples == 0)
		return;
	pthread_mutex_lock(&sampler->mutex);
	if (UINT64_MAX - sampler->sample_credit < samples)
		sampler->sample_credit = UINT64_MAX;
	else
		sampler->sample_credit += samples;
	pthread_cond_broadcast(&sampler->credit_cond);
	pthread_mutex_unlock(&sampler->mutex);
}

bool spf_gain_sampler_is_idle(const spf_gain_sampler_t *sampler)
{
	return sampler && atomic_load_explicit(
		&sampler->idle, memory_order_acquire);
}

uint16_t spf_gain_sampler_collect(
	spf_gain_sampler_t *sampler,
	uint64_t frame_start,
	uint32_t samples,
	spf_gain_observation_v3_t *destination,
	uint16_t capacity,
	uint32_t *overflow_count)
{
	const uint64_t frame_end = frame_start + samples;
	uint16_t copied = 0;
	uint32_t retained = 0;
	pthread_mutex_lock(&sampler->mutex);
	const uint32_t queued_before = sampler->count;
	uint32_t interval_records = 0;
	uint64_t earliest_before = UINT64_MAX;
	uint64_t latest_after = 0;
	for (uint32_t index = 0; index < sampler->count; ++index)
	{
		spf_gain_observation_v3_t record = sampler->records[index];
		if (record.flags & SPF_GAIN_OBSERVATION_SAMPLE_INTERVAL_VALID)
		{
			record.sample_sequence_before = extend_counter_near(
				frame_start, (uint32_t)record.sample_sequence_before);
			record.sample_sequence_after = extend_counter_near(
				frame_start, (uint32_t)record.sample_sequence_after);
			interval_records++;
			if (record.sample_sequence_before < earliest_before)
				earliest_before = record.sample_sequence_before;
			if (record.sample_sequence_after > latest_after)
				latest_after = record.sample_sequence_after;
		}
		const bool overlaps =
			(record.flags & SPF_GAIN_OBSERVATION_SAMPLE_INTERVAL_VALID) &&
			record.sample_sequence_after >= frame_start &&
			record.sample_sequence_before < frame_end;
		if (overlaps)
		{
			if (copied < capacity)
				destination[copied++] = record;
			else
				sampler->overflow_count++;
		}
		if (!(record.flags & SPF_GAIN_OBSERVATION_SAMPLE_INTERVAL_VALID) ||
			record.sample_sequence_after >= frame_end)
		{
			sampler->records[retained++] = sampler->records[index];
		}
	}
	sampler->count = retained;
	if (copied == 0)
	{
		fprintf(stderr,
			"Protocol-v3 gain sampler found no overlap: "
			"frame=[%" PRIu64 ",%" PRIu64 ") queued=%u "
			"interval_records=%u earliest_before=%" PRIu64 " "
			"latest_after=%" PRIu64 " retained=%u failed=%u\n",
			frame_start,
			frame_end,
			queued_before,
			interval_records,
			earliest_before,
			latest_after,
			retained,
			atomic_load(&sampler->failed) ? 1U : 0U);
	}
	*overflow_count = sampler->overflow_count;
	sampler->overflow_count = 0;
	pthread_mutex_unlock(&sampler->mutex);
	return copied;
}

spf_gain_frame_decision_t spf_gain_frame_decide(
	uint64_t buffer_sequence,
	uint16_t observation_count,
	uint32_t startup_frames_discarded)
{
	if (observation_count != 0)
		return SPF_GAIN_FRAME_ACCEPT;
	if (buffer_sequence == 0 &&
		startup_frames_discarded < SPF_GAIN_STARTUP_DISCARD_LIMIT)
		return SPF_GAIN_FRAME_DISCARD_STARTUP;
	return SPF_GAIN_FRAME_REJECT;
}
