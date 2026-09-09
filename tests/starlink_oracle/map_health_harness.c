/* Execute the actual driver functions against explicit kernel/MMIO mocks.
 * All MMIO accesses must hold the same modeled mutex used by the IRQ path.
 * Snapshot progress is modeled; the independent RTL test verifies mapping.
 */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdarg.h>
#include <string.h>
#include <errno.h>
#include <sys/types.h>

typedef uint16_t u16;
typedef uint32_t u32;
typedef uint64_t u64;
typedef int irqreturn_t;
#define __iomem
#define BIT(n) (UINT32_C(1) << (n))
#define GENMASK(high, low) ((UINT32_MAX >> (31 - (high))) & (UINT32_MAX << (low)))
#define U32_MAX UINT32_MAX
#define ARRAY_SIZE(array) (sizeof(array) / sizeof((array)[0]))
#define lower_32_bits(value) ((u32)(value))
#define upper_32_bits(value) ((u32)((u64)(value) >> 32))
#define IRQ_NONE 0
#define IRQ_HANDLED 1
struct mutex { bool held; };
struct adi_starlink_pss_map;
struct map_snapshot;
struct iio_dev { struct adi_starlink_pss_map *state; };
struct device { struct iio_dev *indio; };
struct device_attribute { unsigned int unused; };
static struct adi_starlink_pss_map *active;
static struct iio_dev *dev_to_iio_dev(struct device *dev) { return dev->indio; }
static void *iio_priv(struct iio_dev *dev) { return dev->state; }
static void mutex_lock(struct mutex *lock) { assert(!lock->held); lock->held = true; }
static void mutex_unlock(struct mutex *lock) { assert(lock->held); lock->held = false; }
static int sysfs_emit_at(char *buf, int offset, const char *fmt, ...)
{
    va_list args;
    int result;
    assert(offset >= 0 && offset < 4096);
    va_start(args, fmt);
    result = vsnprintf(buf + offset, 4096 - offset, fmt, args);
    va_end(args);
    assert(result > 0 && result < 4096 - offset);
    return result;
}
#define sysfs_emit(buf, fmt, ...) sysfs_emit_at(buf, 0, fmt, ##__VA_ARGS__)
static u32 ioread32(const void *address);
static void iowrite32(u32 value, void *address);
static void poll_step(void);
static unsigned int poll_steps;
#define readl_poll_timeout(address, value, condition, delay, timeout) ({ \
    int mock_result = -ETIMEDOUT; \
    unsigned int mock_step; \
    assert((delay) == 1 && (timeout) == 10000); \
    for (mock_step = 0; mock_step < 8; mock_step++) { \
        poll_step(); \
        (value) = ioread32(address); \
        if (condition) { mock_result = 0; break; } \
    } \
    mock_result; \
})

/* The tested IRQ scenario has no ready maps, so these must never run. */
static void map_stop_on_fault(struct adi_starlink_pss_map *st, u32 fault)
{ assert(!"IRQ must not stop acquisition in no-ready-map test"); }
static int map_copy_locked(struct adi_starlink_pss_map *st,
    const struct map_snapshot *snapshot, unsigned int bank)
{ assert(!"unexpected map copy"); return -EIO; }
static int map_push_chunks_locked(struct adi_starlink_pss_map *st,
    const struct map_snapshot *snapshot, unsigned int bank)
{ assert(!"unexpected chunk push"); return -EIO; }
static int map_release_locked(struct adi_starlink_pss_map *st, unsigned int bank)
{ assert(!"unexpected bank release"); return -EIO; }

#include "map_health_actual.inc"

static u32 mmio[64], live[64], reads[64];
static unsigned int snapshot_writes, other_writes, lock_reads;
enum fault_mode { NONE, TIMEOUT, GENERATION_AFTER_POLL, GENERATION_DURING_PAYLOAD,
    GENERATION_AFTER_PAYLOAD, OVERRUN_DURING_PAYLOAD, OVERRUN_AFTER_PAYLOAD,
    PENDING_AFTER_PAYLOAD, DDC_ROLLOVER_ONCE, DDC_ROLLOVER_FOREVER };
static enum fault_mode fault;
static u32 rollover_reg;
static const u16 fault_addresses[14] = {
    0x5c, 0x60, 0x68, 0x6c, 0x70, 0x74, 0x78,
    0x88, 0x8c, 0x94, 0x98, 0x9c, 0xa0, 0xa4,
};

static u32 ioread32(const void *address)
{
    size_t reg = (const unsigned char *)address - (const unsigned char *)mmio;
    assert(reg < sizeof(mmio) && reg % 4 == 0);
    assert(active->lock.held);
    lock_reads++;
    reads[reg / 4]++;
    if (reg == MAP_REG_SNAPSHOT_GENERATION && reads[reg / 4] == 3 &&
        fault == GENERATION_AFTER_POLL)
        mmio[reg / 4]++;
    if (reg == MAP_REG_SNAPSHOT_START_1_HI) {
        if (fault == GENERATION_DURING_PAYLOAD)
            mmio[MAP_REG_SNAPSHOT_GENERATION / 4]++;
        if (fault == OVERRUN_DURING_PAYLOAD)
            mmio[MAP_REG_SNAPSHOT_REQUEST_OVERRUN / 4]++;
    }
    if (reg == MAP_REG_STATUS && reads[reg / 4] == 2) {
        if (fault == GENERATION_AFTER_PAYLOAD)
            mmio[MAP_REG_SNAPSHOT_GENERATION / 4]++;
        if (fault == OVERRUN_AFTER_PAYLOAD)
            mmio[MAP_REG_SNAPSHOT_REQUEST_OVERRUN / 4]++;
        if (fault == PENDING_AFTER_PAYLOAD)
            mmio[MAP_REG_SNAPSHOT_STATUS / 4] = 3;
    }
    if (reg == rollover_reg && ((fault == DDC_ROLLOVER_ONCE &&
        reads[reg / 4] == 2) || fault == DDC_ROLLOVER_FOREVER)) {
        mmio[reg / 4]++;
        mmio[(reg - 16) / 4] = 7;
    }
    if (reg == MAP_REG_STATUS) {
        u32 snapshot_status = mmio[MAP_REG_SNAPSHOT_STATUS / 4];
        u32 status = mmio[reg / 4] & ~0x190U;

        status |= (snapshot_status & 1U) << 8;
        status |= (snapshot_status & 2U) << 6;
        if ((status & 1U) && (status & 12U))
            status |= BIT(4);
        return status;
    }
    return mmio[reg / 4];
}

static void iowrite32(u32 value, void *address)
{
    size_t reg = (unsigned char *)address - (unsigned char *)mmio;
    assert(active->lock.held);
    assert(reg < sizeof(mmio) && reg % 4 == 0);
    if (reg == MAP_REG_SNAPSHOT_CONTROL) {
        assert(value == 1);
        snapshot_writes++;
        mmio[MAP_REG_SNAPSHOT_STATUS / 4] |= 2;
    } else {
        other_writes++;
        assert(!"health must not change acquisition, IRQ, bank or faults");
    }
}

static void poll_step(void)
{
    unsigned int reg;
    poll_steps++;
    if (fault == TIMEOUT)
        return;
    if (!(mmio[MAP_REG_SNAPSHOT_STATUS / 4] & 2))
        return;
    for (reg = 0x3c; reg <= 0x78; reg += 4)
        mmio[reg / 4] = live[reg / 4];
    for (reg = 0x88; reg <= 0xac; reg += 4)
        mmio[reg / 4] = live[reg / 4];
    mmio[MAP_REG_SNAPSHOT_GENERATION / 4]++;
    mmio[MAP_REG_SNAPSHOT_STATUS / 4] = 1;
}

static void reset_mock(struct adi_starlink_pss_map *st, u32 version)
{
    memset(st, 0, sizeof(*st));
    memset(mmio, 0, sizeof(mmio));
    memset(live, 0, sizeof(live));
    memset(reads, 0, sizeof(reads));
    active = st;
    st->regs = mmio;
    st->version = version;
    st->input_rate_msps = version == 0x10002 ? 30 :
        (version == 0x10003 || version == 0x10004 ? 60 : 15);
    mmio[MAP_REG_ID / 4] = MAP_IDENTIFICATION;
    mmio[MAP_REG_VERSION / 4] = st->version;
    mmio[MAP_REG_INPUT_RATE_MSPS / 4] = st->input_rate_msps;
    mmio[MAP_REG_STATUS / 4] = 1;
    mmio[MAP_REG_SNAPSHOT_GENERATION / 4] = 7;
    mmio[MAP_REG_SNAPSHOT_STATUS / 4] = 1;
    snapshot_writes = other_writes = lock_reads = poll_steps = 0;
    fault = NONE;
    rollover_reg = MAP_REG_DDC_ACCEPTED_HI;
}

static int receipt(struct adi_starlink_pss_map *st, u32 words[MAP_HEALTH_WORDS],
    char output[4096])
{
    struct iio_dev indio = { .state = st };
    struct device dev = { .indio = &indio };
    struct adi_starlink_pss_map before = *st;
    char *next;
    unsigned int index, used;
    ssize_t result;
    memset(output, '!', 4096);
    result = map_acquisition_health_show(&dev, NULL, output);
    assert(!memcmp(&before, st, sizeof(before)));
    assert(!st->lock.held && other_writes == 0);
    if (result < 0) {
        assert(output[0] == '!'); /* No partial or stale successful receipt. */
        return result;
    }
    assert(result == 424 && output[result - 1] == '\n' && output[result] == 0);
    assert(!strncmp(output, "PSMH 1 46", 9));
    next = output + 9;
    for (index = 0; index < MAP_HEALTH_WORDS; index++) {
        assert(next[0] == ' ');
        assert(sscanf(next, " %8x%n", &words[index], &used) == 1 && used == 9);
        next += used;
    }
    assert(!strcmp(next, "\n"));
    return 0;
}

int main(void)
{
    struct adi_starlink_pss_map st;
    struct map_snapshot snapshot;
    struct iio_dev indio = { .state = &st };
    u32 words[MAP_HEALTH_WORDS], version, bit, index;
    char output[4096];
    unsigned int fault_receipts = 0, failures = 0, rollovers = 0;
    const enum fault_mode failure_modes[] = {
        TIMEOUT, GENERATION_AFTER_POLL, GENERATION_DURING_PAYLOAD,
        GENERATION_AFTER_PAYLOAD, OVERRUN_DURING_PAYLOAD,
        OVERRUN_AFTER_PAYLOAD, PENDING_AFTER_PAYLOAD,
    };

    for (version = 0x10001; version <= 0x10005; version++) {
        reset_mock(&st, version);
        st.streaming = st.acquisition_enabled = st.irq_live = true;
        st.maps_delivered = 13;
        st.chunks_delivered = 2600;
        st.buffer_push_failures = 11;
        st.fault_flags = 0x7f;
        mmio[MAP_REG_STATUS / 4] = 15;
        live[MAP_REG_SNAPSHOT_READY / 4] = 3;
        live[MAP_REG_SNAPSHOT_MAP_GENERATION_0 / 4] = 123;
        live[MAP_REG_SNAPSHOT_MAP_GENERATION_1 / 4] = 124;
        live[MAP_REG_SNAPSHOT_START_0_LO / 4] = 0xfedcba98;
        live[MAP_REG_SNAPSHOT_START_0_HI / 4] = 0x01234567;
        live[MAP_REG_SNAPSHOT_START_1_LO / 4] = 0x89abcdef;
        live[MAP_REG_SNAPSHOT_START_1_HI / 4] = 0x76543210;
        for (index = 0; index < 14; index++)
            live[fault_addresses[index] / 4] = index + 100;
        mmio[MAP_REG_BRIDGE_READ_ERROR / 4] = 12;
        mmio[MAP_REG_BRIDGE_RELEASE_ERROR / 4] = 13;
        mmio[MAP_REG_SNAPSHOT_REQUEST_OVERRUN / 4] = 14;
        mmio[MAP_REG_DDC_ACCEPTED_LO / 4] = 0xfffffff0;
        mmio[MAP_REG_DDC_ACCEPTED_HI / 4] = 21;
        mmio[MAP_REG_DDC_EMITTED_LO / 4] = 23;
        mmio[MAP_REG_DDC_EMITTED_HI / 4] = 24;
        mmio[MAP_REG_DDC_DISCONTINUITY / 4] = 25;
        mmio[MAP_REG_DDC_SATURATION / 4] = 26;
        live[MAP_REG_SNAPSHOT_ACCEPTED / 4] = 27;
        live[MAP_REG_SNAPSHOT_PUBLISHED / 4] = 28;
        live[MAP_REG_SNAPSHOT_DENOMINATOR_ZERO / 4] = 29;
        live[MAP_REG_SNAPSHOT_INGRESS_FIFO / 4] = 0x00100009;
        live[MAP_REG_SNAPSHOT_CANDIDATE_FIFO / 4] = 0x00070004;
        assert(receipt(&st, words, output) == 0);
        assert(words[0] == version && words[1] == st.input_rate_msps);
        assert(words[2] == 8 && words[3] == 0x11f && words[4] == 0x11f);
        assert(words[5] == 7 && words[6] == 0x7f && words[7] == 13);
        assert(words[8] == 2600 && words[9] == 11 && words[10] == 3);
        assert(words[11] == 123 && words[12] == 124);
        assert(words[13] == 0xfedcba98 && words[14] == 0x01234567);
        assert(words[15] == 0x89abcdef && words[16] == 0x76543210);
        for (index = 0; index < 14; index++)
            assert(words[17 + index] == index + 100);
        assert(words[31] == 12 && words[32] == 13 && words[33] == 14);
        if (st.input_rate_msps == 15) {
            for (index = 34; index <= 40; index++)
                assert(words[index] == 0);
            for (index = 0xe0 / 4; index <= 0xf4 / 4; index++)
                assert(reads[index] == 0);
        } else {
            assert(words[34] == (version == 0x10004 ? 2U : 1U));
            assert(words[35] == 0xfffffff0 && words[37] == 23);
            assert(words[36] == (version == 0x10004 ? 21U : 0U));
            assert(words[38] == (version == 0x10004 ? 24U : 0U));
            assert(words[39] == 25 && words[40] == 26);
            if (version != 0x10004) {
                assert(!reads[MAP_REG_DDC_ACCEPTED_HI / 4]);
                assert(!reads[MAP_REG_DDC_EMITTED_HI / 4]);
            }
        }
        assert(words[41] == 27 && words[42] == 28 && words[43] == 29);
        assert(words[44] == 0x00100009 && words[45] == 0x00070004);

        /* No IRQ-ready bank: a fault arriving after the final delivered map
         * is invisible to that IRQ path, but visible in the fresh receipt.
         */
        for (index = 0; index < 14; index++) {
            reset_mock(&st, version);
            st.streaming = st.acquisition_enabled = st.irq_live = true;
            st.maps_delivered = 1;
            st.chunks_delivered = 200;
            live[fault_addresses[index] / 4] = 1;
            assert(map_irq_thread(0, &indio) == IRQ_NONE);
            assert(snapshot_writes == 0 && st.fault_flags == 0);
            assert(receipt(&st, words, output) == 0);
            assert(snapshot_writes == 1 && words[10] == 0 && words[7] == 1);
            assert(words[17 + index] == 1 && words[6] == 0);
            assert(receipt(&st, words, output) == 0);
            assert(words[2] == 9 && words[17 + index] == 1);
            fault_receipts++;
        }

        /* Receipts preserve diagnostic and fatal bits without clearing or
         * silently applying a different verdict than the existing driver.
         */
        for (bit = 0; bit < 32; bit++) {
            reset_mock(&st, version);
            live[MAP_REG_SNAPSHOT_HEALTH_FLAGS / 4] = BIT(bit);
            assert(receipt(&st, words, output) == 0);
            assert(words[24] == BIT(bit));
            memset(&snapshot, 0, sizeof(snapshot));
            snapshot.fault_signature[7] = words[24];
            assert(map_snapshot_fault_free(&st, &snapshot) ==
                !(BIT(bit) & (version == 0x10001 ? 0x17ffU :
                    version == 0x10005 ? 0x57ffU : 0x37ffU)));
        }
    }

    for (index = 0; index < ARRAY_SIZE(failure_modes); index++) {
        reset_mock(&st, 0x10005);
        fault = failure_modes[index];
        assert(receipt(&st, words, output) == (fault == TIMEOUT ? -ETIMEDOUT : -EIO));
        assert(snapshot_writes == 1);
        if (fault == TIMEOUT)
            assert(poll_steps == 8);
        failures++;
    }
    reset_mock(&st, 0x10005);
    mmio[MAP_REG_SNAPSHOT_STATUS / 4] = 3;
    assert(receipt(&st, words, output) == -EBUSY && snapshot_writes == 0);
    failures++;
    reset_mock(&st, 0x10005);
    mmio[MAP_REG_SNAPSHOT_GENERATION / 4] = U32_MAX;
    assert(receipt(&st, words, output) == -EOVERFLOW && snapshot_writes == 0);
    failures++;
    reset_mock(&st, 0x10005);
    mmio[MAP_REG_SNAPSHOT_REQUEST_OVERRUN / 4] = U32_MAX;
    assert(receipt(&st, words, output) == -EOVERFLOW && snapshot_writes == 0);
    failures++;
    for (index = 0; index < 3; index++) {
        const u32 regs[] = { MAP_REG_ID, MAP_REG_VERSION, MAP_REG_INPUT_RATE_MSPS };
        reset_mock(&st, 0x10005);
        mmio[regs[index] / 4]++;
        assert(receipt(&st, words, output) == -ENODEV && snapshot_writes == 0);
        failures++;
    }
    for (index = 0; index < 2; index++) {
        reset_mock(&st, 0x10004);
        rollover_reg = index ? MAP_REG_DDC_EMITTED_HI : MAP_REG_DDC_ACCEPTED_HI;
        fault = DDC_ROLLOVER_ONCE;
        assert(receipt(&st, words, output) == 0);
        assert(words[index ? 37 : 35] == 7 && words[index ? 38 : 36] == 1);
        assert(reads[rollover_reg / 4] == 4);
        rollovers++;
        reset_mock(&st, 0x10004);
        rollover_reg = index ? MAP_REG_DDC_EMITTED_HI : MAP_REG_DDC_ACCEPTED_HI;
        fault = DDC_ROLLOVER_FOREVER;
        assert(receipt(&st, words, output) == -EAGAIN);
        assert(reads[rollover_reg / 4] == 6);
        rollovers++;
    }
    reset_mock(&st, 0x10005);
    assert(receipt(&st, words, output) == 0 && lock_reads > 40);
    fputs(output, stdout);
    printf("MAP_HEALTH_RECEIPT_PASS versions=5 fault_receipts=%u failures=%u "
        "rollovers=%u mock_only=1 no_kernel_or_radio_claim=1\n",
        fault_receipts, failures, rollovers);
    return 0;
}
