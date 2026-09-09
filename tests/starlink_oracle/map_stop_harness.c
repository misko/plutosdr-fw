/* Actual driver C follows kernel/MMIO mocks. This does not simulate FPGA
 * clocks, network IIO, a real mutex scheduler, or durable host delivery.
 */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdarg.h>
#include <stdlib.h>
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
#define U16_MAX UINT16_MAX
#define ARRAY_SIZE(array) (sizeof(array) / sizeof((array)[0]))
#define lower_32_bits(value) ((u32)(value))
#define upper_32_bits(value) ((u32)((u64)(value) >> 32))
#define IRQ_NONE 0
#define IRQ_HANDLED 1
struct mutex { bool held; };
struct adi_starlink_pss_map;
struct iio_dev { struct adi_starlink_pss_map *state; };
struct device { struct iio_dev *indio; };
struct device_attribute { unsigned int unused; };
static struct adi_starlink_pss_map *active;
static unsigned int lock_entries, lock_exits, irq_disables;
static struct iio_dev *dev_to_iio_dev(struct device *dev) { return dev->indio; }
static void *iio_priv(struct iio_dev *dev) { return dev->state; }
static void mutex_lock(struct mutex *lock)
{ assert(!lock->held); lock->held = true; lock_entries++; }
static void mutex_unlock(struct mutex *lock)
{ assert(lock->held); lock->held = false; lock_exits++; }
static void disable_irq_nosync(int irq) { irq_disables++; }
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
static int kstrtou32(const char *text, unsigned int base, u32 *value)
{
    char *end;
    unsigned long long parsed;
    if (!*text || *text == '-' || *text == ' ')
        return -EINVAL;
    errno = 0;
    parsed = strtoull(text, &end, base);
    if (errno == ERANGE || parsed > UINT32_MAX)
        return -ERANGE;
    if (end == text || (*end && strcmp(end, "\n")))
        return -EINVAL;
    *value = parsed;
    return 0;
}
static u32 ioread32(const void *address);
static void iowrite32(u32 value, void *address);
static int iio_push_to_buffers(struct iio_dev *indio, const void *scan);
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

#include "map_stop_actual.inc"

static u32 mmio[64], live[64], stop[MAP_STOP_WORDS], selector;
static u32 staged, reject_code, bank, data_index;
static unsigned int ticket_writes, control_writes, selector_writes, stop_reads;
static unsigned int pushes, release_writes, mutation_hits, stop_completion_count;
static unsigned int push_failure, release_failure, copy_failure;
static bool acceptance_timeout, tear_forever, tear_once, snapshot_timeout;
static bool lose_ticket_after_poll, accepted_in_poll, late_copy_fault;
static unsigned int transition_field;
static u16 map_storage[MAP_PHASE_BINS];
static struct iio_dev buffer_device;

static void check_unlocked(void)
{ assert(!active->lock.held && lock_entries == lock_exits); }

static u32 ioread32(const void *address)
{
    size_t reg = (const unsigned char *)address - (const unsigned char *)mmio;
    assert(active->lock.held && reg < sizeof(mmio) && reg % 4 == 0);
    if (reg == MAP_REG_STOP_TICKET)
        return stop[3];
    if (reg == MAP_REG_STOP_WORD) {
        assert(selector < MAP_STOP_WORDS);
        if (lose_ticket_after_poll && accepted_in_poll) {
            stop[3] = stop[4] = 0;
            stop[2] = MAP_STOP_ENABLED;
            lose_ticket_after_poll = false;
        }
        stop_reads++;
        if (selector == 7 && (tear_forever || tear_once)) {
            stop[3]++;
            stop[4]++;
            stop[6] += MAP_PHASE_BINS * 64;
            stop[8] += MAP_PHASE_BINS * 64;
            mutation_hits++;
            tear_once = false;
        }
        if (selector == 7 && transition_field) {
            if (transition_field < MAP_STOP_WORDS) stop[transition_field] ^= 1U;
            else {
                mmio[MAP_REG_STATUS / 4] ^= MAP_STATUS_ENABLED;
                if (transition_field == 13) stop[2] ^= MAP_STOP_ENABLED;
            }
            transition_field = 0;
            mutation_hits++;
        }
        return stop[selector];
    }
    if (reg == MAP_REG_STATUS)
        return mmio[reg / 4] | ((live[MAP_REG_SNAPSHOT_READY / 4] & 3U) << 2);
    if (reg == MAP_REG_DATA) {
        assert(data_index < MAP_PHASE_BINS);
        if (late_copy_fault && data_index == 100)
            live[MAP_REG_SNAPSHOT_HEALTH_FLAGS / 4] = BIT(14);
        return copy_failure ? 0x10000U : bank * 1000U + (data_index++ % 1000U);
    }
    return mmio[reg / 4];
}

static void iowrite32(u32 value, void *address)
{
    size_t reg = (unsigned char *)address - (unsigned char *)mmio;
    assert(active->lock.held && reg < sizeof(mmio) && reg % 4 == 0);
    switch (reg) {
    case MAP_REG_STOP_WORD:
        assert(value < MAP_STOP_WORDS);
        selector = value;
        selector_writes++;
        break;
    case MAP_REG_STOP_TICKET:
        ticket_writes++;
        if (value == stop[3]) { stop[11] = 0; break; }
        if (staged == value) { stop[11] = 0; break; }
        if (staged || (stop[2] & BIT(0))) { stop[11] = 3; break; }
        staged = value;
        stop[2] |= BIT(0);
        stop[11] = 0;
        break;
    case MAP_REG_CONTROL:
        assert(value == 0); /* Only a real IRQ fault may invoke legacy abort. */
        control_writes++;
        mmio[MAP_REG_STATUS / 4] &= ~MAP_STATUS_ENABLED;
        stop[2] &= ~MAP_STOP_ENABLED;
        break;
    case MAP_REG_SNAPSHOT_CONTROL:
        assert(value == 1);
        mmio[MAP_REG_SNAPSHOT_STATUS / 4] = 2;
        break;
    case MAP_REG_SELECT: assert(value < 2); bank = value; break;
    case MAP_REG_INDEX: assert(value == 0); data_index = 0; break;
    case MAP_REG_RELEASE:
        assert(value == 1);
        release_writes++;
        if (release_failure) {
            mmio[MAP_REG_BRIDGE_RELEASE_ERROR / 4]++;
            mmio[MAP_REG_COMMAND_STATUS / 4] = MAP_COMMAND_RELEASE_ERROR;
        } else live[MAP_REG_SNAPSHOT_READY / 4] &= ~BIT(bank);
        break;
    default: assert(!"unexpected write");
    }
}

static void poll_step(void)
{
    unsigned int reg;
    poll_steps++;
    if (staged && !acceptance_timeout) {
        if (reject_code) {
            stop[11] = reject_code;
            stop[2] &= ~BIT(0);
        } else { stop[3] = staged; accepted_in_poll = true; }
        staged = 0;
    }
    if (snapshot_timeout || !(mmio[MAP_REG_SNAPSHOT_STATUS / 4] & 2U))
        return;
    for (reg = 0x3c; reg <= 0x78; reg += 4)
        mmio[reg / 4] = live[reg / 4];
    for (reg = 0x88; reg <= 0xac; reg += 4)
        mmio[reg / 4] = live[reg / 4];
    mmio[MAP_REG_SNAPSHOT_GENERATION / 4]++;
    mmio[MAP_REG_SNAPSHOT_STATUS / 4] = 1;
}

static int iio_push_to_buffers(struct iio_dev *indio, const void *data)
{
    const struct map_scan *scan = data;
    unsigned int chunk = pushes % MAP_CHUNKS, index;
    const u16 *samples = (const u16 *)&scan->words[MAP_META_WORDS];
    assert(active->lock.held && indio->state == active);
    if (push_failure && pushes + 1 == push_failure)
        return -ENOSPC;
    assert(scan->words[0] == MAP_CHUNK_MAGIC && scan->words[1] == MAP_STOP_VERSION);
    assert(scan->words[2] == 41U + bank && scan->words[3] == chunk);
    assert(scan->words[4] == MAP_CHUNKS && scan->words[7] == chunk * MAP_CHUNK_BINS);
    assert(scan->words[5] == live[(MAP_REG_SNAPSHOT_START_0_LO + bank * 8) / 4]);
    assert(scan->words[6] == live[(MAP_REG_SNAPSHOT_START_0_HI + bank * 8) / 4]);
    assert(scan->words[8] == MAP_CHUNK_BINS);
    for (index = 0; index < MAP_CHUNK_BINS; index++)
        assert(samples[index] == bank * 1000U + ((chunk * MAP_CHUNK_BINS + index) % 1000U));
    for (index = MAP_CHUNK_PAYLOAD_WORDS; index < MAP_SCAN_WORDS; index++)
        assert(scan->words[index] == 0);
    pushes++;
    return 0;
}

static void reset_mock(struct adi_starlink_pss_map *st)
{
    memset(st, 0, sizeof(*st));
    memset(mmio, 0, sizeof(mmio));
    memset(live, 0, sizeof(live));
    memset(stop, 0, sizeof(stop));
    active = st;
    st->regs = mmio;
    st->version = MAP_STOP_VERSION;
    st->input_rate_msps = 15;
    st->map = map_storage;
    buffer_device.state = st;
    st->indio_dev = &buffer_device;
    st->streaming = st->irq_live = st->acquisition_enabled = true;
    mmio[MAP_REG_ID / 4] = MAP_IDENTIFICATION;
    mmio[MAP_REG_VERSION / 4] = MAP_STOP_VERSION;
    mmio[MAP_REG_CAPABILITIES / 4] = MAP_STOP_CAPABILITIES;
    mmio[MAP_REG_PHASE_BINS / 4] = MAP_PHASE_BINS;
    mmio[MAP_REG_TILE_GEOMETRY / 4] = MAP_TILE_GEOMETRY;
    mmio[MAP_REG_INPUT_RATE_MSPS / 4] = 15;
    mmio[MAP_REG_DDC_CONFIG / 4] = 0x000f0202;
    mmio[MAP_REG_STATUS / 4] = MAP_STATUS_EPOCH_LIVE | MAP_STATUS_ENABLED;
    stop[0] = MAP_STOP_MAGIC;
    stop[1] = MAP_STOP_VERSION_WORDS;
    stop[2] = MAP_STOP_ENABLED;
    selector = staged = reject_code = bank = data_index = 0;
    lock_entries = lock_exits = irq_disables = poll_steps = 0;
    ticket_writes = control_writes = selector_writes = stop_reads = 0;
    pushes = release_writes = mutation_hits = stop_completion_count = 0;
    push_failure = release_failure = copy_failure = 0;
    acceptance_timeout = tear_forever = tear_once = snapshot_timeout = false;
    lose_ticket_after_poll = accepted_in_poll = late_copy_fault = false;
    transition_field = 0;
}

static int request(struct device *dev, const char *text)
{
    int result = map_acquisition_stop_request_store(dev, NULL, text, strlen(text));
    check_unlocked();
    return result;
}

static int receipt(struct device *dev, char *buf)
{
    int result;
    memset(buf, '!', 4096);
    result = map_acquisition_stop_show(dev, NULL, buf);
    check_unlocked();
    if (result < 0) assert(buf[0] == '!');
    else assert(result == 118 && buf[result - 1] == '\n' && !buf[result]);
    return result;
}

static void complete_stop(void)
{
    assert(stop[3] && (stop[2] & BIT(0)));
    stop[2] = BIT(1) | BIT(2) | BIT(4);
    stop[4] = stop[3];
    stop[5] = 42;
    stop[6] = 0xfff80000;
    stop[7] = 1;
    stop[8] = 0x000b8800;
    stop[9] = 2;
    mmio[MAP_REG_STATUS / 4] &= ~MAP_STATUS_ENABLED;
    live[MAP_REG_SNAPSHOT_READY / 4] = 3;
    live[MAP_REG_SNAPSHOT_MAP_GENERATION_0 / 4] = 41;
    live[MAP_REG_SNAPSHOT_MAP_GENERATION_1 / 4] = 42;
    live[MAP_REG_SNAPSHOT_START_0_LO / 4] = 123;
    live[MAP_REG_SNAPSHOT_START_1_LO / 4] = stop[6];
    live[MAP_REG_SNAPSHOT_START_1_HI / 4] = stop[7];
    stop_completion_count++;
}

int main(void)
{
    struct adi_starlink_pss_map st;
    struct iio_dev indio = { .state = &st };
    struct device dev = { .indio = &indio };
    const int errors[] = {0, -EINVAL, -ERANGE, -EBUSY, -EPIPE, -EIO};
    const char *bad[] = {"0", "-1", "4294967296", "1.0", "1x", "", "true"};
    const unsigned int contract_regs[] = {MAP_REG_ID, MAP_REG_VERSION,
        MAP_REG_CAPABILITIES, MAP_REG_PHASE_BINS, MAP_REG_TILE_GEOMETRY,
        MAP_REG_INPUT_RATE_MSPS, MAP_REG_DDC_CONFIG, MAP_REG_DDC_GROUP_DELAY};
    unsigned int index, bit, failed_paths = 0;
    char output[4096];

    reset_mock(&st);
    assert(request(&dev, "1\n") == 2 && stop[3] == 1 && (stop[2] & BIT(0)));
    assert(st.streaming && st.irq_live && st.acquisition_enabled);
    assert(request(&dev, "2") == -EBUSY && stop[3] == 1 && (stop[2] & BIT(0)));
    assert(!staged && request(&dev, "1") == 1); /* no competing overwrite */
    /* Polling a source-quiet pending tile never manufactures completion. */
    for (index = 0; index < 20; index++) {
        assert(receipt(&dev, output) == 118 && (stop[2] & BIT(0)));
        assert(stop_completion_count == 0 && control_writes == 0 && irq_disables == 0);
    }
    assert(map_irq_thread(0, &indio) == IRQ_NONE);
    check_unlocked();
    complete_stop();
    assert(receipt(&dev, output) == 118);
    puts(output);
    assert(!st.acquisition_enabled && st.streaming && st.irq_live);
    assert(request(&dev, "1") == 1 && stop_completion_count == 1);
    assert(map_irq_thread(0, &indio) == IRQ_HANDLED);
    check_unlocked();
    assert(st.maps_delivered == 1 && st.chunks_delivered == 200 && pushes == 200);
    assert(map_irq_thread(0, &indio) == IRQ_HANDLED);
    check_unlocked();
    assert(st.maps_delivered == 2 && st.chunks_delivered == 400 && pushes == 400);
    assert(release_writes == 2 && !live[MAP_REG_SNAPSHOT_READY / 4]);
    assert(!st.fault_flags && st.streaming && st.irq_live && !irq_disables && !control_writes);
    /* Fresh late failure is visible without changing retained coordinates. */
    stop[2] |= BIT(3); stop[10] = BIT(0);
    assert(receipt(&dev, output) == 118 && strstr(output, "0000001e"));
    assert(stop[6] == 0xfff80000 && stop[9] == 2);
    /* Driver retry writes the old ticket, never invents the next ticket.
     * The separate RTL suite establishes actual hardware idempotence.
     */
    mmio[MAP_REG_STATUS / 4] |= MAP_STATUS_ENABLED;
    stop[2] = MAP_STOP_ENABLED;
    assert(request(&dev, "1") == 1 && !staged && stop_completion_count == 1);
    assert(stop[3] == 1 && stop[4] == 1 && stop[6] == 0xfff80000);

    for (index = 0; index < ARRAY_SIZE(bad); index++) {
        reset_mock(&st);
        assert(request(&dev, bad[index]) < 0 && !ticket_writes);
    }
    for (index = 0; index < ARRAY_SIZE(contract_regs); index++) {
        for (bit = 0; bit < 32; bit++) {
            reset_mock(&st);
            mmio[contract_regs[index] / 4] ^= BIT(bit);
            assert(receipt(&dev, output) == -ENODEV && !selector_writes);
        }
    }
    for (index = 0x10001; index <= 0x10005; index++) {
        reset_mock(&st); st.version = index;
        assert(request(&dev, "1") == -EOPNOTSUPP && !selector_writes);
    }
    for (index = 1; index <= 5; index++) {
        reset_mock(&st); reject_code = index;
        assert(request(&dev, "1") == errors[index] && stop[3] == 0);
        assert(!control_writes && !irq_disables && st.streaming && st.irq_live);
    }
    reset_mock(&st); acceptance_timeout = true;
    assert(request(&dev, "1") == -ETIMEDOUT && staged == 1 && (stop[2] & BIT(0)));
    assert(receipt(&dev, output) == 118 && !control_writes && !irq_disables);
    acceptance_timeout = false;
    assert(request(&dev, "1") == 1 && stop[3] == 1); /* retry same staged ticket */
    reset_mock(&st); lose_ticket_after_poll = true;
    assert(request(&dev, "1") == -EIO && stop[3] == 0);
    assert(!control_writes && !irq_disables); /* vanished epoch != cancellation */
    reset_mock(&st); stop[3] = U32_MAX;
    assert(request(&dev, "1") == -EOVERFLOW && !ticket_writes);
    assert(request(&dev, "4294967295") == 10); /* no wrap; idempotent max */
    reset_mock(&st); assert(request(&dev, "2") == -ERANGE && !ticket_writes);
    reset_mock(&st); st.streaming = false;
    assert(request(&dev, "1") == -EBUSY && !ticket_writes);
    reset_mock(&st); st.irq_live = false;
    assert(request(&dev, "1") == -EBUSY && !ticket_writes);
    reset_mock(&st); st.fault_flags = MAP_FAULT_DATA;
    assert(request(&dev, "1") == -EIO && !ticket_writes);
    reset_mock(&st); mmio[MAP_REG_STATUS / 4] &= ~MAP_STATUS_ENABLED;
    stop[2] &= ~MAP_STOP_ENABLED;
    assert(request(&dev, "1") == -EPIPE && !ticket_writes);
    reset_mock(&st); tear_once = true;
    assert(receipt(&dev, output) == 118 && mutation_hits == 1);
    reset_mock(&st); tear_forever = true;
    assert(receipt(&dev, output) == -EAGAIN && mutation_hits == 3);
    for (index = 0; index < 6; index++) {
        const unsigned int fields[] = {2, 4, 10, 11, 12, 13};
        reset_mock(&st); transition_field = fields[index];
        assert(receipt(&dev, output) == (fields[index] == 12 ? -EAGAIN : 118));
        assert(mutation_hits == 1 && stop_reads == (fields[index] == 12 ? 66 : 44));
    }
    for (index = 0; index < 5; index++) {
        reset_mock(&st);
        switch (index) {
        case 0: stop[0] ^= 1; break;
        case 1: stop[1] ^= 1; break;
        case 2: stop[2] |= BIT(6); break;
        case 3: stop[10] |= BIT(6); break;
        case 4: stop[11] = 6; break;
        }
        assert(receipt(&dev, output) == -EPROTO);
    }
    reset_mock(&st); stop[2] &= ~MAP_STOP_ENABLED;
    assert(receipt(&dev, output) == -EAGAIN);
    reset_mock(&st); mmio[MAP_REG_STATUS / 4] &= ~MAP_STATUS_EPOCH_LIVE;
    assert(receipt(&dev, output) == -ENODEV);

    /* Actual IRQ copy/push/release and late-health errors remain fail-closed. */
    for (index = 0; index < 6; index++) {
        reset_mock(&st);
        assert(request(&dev, "1") == 1);
        complete_stop();
        assert(receipt(&dev, output) == 118);
        switch (index) {
        case 0: copy_failure = 1; break;
        case 1: push_failure = 123; break;
        case 2: release_failure = 1; break;
        case 3: live[MAP_REG_SNAPSHOT_HEALTH_FLAGS / 4] = BIT(14); break;
        case 4: snapshot_timeout = true; break;
        case 5: late_copy_fault = true; break;
        }
        assert(map_irq_thread(0, &indio) == IRQ_HANDLED);
        check_unlocked();
        assert(st.fault_flags && !st.irq_live && irq_disables == 1 && control_writes == 1);
        assert(st.maps_delivered == 0 && st.streaming);
        if (index == 1) assert(st.chunks_delivered == 122 && st.buffer_push_failures == 1);
        if (index == 2) assert(st.chunks_delivered == 200 && !st.buffer_push_failures);
        failed_paths++;
    }
    printf("MAP_STOP_DRIVER_PASS exact_chunks=400 retained_irq=1 contract_mutations=256 "
           "irq_failures=%u mock_only=1 no_kernel_or_radio_claim=1\n", failed_paths);
    return 0;
}
