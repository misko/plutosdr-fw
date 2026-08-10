#ifndef SPF_IP_CONTROL_REPLAY_H
#define SPF_IP_CONTROL_REPLAY_H

#include "spf_ip_protocol.h"

#include <netinet/in.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define SPF_IP_CONTROL_REPLAY_CAPACITY 16
#define SPF_IP_CONTROL_PEER_CAPACITY 8

typedef enum
{
	SPF_IP_REPLAY_MISS = 0,
	SPF_IP_REPLAY_PENDING,
	SPF_IP_REPLAY_PREPARED,
	SPF_IP_REPLAY_RESPONDED,
	SPF_IP_REPLAY_COLLISION,
	SPF_IP_REPLAY_STALE,
} spf_ip_replay_lookup_t;

typedef enum
{
	SPF_IP_REPLAY_ENTRY_EMPTY = 0,
	SPF_IP_REPLAY_ENTRY_PENDING,
	SPF_IP_REPLAY_ENTRY_PREPARED,
	SPF_IP_REPLAY_ENTRY_RESPONDED,
} spf_ip_replay_entry_state_t;

typedef struct
{
	spf_ip_replay_entry_state_t state;
	struct sockaddr_in peer;
	spf_ip_control_v1_t request;
	spf_ip_control_v1_t response;
	uint64_t age;
} spf_ip_control_replay_entry_t;

typedef struct
{
	bool valid;
	struct sockaddr_in peer;
	uint64_t highest_request_id;
	uint64_t age;
} spf_ip_control_peer_t;

typedef struct
{
	spf_ip_control_replay_entry_t entries[SPF_IP_CONTROL_REPLAY_CAPACITY];
	spf_ip_control_peer_t peers[SPF_IP_CONTROL_PEER_CAPACITY];
	uint64_t next_age;
	uint64_t coalesced_count;
	uint64_t replayed_count;
	uint64_t collision_count;
	uint64_t eviction_count;
	uint64_t stale_count;
} spf_ip_control_replay_t;

void spf_ip_control_replay_init(spf_ip_control_replay_t *replay);
spf_ip_replay_lookup_t spf_ip_control_replay_lookup(
	spf_ip_control_replay_t *replay,
	const struct sockaddr_in *peer,
	const spf_ip_control_v1_t *request,
	int *slot,
	const spf_ip_control_v1_t **response);
bool spf_ip_control_replay_begin(spf_ip_control_replay_t *replay,
	const struct sockaddr_in *peer,
	const spf_ip_control_v1_t *request,
	int *slot);
bool spf_ip_control_replay_prepare(spf_ip_control_replay_t *replay,
	int slot,
	const spf_ip_control_v1_t *response);
bool spf_ip_control_replay_mark_responded(spf_ip_control_replay_t *replay,
	int slot);
bool spf_ip_control_replay_remove(spf_ip_control_replay_t *replay, int slot);
size_t spf_ip_control_replay_count(const spf_ip_control_replay_t *replay);

#endif
