#ifndef SPF_IP_TX_POLICY_H
#define SPF_IP_TX_POLICY_H

#include <stddef.h>
#include <stdint.h>

#define SPF_IP_DEFAULT_TX_PAYLOAD_BYTES_PER_SECOND UINT32_C(40000000)
#define SPF_IP_LEGACY_TX_PAYLOAD_BYTES_PER_SECOND UINT32_C(11360000)
#define SPF_IP_DEFAULT_PACING_INTERVAL_US UINT32_C(1000)
#define SPF_IP_MAX_SENDMMSG_BATCH UINT32_C(64)
#define SPF_IP_MAX_GSO_PAYLOAD_BYTES UINT32_C(65507)
#define SPF_IP_MAX_GSO_SEGMENTS UINT32_C(64)

uint32_t spf_ip_tx_batch_size(size_t payload_bytes_per_datagram,
	uint32_t target_payload_bytes_per_second,
	uint32_t pacing_interval_us);

uint64_t spf_ip_tx_deadline_ns(uint64_t start_ns,
	uint64_t payload_bytes_sent,
	uint32_t target_payload_bytes_per_second);

uint32_t spf_ip_gso_segments_per_send(size_t datagram_bytes);

#endif
