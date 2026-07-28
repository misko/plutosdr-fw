#ifndef __SPF_HARDWARE_IDENTITY_H__
#define __SPF_HARDWARE_IDENTITY_H__

#include <stdbool.h>
#include <stdint.h>

bool spf_read_fpga_device_dna(uint64_t *device_dna);

#endif
