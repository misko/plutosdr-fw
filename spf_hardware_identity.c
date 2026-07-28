#include "spf_hardware_identity.h"

#include <fcntl.h>
#include <stddef.h>
#include <stdint.h>
#include <sys/mman.h>
#include <unistd.h>

#define SPF_DEVICE_DNA_GPIO_BASE UINT32_C(0x41200000)
#define SPF_DEVICE_DNA_GPIO_RANGE 4096u
#define SPF_DEVICE_DNA_LOW_OFFSET 0u
#define SPF_DEVICE_DNA_HIGH_OFFSET 8u
#define SPF_DEVICE_DNA_HIGH_MASK UINT32_C(0x01ffffff)
#define SPF_DEVICE_DNA_VALID_MASK UINT32_C(0x80000000)

bool spf_read_fpga_device_dna(uint64_t *device_dna)
{
	if (device_dna == NULL)
		return false;
	*device_dna = 0;

	int fd = open("/dev/mem", O_RDONLY | O_SYNC);
	if (fd < 0)
		return false;
	void *mapping = mmap(
		NULL,
		SPF_DEVICE_DNA_GPIO_RANGE,
		PROT_READ,
		MAP_SHARED,
		fd,
		SPF_DEVICE_DNA_GPIO_BASE);
	if (mapping == MAP_FAILED)
	{
		close(fd);
		return false;
	}

	volatile const uint32_t *registers =
		(volatile const uint32_t *)mapping;
	const uint32_t low =
		registers[SPF_DEVICE_DNA_LOW_OFFSET / sizeof(uint32_t)];
	const uint32_t high =
		registers[SPF_DEVICE_DNA_HIGH_OFFSET / sizeof(uint32_t)];
	const uint64_t value =
		(uint64_t)low |
		((uint64_t)(high & SPF_DEVICE_DNA_HIGH_MASK) << 32);
	const bool valid =
		(high & SPF_DEVICE_DNA_VALID_MASK) != 0 &&
		value != 0;

	munmap(mapping, SPF_DEVICE_DNA_GPIO_RANGE);
	close(fd);
	if (!valid)
		return false;
	*device_dna = value;
	return true;
}
