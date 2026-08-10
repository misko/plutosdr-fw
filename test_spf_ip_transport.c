#include "spf_ip_frame_queue.h"
#include "spf_ip_tx_policy.h"

#include <assert.h>

static void test_finite_frame_queue(void)
{
	spf_ip_frame_queue_t queue;
	size_t storage[4];
	assert(spf_ip_frame_queue_init(&queue, storage, 4));
	for (size_t index = 0; index < 4; ++index)
		assert(spf_ip_frame_queue_push(&queue, index));
	assert(!spf_ip_frame_queue_push(&queue, 4));
	for (size_t index = 0; index < 4; ++index)
	{
		size_t value = 99;
		assert(spf_ip_frame_queue_pop(&queue, &value));
		assert(value == index);
	}
	size_t value = 0;
	assert(!spf_ip_frame_queue_pop(&queue, &value));

	/* Exercise wraparound independently from the worker thread. */
	assert(spf_ip_frame_queue_push(&queue, 10));
	assert(spf_ip_frame_queue_push(&queue, 11));
	assert(spf_ip_frame_queue_pop(&queue, &value) && value == 10);
	assert(spf_ip_frame_queue_push(&queue, 12));
	assert(spf_ip_frame_queue_pop(&queue, &value) && value == 11);
	assert(spf_ip_frame_queue_pop(&queue, &value) && value == 12);
}

static void test_rate_to_batch_policy(void)
{
	/* 40 MB/s at an MTU-safe 1420-byte payload produces 28 packets/ms. */
	assert(spf_ip_tx_batch_size(1420, 40000000, 1000) == 28);
	assert(spf_ip_tx_batch_size(1420, 24000000, 1000) == 16);
	assert(spf_ip_tx_batch_size(1420, 1, 1000) == 1);
	assert(spf_ip_tx_batch_size(1420, UINT32_MAX, 1000) == 64);
	assert(spf_ip_tx_batch_size(0, 40000000, 1000) == 0);
}

static void test_absolute_rate_deadline_policy(void)
{
	const uint64_t start = UINT64_C(123000000000);
	assert(spf_ip_tx_deadline_ns(start, 40000000, 40000000) ==
		start + UINT64_C(1000000000));
	assert(spf_ip_tx_deadline_ns(start, 20000000, 40000000) ==
		start + UINT64_C(500000000));
	assert(spf_ip_tx_deadline_ns(start, 80000001, 40000000) ==
		start + UINT64_C(2000000025));
	assert(spf_ip_tx_deadline_ns(start, 1, 0) == 0);
}

static void test_udp_gso_group_policy(void)
{
	assert(spf_ip_gso_segments_per_send(1472) == 44);
	assert(spf_ip_gso_segments_per_send(1024) == 63);
	assert(spf_ip_gso_segments_per_send(256) == 64);
	assert(spf_ip_gso_segments_per_send(65507) == 1);
	assert(spf_ip_gso_segments_per_send(0) == 0);
	assert(spf_ip_gso_segments_per_send(65508) == 0);
}

int main(void)
{
	test_finite_frame_queue();
	test_rate_to_batch_policy();
	test_absolute_rate_deadline_policy();
	test_udp_gso_group_policy();
	return 0;
}
