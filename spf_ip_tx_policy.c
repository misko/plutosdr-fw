#include "spf_ip_tx_policy.h"

uint32_t spf_ip_tx_batch_size(size_t payload_bytes_per_datagram,
	uint32_t target_payload_bytes_per_second,
	uint32_t pacing_interval_us)
{
	if (payload_bytes_per_datagram == 0 ||
		target_payload_bytes_per_second == 0 || pacing_interval_us == 0)
		return 0;
	const uint64_t numerator =
		(uint64_t)target_payload_bytes_per_second * pacing_interval_us;
	const uint64_t denominator =
		(uint64_t)payload_bytes_per_datagram * UINT64_C(1000000);
	uint64_t batch = numerator / denominator;
	if (batch == 0)
		batch = 1;
	if (batch > SPF_IP_MAX_SENDMMSG_BATCH)
		batch = SPF_IP_MAX_SENDMMSG_BATCH;
	return (uint32_t)batch;
}
