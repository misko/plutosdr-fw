#ifndef SPF_IP_FRAME_QUEUE_H
#define SPF_IP_FRAME_QUEUE_H

#include <stdbool.h>
#include <stddef.h>

typedef struct
{
	size_t *storage;
	size_t capacity;
	size_t head;
	size_t tail;
	size_t count;
} spf_ip_frame_queue_t;

bool spf_ip_frame_queue_init(spf_ip_frame_queue_t *queue,
	size_t *storage,
	size_t capacity);
bool spf_ip_frame_queue_push(spf_ip_frame_queue_t *queue, size_t value);
bool spf_ip_frame_queue_pop(spf_ip_frame_queue_t *queue, size_t *value);

#endif
