#include "spf_ip_protocol.h"

#include <string.h>
#include <zlib.h>

static bool fields_zero_for_query(const spf_ip_control_v1_t *message)
{
	return message->flags == 0 &&
		message->protocol_min == 0 && message->protocol_max == 0 &&
		message->features == 0 && message->max_samples_per_channel == 0 &&
		message->max_finite_frames == 0 && message->enabled_scan_mask == 0 &&
		message->samples_per_channel == 0 && message->frame_count == 0 &&
		message->gain_observation_interval_samples == 0 &&
		message->gain_observation_capacity == 0 &&
		message->gain_event_capacity == 0 && message->data_port == 0 &&
		message->max_datagram_bytes == 0 && message->stream_id == 0;
}

void spf_ip_control_init_query(spf_ip_control_v1_t *message,
	uint64_t request_id)
{
	memset(message, 0, sizeof(*message));
	message->magic = SPF_IP_CONTROL_MAGIC;
	message->version = SPF_IP_CONTROL_VERSION;
	message->message_type = SPF_IP_CONTROL_QUERY_CAPABILITIES;
	message->message_bytes = sizeof(*message);
	message->request_id = request_id;
}

void spf_ip_control_init_capabilities(spf_ip_control_v1_t *message,
	uint64_t request_id)
{
	memset(message, 0, sizeof(*message));
	message->magic = SPF_IP_CONTROL_MAGIC;
	message->version = SPF_IP_CONTROL_VERSION;
	message->message_type = SPF_IP_CONTROL_CAPABILITIES;
	message->message_bytes = sizeof(*message);
	message->request_id = request_id;
	message->flags = SPF_IP_CONTROL_FLAG_FINITE_RX |
		SPF_IP_CONTROL_FLAG_IDEMPOTENT_REQUESTS;
	message->protocol_min = 3;
	message->protocol_max = 3;
	message->features = SPF_METADATA_KNOWN_FEATURES;
	message->max_samples_per_channel = SPF_IP_MAX_SAMPLES_PER_CHANNEL;
	message->max_finite_frames = SPF_IP_MAX_FINITE_FRAMES;
}

void spf_ip_control_init_error(spf_ip_control_v1_t *message,
	uint64_t request_id,
	int32_t status)
{
	memset(message, 0, sizeof(*message));
	message->magic = SPF_IP_CONTROL_MAGIC;
	message->version = SPF_IP_CONTROL_VERSION;
	message->message_type = SPF_IP_CONTROL_ERROR;
	message->message_bytes = sizeof(*message);
	message->request_id = request_id;
	message->status = status == 0 ? -1 : status;
}

void spf_ip_control_init_reply(spf_ip_control_v1_t *reply,
	const spf_ip_control_v1_t *request,
	spf_ip_control_type_t reply_type,
	uint64_t stream_id)
{
	*reply = *request;
	reply->message_type = reply_type;
	reply->stream_id = stream_id;
}

bool spf_ip_control_validate(const spf_ip_control_v1_t *message)
{
	if (message == NULL || message->magic != SPF_IP_CONTROL_MAGIC ||
		message->version != SPF_IP_CONTROL_VERSION ||
		message->message_bytes != sizeof(*message) ||
		(message->flags & ~SPF_IP_CONTROL_KNOWN_FLAGS) != 0 ||
		(message->features & ~SPF_METADATA_KNOWN_FEATURES) != 0)
		return false;

	if (message->message_type != SPF_IP_CONTROL_ERROR && message->status != 0)
		return false;
	if (message->message_type == SPF_IP_CONTROL_ERROR)
		return message->status != 0;

	if (message->message_type == SPF_IP_CONTROL_QUERY_CAPABILITIES)
		return fields_zero_for_query(message);

	if (message->message_type == SPF_IP_CONTROL_CAPABILITIES)
	{
		if ((message->flags & SPF_IP_CONTROL_FLAG_FINITE_RX) == 0 ||
			message->protocol_min < 1 ||
			message->protocol_min > message->protocol_max ||
			message->protocol_max > 3 ||
			message->max_samples_per_channel == 0 ||
			message->max_samples_per_channel > SPF_IP_MAX_SAMPLES_PER_CHANNEL ||
			message->max_finite_frames == 0 ||
			message->max_finite_frames > SPF_IP_MAX_FINITE_FRAMES)
			return false;
		return message->enabled_scan_mask == 0 &&
			message->samples_per_channel == 0 && message->frame_count == 0 &&
			message->gain_observation_interval_samples == 0 &&
			message->gain_observation_capacity == 0 &&
			message->gain_event_capacity == 0 && message->data_port == 0 &&
			message->max_datagram_bytes == 0 && message->stream_id == 0;
	}

	if (message->message_type == SPF_IP_CONTROL_START_RX ||
		message->message_type == SPF_IP_CONTROL_STARTED)
	{
		if (message->protocol_min != message->protocol_max ||
			message->protocol_min < 1 || message->protocol_min > 3 ||
			message->max_samples_per_channel != 0 ||
			message->max_finite_frames != 0 ||
			message->enabled_scan_mask != UINT32_C(0x0f) ||
			message->samples_per_channel == 0 ||
			message->samples_per_channel > SPF_IP_MAX_SAMPLES_PER_CHANNEL ||
			message->frame_count == 0 ||
			message->frame_count > SPF_IP_MAX_FINITE_FRAMES ||
			message->data_port == 0 ||
			message->max_datagram_bytes <= sizeof(spf_ip_fragment_v1_t) ||
			message->max_datagram_bytes > SPF_IP_MAX_DATAGRAM_BYTES)
			return false;
		if (message->protocol_min == 3)
		{
			const uint64_t required = SPF_METADATA_FEATURE_GAIN_OBSERVATIONS |
				SPF_METADATA_FEATURE_HARDWARE_SAMPLE_COUNTER;
			if ((message->features & required) != required ||
				message->gain_observation_interval_samples == 0 ||
				message->gain_observation_capacity == 0 ||
				message->gain_observation_capacity > SPF_IP_MAX_GAIN_OBSERVATIONS ||
				message->gain_event_capacity > SPF_IP_MAX_GAIN_EVENTS)
				return false;
		}
		else if (message->gain_observation_interval_samples != 0 ||
			message->gain_observation_capacity != 0 ||
			message->gain_event_capacity != 0)
			return false;
		if (message->message_type == SPF_IP_CONTROL_START_RX)
			return message->stream_id == 0;
		return message->stream_id != 0;
	}

	if (message->message_type == SPF_IP_CONTROL_STOP_RX ||
		message->message_type == SPF_IP_CONTROL_STOPPED)
	{
		if (message->stream_id == 0)
			return false;
		spf_ip_control_v1_t copy = *message;
		copy.stream_id = 0;
		return fields_zero_for_query(&copy);
	}

	return false;
}

bool spf_ip_fragment_validate(const spf_ip_fragment_v1_t *header,
	size_t datagram_bytes)
{
	if (header == NULL || header->magic != SPF_IP_FRAGMENT_MAGIC ||
		header->version != SPF_IP_FRAGMENT_VERSION ||
		header->header_bytes != sizeof(*header) ||
		(header->flags & ~SPF_IP_FRAGMENT_KNOWN_FLAGS) != 0 ||
		header->frame_bytes == 0 || header->frame_bytes > SPF_IP_MAX_FRAME_BYTES ||
		header->fragment_count == 0 ||
		header->fragment_count > SPF_IP_MAX_FRAGMENT_COUNT ||
		header->fragment_index >= header->fragment_count ||
		header->fragment_bytes == 0 ||
		header->fragment_offset > header->frame_bytes ||
		header->fragment_bytes > header->frame_bytes - header->fragment_offset ||
		datagram_bytes != sizeof(*header) + header->fragment_bytes ||
		datagram_bytes > SPF_IP_MAX_DATAGRAM_BYTES)
		return false;
	if (((header->flags & SPF_IP_FRAGMENT_FLAG_FIRST) != 0) !=
		(header->fragment_index == 0))
		return false;
	if (((header->flags & SPF_IP_FRAGMENT_FLAG_LAST) != 0) !=
		(header->fragment_index == header->fragment_count - 1))
		return false;
	return true;
}

uint32_t spf_ip_crc32(const void *data, size_t bytes)
{
	return (uint32_t)crc32(0, data, bytes);
}

size_t spf_ip_fragment_count(size_t frame_bytes, size_t max_datagram_bytes)
{
	if (frame_bytes == 0 || frame_bytes > SPF_IP_MAX_FRAME_BYTES ||
		max_datagram_bytes <= sizeof(spf_ip_fragment_v1_t) ||
		max_datagram_bytes > SPF_IP_MAX_DATAGRAM_BYTES)
		return 0;
	const size_t payload_bytes =
		max_datagram_bytes - sizeof(spf_ip_fragment_v1_t);
	const size_t count = (frame_bytes + payload_bytes - 1) / payload_bytes;
	return count <= SPF_IP_MAX_FRAGMENT_COUNT ? count : 0;
}

bool spf_ip_fragment_plan(
	spf_ip_fragment_v1_t *headers,
	size_t header_capacity,
	const void *frame,
	size_t frame_bytes,
	uint64_t stream_id,
	uint64_t frame_sequence,
	size_t max_datagram_bytes)
{
	const size_t count = spf_ip_fragment_count(
		frame_bytes, max_datagram_bytes);
	if (headers == NULL || frame == NULL || stream_id == 0 || count == 0 ||
		header_capacity < count)
		return false;
	const size_t payload_capacity =
		max_datagram_bytes - sizeof(spf_ip_fragment_v1_t);
	const uint32_t frame_crc32 = spf_ip_crc32(frame, frame_bytes);
	for (size_t index = 0; index < count; ++index)
	{
		const size_t offset = index * payload_capacity;
		const size_t remaining = frame_bytes - offset;
		const size_t fragment_bytes = remaining < payload_capacity
			? remaining : payload_capacity;
		spf_ip_fragment_v1_t *header = &headers[index];
		memset(header, 0, sizeof(*header));
		header->magic = SPF_IP_FRAGMENT_MAGIC;
		header->version = SPF_IP_FRAGMENT_VERSION;
		header->header_bytes = sizeof(*header);
		if (index == 0)
			header->flags |= SPF_IP_FRAGMENT_FLAG_FIRST;
		if (index == count - 1)
			header->flags |= SPF_IP_FRAGMENT_FLAG_LAST;
		header->stream_id = stream_id;
		header->frame_sequence = frame_sequence;
		header->frame_bytes = (uint32_t)frame_bytes;
		header->frame_crc32 = frame_crc32;
		header->fragment_index = (uint32_t)index;
		header->fragment_count = (uint32_t)count;
		header->fragment_offset = (uint32_t)offset;
		header->fragment_bytes = (uint32_t)fragment_bytes;
		if (!spf_ip_fragment_validate(
			header, sizeof(*header) + fragment_bytes))
			return false;
	}
	return true;
}
