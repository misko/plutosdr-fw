#include "spf_ip_frame_queue.h"

#include <string.h>

bool spf_ip_frame_queue_init(spf_ip_frame_queue_t *queue,
	size_t *storage,
	size_t capacity)
{
	if (queue == NULL || storage == NULL || capacity == 0)
		return false;
	memset(queue, 0, sizeof(*queue));
	queue->storage = storage;
	queue->capacity = capacity;
	return true;
}

bool spf_ip_frame_queue_push(spf_ip_frame_queue_t *queue, size_t value)
{
	if (queue == NULL || queue->storage == NULL ||
		queue->count >= queue->capacity)
		return false;
	queue->storage[queue->tail] = value;
	queue->tail = (queue->tail + 1) % queue->capacity;
	queue->count++;
	return true;
}

bool spf_ip_frame_queue_pop(spf_ip_frame_queue_t *queue, size_t *value)
{
	if (queue == NULL || value == NULL || queue->storage == NULL ||
		queue->count == 0)
		return false;
	*value = queue->storage[queue->head];
	queue->head = (queue->head + 1) % queue->capacity;
	queue->count--;
	return true;
}
