#include "spf_ip_control_replay.h"

#include <limits.h>
#include <string.h>

static bool same_peer(const struct sockaddr_in *left,
	const struct sockaddr_in *right)
{
	return left->sin_family == right->sin_family &&
		left->sin_port == right->sin_port &&
		left->sin_addr.s_addr == right->sin_addr.s_addr;
}

static bool valid_slot(int slot)
{
	return slot >= 0 && slot < SPF_IP_CONTROL_REPLAY_CAPACITY;
}

static bool request_id_after(uint64_t candidate, uint64_t reference)
{
	return (int64_t)(candidate - reference) > 0;
}

static int find_peer(const spf_ip_control_replay_t *replay,
	const struct sockaddr_in *peer)
{
	for (int index = 0; index < SPF_IP_CONTROL_PEER_CAPACITY; ++index)
		if (replay->peers[index].valid &&
			same_peer(peer, &replay->peers[index].peer))
			return index;
	return -1;
}

static int select_peer_slot(const spf_ip_control_replay_t *replay)
{
	int selected = 0;
	uint64_t oldest_age = UINT64_MAX;
	for (int index = 0; index < SPF_IP_CONTROL_PEER_CAPACITY; ++index)
	{
		if (!replay->peers[index].valid)
			return index;
		if (replay->peers[index].age < oldest_age)
		{
			oldest_age = replay->peers[index].age;
			selected = index;
		}
	}
	return selected;
}

void spf_ip_control_replay_init(spf_ip_control_replay_t *replay)
{
	if (replay == NULL)
		return;
	memset(replay, 0, sizeof(*replay));
	replay->next_age = 1;
}

spf_ip_replay_lookup_t spf_ip_control_replay_lookup(
	spf_ip_control_replay_t *replay,
	const struct sockaddr_in *peer,
	const spf_ip_control_v1_t *request,
	int *slot,
	const spf_ip_control_v1_t **response)
{
	if (slot != NULL)
		*slot = -1;
	if (response != NULL)
		*response = NULL;
	if (replay == NULL || peer == NULL || request == NULL)
		return SPF_IP_REPLAY_MISS;
	for (int index = 0; index < SPF_IP_CONTROL_REPLAY_CAPACITY; ++index)
	{
		spf_ip_control_replay_entry_t *entry = &replay->entries[index];
		if (entry->state == SPF_IP_REPLAY_ENTRY_EMPTY ||
			!same_peer(peer, &entry->peer) ||
			request->request_id != entry->request.request_id)
			continue;
		if (slot != NULL)
			*slot = index;
		if (memcmp(request, &entry->request, sizeof(*request)) != 0)
		{
			replay->collision_count++;
			return SPF_IP_REPLAY_COLLISION;
		}
		if (entry->state == SPF_IP_REPLAY_ENTRY_PENDING)
		{
			replay->coalesced_count++;
			return SPF_IP_REPLAY_PENDING;
		}
		if (response != NULL)
			*response = &entry->response;
		if (entry->state == SPF_IP_REPLAY_ENTRY_PREPARED)
		{
			replay->coalesced_count++;
			return SPF_IP_REPLAY_PREPARED;
		}
		replay->replayed_count++;
		return SPF_IP_REPLAY_RESPONDED;
	}
	const int peer_slot = find_peer(replay, peer);
	if (peer_slot >= 0 && !request_id_after(request->request_id,
		replay->peers[peer_slot].highest_request_id))
	{
		replay->stale_count++;
		return SPF_IP_REPLAY_STALE;
	}
	return SPF_IP_REPLAY_MISS;
}

bool spf_ip_control_replay_begin(spf_ip_control_replay_t *replay,
	const struct sockaddr_in *peer,
	const spf_ip_control_v1_t *request,
	int *slot)
{
	if (slot != NULL)
		*slot = -1;
	if (replay == NULL || peer == NULL || request == NULL)
		return false;
	int peer_slot = find_peer(replay, peer);
	if (peer_slot >= 0 && !request_id_after(request->request_id,
		replay->peers[peer_slot].highest_request_id))
		return false;
	int selected = -1;
	uint64_t oldest_age = UINT64_MAX;
	for (int index = 0; index < SPF_IP_CONTROL_REPLAY_CAPACITY; ++index)
	{
		const spf_ip_control_replay_entry_t *entry = &replay->entries[index];
		if (entry->state == SPF_IP_REPLAY_ENTRY_EMPTY)
		{
			selected = index;
			break;
		}
		if (entry->state == SPF_IP_REPLAY_ENTRY_RESPONDED &&
			entry->age < oldest_age)
		{
			oldest_age = entry->age;
			selected = index;
		}
	}
	if (selected < 0)
		return false;
	if (peer_slot < 0)
	{
		peer_slot = select_peer_slot(replay);
		memset(&replay->peers[peer_slot], 0,
			sizeof(replay->peers[peer_slot]));
		replay->peers[peer_slot].valid = true;
		replay->peers[peer_slot].peer = *peer;
	}
	replay->peers[peer_slot].highest_request_id = request->request_id;
	replay->peers[peer_slot].age = replay->next_age;
	if (replay->entries[selected].state != SPF_IP_REPLAY_ENTRY_EMPTY)
		replay->eviction_count++;
	spf_ip_control_replay_entry_t *entry = &replay->entries[selected];
	memset(entry, 0, sizeof(*entry));
	entry->state = SPF_IP_REPLAY_ENTRY_PENDING;
	entry->peer = *peer;
	entry->request = *request;
	entry->age = replay->next_age++;
	if (replay->next_age == 0)
		replay->next_age = 1;
	if (slot != NULL)
		*slot = selected;
	return true;
}

bool spf_ip_control_replay_prepare(spf_ip_control_replay_t *replay,
	int slot,
	const spf_ip_control_v1_t *response)
{
	if (replay == NULL || response == NULL || !valid_slot(slot) ||
		replay->entries[slot].state != SPF_IP_REPLAY_ENTRY_PENDING)
		return false;
	replay->entries[slot].response = *response;
	replay->entries[slot].state = SPF_IP_REPLAY_ENTRY_PREPARED;
	return true;
}

bool spf_ip_control_replay_mark_responded(spf_ip_control_replay_t *replay,
	int slot)
{
	if (replay == NULL || !valid_slot(slot) ||
		replay->entries[slot].state != SPF_IP_REPLAY_ENTRY_PREPARED)
		return false;
	replay->entries[slot].state = SPF_IP_REPLAY_ENTRY_RESPONDED;
	return true;
}

bool spf_ip_control_replay_remove(spf_ip_control_replay_t *replay, int slot)
{
	if (replay == NULL || !valid_slot(slot) ||
		replay->entries[slot].state == SPF_IP_REPLAY_ENTRY_EMPTY)
		return false;
	memset(&replay->entries[slot], 0, sizeof(replay->entries[slot]));
	return true;
}

size_t spf_ip_control_replay_count(const spf_ip_control_replay_t *replay)
{
	if (replay == NULL)
		return 0;
	size_t count = 0;
	for (int index = 0; index < SPF_IP_CONTROL_REPLAY_CAPACITY; ++index)
		if (replay->entries[index].state != SPF_IP_REPLAY_ENTRY_EMPTY)
			count++;
	return count;
}
