/* Real driver code is included below; only its kernel/device dependencies are
 * modeled. Polls execute at most eight mock steps, checking the driver's actual
 * timeout parameters. No mock submission is represented as a DMA completion.
 */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>

typedef uint32_t u32;
typedef uint64_t u64;
#define __iomem
#define U32_MAX UINT32_MAX
#define BIT(n) (UINT32_C(1) << (n))
#define READ_ONCE(value) (value)
#define WRITE_ONCE(value, next) ((value) = (next))
#define DMA_DEV_TO_MEM 2
#define DMA_PREP_INTERRUPT 1
#define IIO_BUFFER_BLOCK_FLAG_CYCLIC BIT(1)
#define min_t(type, a, b) ((type)(a) < (type)(b) ? (type)(a) : (type)(b))
#define rounddown(value, align) ((value) - (value) % (align))
struct mutex { bool held; };
struct clk { unsigned long rate; };
struct pilot_state;
struct iio_buffer { unsigned int length; unsigned long *channel_mask; };
struct iio_dev {
    struct pilot_state *state;
    unsigned int scan_bytes;
    unsigned long *active_scan_mask;
    struct iio_buffer *buffer;
};
struct list_head { unsigned int unused; };
struct iio_dma_buffer_queue {
    void *driver_data;
    struct iio_buffer buffer;
    struct mutex list_lock;
};
struct iio_dma_buffer_block {
    struct { u32 size, flags, bytes_used; } block;
    struct iio_dma_buffer_queue *queue;
    struct list_head head;
    uintptr_t phys_addr;
};
typedef int dma_cookie_t;
struct dma_chan { unsigned int unused; };
struct dmaengine_result { unsigned int unused; };
struct dma_async_tx_descriptor {
    void (*callback_result)(void *, const struct dmaengine_result *);
    void *callback_param;
};
struct dmaengine_buffer {
    struct dma_chan *chan;
    struct iio_dma_buffer_queue queue;
    struct list_head active;
    size_t max_size, align;
};
static struct dmaengine_buffer mock_dma;
static struct dma_chan mock_chan;
static struct dma_async_tx_descriptor mock_descriptor;
static void *iio_priv(struct iio_dev *indio) { return indio->state; }
static void mutex_lock(struct mutex *lock) { assert(!lock->held); lock->held = true; }
static void mutex_unlock(struct mutex *lock) { assert(lock->held); lock->held = false; }
static unsigned long clk_get_rate(struct clk *clock) { return clock->rate; }

static u32 mmio[64];
static char trace[128];
static unsigned int trace_length, status_polls, snapshot_reads;
static unsigned int dma_calls, dma_inflight, dma_completed;
static int dma_result;
static bool clear_stuck, bad_visit_readback, arm_stuck, arm_fault;
static bool drain_stuck, latch_stuck, snapshot_race;
static bool stop_seen;
static unsigned int poll_delay, poll_timeout;

static u32 readl(const void *address);
static void writel(u32 value, void *address);
static void mock_poll_step(const void *address);
int iio_dmaengine_buffer_submit_block(struct iio_dma_buffer_queue *queue,
    struct iio_dma_buffer_block *block, int direction);
#define readl_poll_timeout(address, value, condition, delay, timeout) ({ \
    int mock_result = -ETIMEDOUT; \
    unsigned int mock_poll; \
    poll_delay = (delay); poll_timeout = (timeout); \
    for (mock_poll = 0; mock_poll < 8; mock_poll++) { \
        mock_poll_step(address); \
        (value) = readl(address); \
        if (condition) { mock_result = 0; break; } \
    } \
    mock_result; \
})

#include "pilot_driver_actual.inc"

static void record(char event)
{
    assert(trace_length + 1 < sizeof(trace));
    trace[trace_length++] = event;
    trace[trace_length] = 0;
}

static unsigned int offset(const void *address)
{
    uintptr_t bytes = (uintptr_t)address - (uintptr_t)mmio;
    assert(bytes < sizeof(mmio) && bytes % 4 == 0);
    return bytes;
}

static u32 readl(const void *address)
{
    unsigned int reg = offset(address);
    if (reg >= PIL_SNAPSHOT && reg < PIL_SNAPSHOT + 4 * PIL_WORDS) {
        snapshot_reads++;
        if (snapshot_race && snapshot_reads == 13)
            mmio[PIL_GENERATION / 4]++;
    }
    if (reg == PIL_VISIT && bad_visit_readback)
        return mmio[reg / 4] ^ 1;
    return mmio[reg / 4];
}

static void writel(u32 value, void *address)
{
    unsigned int reg = offset(address);
    if (reg == PIL_VISIT) {
        record('V');
        mmio[reg / 4] = value;
    } else if (reg == PIL_LIMIT) {
        record('L');
        mmio[reg / 4] = value;
    } else {
        assert(reg == PIL_COMMAND);
        switch (value) {
        case PIL_CLEAR:
            record('C');
            assert(!(mmio[PIL_STATUS / 4] & (PIL_ACTIVE | PIL_QUEUED)));
            if (!clear_stuck) {
                mmio[PIL_GENERATION / 4] = 0;
                mmio[PIL_FAULT / 4] = 0;
                mmio[PIL_STATUS / 4] = 0;
            }
            break;
        case PIL_ARM:
            record('A');
            assert(dma_inflight && mmio[PIL_VISIT / 4]);
            if (!arm_stuck)
                mmio[PIL_STATUS / 4] = BIT(4) | PIL_ACTIVE;
            if (arm_fault) {
                mmio[PIL_FAULT / 4] = BIT(0);
                mmio[PIL_STATUS / 4] &= ~PIL_ACTIVE;
            }
            break;
        case PIL_STOP:
            record('S');
            stop_seen = true;
            status_polls = 0;
            mmio[PIL_STATUS / 4] &= ~PIL_ACTIVE;
            break;
        case PIL_LATCH:
            record('T');
            if (!latch_stuck) {
                u32 old = mmio[PIL_GENERATION / 4];
                mmio[PIL_GENERATION / 4] = old == UINT32_MAX ? 1 : old + 1;
            }
            break;
        default:
            assert(false);
        }
    }
}

static void mock_poll_step(const void *address)
{
    if (offset(address) == PIL_STATUS && stop_seen) {
        status_polls++;
        if (!drain_stuck && dma_inflight && status_polls >= 2)
            mmio[PIL_STATUS / 4] &= ~PIL_QUEUED;
    }
}

static struct dmaengine_buffer *iio_buffer_to_dmaengine_buffer(struct iio_buffer *buffer)
{
    assert(buffer);
    record('D');
    dma_calls++;
    return &mock_dma;
}

static void iio_dma_buffer_block_done(struct iio_dma_buffer_block *block)
{
    assert(block->block.bytes_used == 0); /* actual helper's empty-cap path */
    dma_completed++;
}

static void iio_dmaengine_buffer_block_done(void *data, const struct dmaengine_result *result)
{
    (void)data;
    (void)result;
    assert(false); /* controller completion is deliberately not synthesized */
}

static struct dma_async_tx_descriptor *dmaengine_prep_slave_single(
    struct dma_chan *chan, uintptr_t address, size_t length, int direction, int flags)
{
    assert(chan == &mock_chan && address && length);
    assert(direction == DMA_DEV_TO_MEM && flags == DMA_PREP_INTERRUPT);
    return dma_result ? NULL : &mock_descriptor;
}

static struct dma_async_tx_descriptor *dmaengine_prep_dma_cyclic(
    struct dma_chan *chan, uintptr_t address, size_t length, size_t period,
    int direction, int flags)
{
    (void)chan; (void)address; (void)length; (void)period; (void)direction; (void)flags;
    assert(false); /* PIL1 must reject cyclic before the actual helper */
    return NULL;
}

static void spin_lock_irq(struct mutex *lock) { mutex_lock(lock); }
static void spin_unlock_irq(struct mutex *lock) { mutex_unlock(lock); }
static void list_add_tail(struct list_head *entry, struct list_head *head)
{ assert(entry && head); }
static dma_cookie_t dmaengine_submit(struct dma_async_tx_descriptor *descriptor)
{ assert(descriptor == &mock_descriptor); return 1; }
static int dma_submit_error(dma_cookie_t cookie) { return cookie < 0 ? cookie : 0; }
static void dma_async_issue_pending(struct dma_chan *chan)
{ assert(chan == &mock_chan); dma_inflight++; }

/* Execute the real min(max_size)/rounddown path and preserve successful
 * descriptor ownership. The kernel helper's unused queue argument is normal.
 */
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wunused-parameter"
#include "pilot_dmaengine_actual.inc"
#pragma GCC diagnostic pop

struct fixture {
    struct pilot_state st;
    struct clk clock;
    unsigned long mask, buffer_mask;
    struct iio_buffer buffer;
    struct iio_dev indio;
    struct iio_dma_buffer_queue queue;
    struct iio_dma_buffer_block block;
};

static void init(struct fixture *f)
{
    memset(f, 0, sizeof(*f));
    memset(mmio, 0, sizeof(mmio));
    memset(trace, 0, sizeof(trace));
    trace_length = status_polls = snapshot_reads = dma_calls = dma_inflight = dma_completed = 0;
    memset(&mock_dma, 0, sizeof(mock_dma));
    memset(&mock_descriptor, 0, sizeof(mock_descriptor));
    mock_dma.chan = &mock_chan;
    mock_dma.max_size = UINT32_MAX; /* actual AXI DMA driver's advertised cap */
    mock_dma.align = 8;
    dma_result = 0;
    clear_stuck = bad_visit_readback = arm_stuck = arm_fault = false;
    drain_stuck = latch_stuck = snapshot_race = stop_seen = false;
    poll_delay = poll_timeout = 0;
    f->clock.rate = 15000000;
    f->mask = BIT(0) | BIT(1);
    f->buffer_mask = BIT(0) | BIT(1);
    f->st.regs = mmio;
    f->st.source_clk = &f->clock;
    f->st.source_rate = 15000000;
    f->st.visit = 17;
    f->st.limit = 300000;
    f->buffer.length = 25000;
    f->buffer.channel_mask = &f->buffer_mask;
    f->indio.state = &f->st;
    f->indio.scan_bytes = 4;
    f->indio.active_scan_mask = &f->mask;
    f->indio.buffer = &f->buffer;
    f->queue.driver_data = &f->st;
    f->block.block.size = 100000;
    f->block.queue = &f->queue;
    f->block.phys_addr = 0x10000;
}

static unsigned int geometry_tests(void)
{
    struct fixture f;
    unsigned int length, limit, count = 0;
    init(&f);
    assert(PIL_DMA_ALIGNMENT == 8 && PIL_SCAN_BYTES == 4 && PIL_DMA_MAX_BYTES == 16777216);
    for (length = 0; length <= 128; length++) {
        for (limit = 0; limit <= 255; limit++) {
            bool valid = length > 0 && length % 2 == 0 &&
                (!limit || limit % length == 0);
            f.st.limit = limit;
            assert(pilot_buffer_geometry(&f.st, length) == (valid ? 0 : -EINVAL));
            if (valid)
                assert(f.st.buffer_bytes == 4 * length);
            count++;
        }
    }
    f.st.limit = 300000;
    assert(!pilot_buffer_geometry(&f.st, 25000) && f.st.buffer_bytes == 100000);
    count++;
    f.st.limit = 0;
    assert(pilot_buffer_geometry(&f.st, UINT32_MAX) == -EINVAL);
    assert(pilot_buffer_geometry(&f.st, UINT32_MAX / 4 + 1) == -EINVAL);
    assert(pilot_buffer_geometry(&f.st, UINT32_MAX / 4 - 1) == -EINVAL);
    assert(!pilot_buffer_geometry(&f.st, 4194304) && f.st.buffer_bytes == 16777216);
    assert(pilot_buffer_geometry(&f.st, 4194306) == -EINVAL);
    return count + 5;
}

static unsigned int preenable_tests(void)
{
    struct fixture f;
    unsigned int case_id;
    for (case_id = 0; case_id < 13; case_id++) {
        init(&f);
        switch (case_id) {
        case 0: f.st.recovery_failed = true; break;
        case 1: f.st.visit = 0; break;
        case 2: f.indio.scan_bytes = 8; break;
        case 3: f.mask = BIT(0); break;
        case 4: f.buffer.channel_mask = NULL; break;
        case 5: f.clock.rate = 30000000; break;
        case 6: f.buffer.length = 0; break;
        case 7: f.buffer.length = 3; f.st.limit = 3; break;
        case 8: f.st.limit = 300001; break;
        case 9: f.buffer.length = UINT32_MAX; break;
        case 10: f.buffer.length = UINT32_MAX / 4 + 1; break;
        case 11: f.buffer_mask = BIT(1); break;
        case 12: f.buffer.length = 4194306; f.st.limit = 0; break;
        }
        assert(pilot_preenable(&f.indio) == -EINVAL);
        assert(!f.st.lock.held && !trace_length && !dma_calls);
    }
    init(&f);
    mmio[PIL_STATUS / 4] = PIL_ACTIVE;
    assert(pilot_preenable(&f.indio) == -EBUSY && !trace_length);
    mmio[PIL_STATUS / 4] = PIL_QUEUED;
    assert(pilot_preenable(&f.indio) == -EBUSY && !trace_length);
    init(&f);
    mmio[PIL_GENERATION / 4] = 9;
    clear_stuck = true;
    assert(pilot_preenable(&f.indio) == -ETIMEDOUT && !strcmp(trace, "C"));
    assert(poll_delay == 1 && poll_timeout == 10000 && !f.st.lock.held);
    init(&f);
    bad_visit_readback = true;
    assert(pilot_preenable(&f.indio) == -EIO && !strcmp(trace, "CVL"));
    init(&f);
    f.st.dma_error = -EIO;
    f.st.dma_submitted = 42;
    mmio[PIL_FAULT / 4] = BIT(0);
    assert(!pilot_preenable(&f.indio));
    assert(!strcmp(trace, "CVL") && !f.st.dma_error && !f.st.dma_submitted);
    assert(f.st.buffer_bytes == 100000 && !f.st.lock.held);
    for (case_id = 2; case_id <= 4; case_id += 2) {
        init(&f);
        f.clock.rate = f.st.source_rate = 15000000 * case_id;
        assert(!pilot_preenable(&f.indio) && f.st.buffer_bytes == 100000);
    }
    return 20;
}

static unsigned int submission_tests(void)
{
    static const u32 bad_sizes[] = {0, 4, 8, 99992, 99996, 100001, 100008, UINT32_MAX};
    struct fixture f;
    unsigned int n;
    for (n = 0; n < sizeof(bad_sizes) / sizeof(bad_sizes[0]); n++) {
        init(&f);
        assert(!pilot_preenable(&f.indio));
        f.block.block.size = bad_sizes[n];
        assert(pilot_submit(&f.queue, &f.block) == -EINVAL);
        assert(!dma_calls && f.st.dma_error == -EINVAL && !f.st.dma_submitted);
        assert(pilot_postenable(&f.indio) == -EINVAL && !strchr(trace, 'A'));
    }
    init(&f);
    assert(pilot_submit(&f.queue, &f.block) == -EINVAL && !dma_calls);
    init(&f);
    assert(!pilot_preenable(&f.indio));
    f.block.block.flags = IIO_BUFFER_BLOCK_FLAG_CYCLIC;
    assert(pilot_submit(&f.queue, &f.block) == -EINVAL && !dma_calls);
    init(&f);
    assert(!pilot_preenable(&f.indio));
    dma_result = -ENOMEM;
    assert(pilot_submit(&f.queue, &f.block) == -ENOMEM && dma_calls == 1);
    assert(pilot_postenable(&f.indio) == -ENOMEM && !strchr(trace, 'A'));
    dma_result = 0;
    assert(!pilot_submit(&f.queue, &f.block));
    assert(f.st.dma_error == -ENOMEM); /* success cannot erase a prior failure */
    f.st.dma_submitted = UINT32_MAX;
    assert(!pilot_submit(&f.queue, &f.block) && f.st.dma_submitted == UINT32_MAX);
    return 13;
}

static unsigned int lifecycle_tests(void)
{
    struct fixture f;
    unsigned int episode;
    init(&f);
    assert(!pilot_preenable(&f.indio));
    assert(pilot_postenable(&f.indio) == -ENOBUFS && !strchr(trace, 'A'));
    for (episode = 0; episode < 3; episode++) {
        if (episode)
            assert(!pilot_preenable(&f.indio));
        assert(!pilot_submit(&f.queue, &f.block));
        assert(!pilot_postenable(&f.indio));
        assert(poll_delay == 1 && poll_timeout == 10000 && !f.st.lock.held);
        assert(mmio[PIL_STATUS / 4] & PIL_ACTIVE);
        mmio[PIL_STATUS / 4] |= PIL_QUEUED;
        assert(!pilot_predisable(&f.indio));
        assert(status_polls == 2 && poll_delay == 10 && poll_timeout == 25000);
        assert(!(mmio[PIL_STATUS / 4] & (PIL_ACTIVE | PIL_QUEUED)));
        /* STOP/drain must not manufacture completion of the partial descriptor. */
        assert(dma_inflight && !dma_completed && !f.st.recovery_failed);
        dma_inflight = 0; /* mock core teardown; not a completion receipt */
        stop_seen = false;
    }
    assert(!strcmp(trace, "CVLDASCVLDASCVLDAS"));
    init(&f);
    assert(!pilot_preenable(&f.indio) && !pilot_submit(&f.queue, &f.block));
    arm_stuck = true;
    assert(pilot_postenable(&f.indio) == -ETIMEDOUT && !strcmp(trace, "CVLDAS"));
    init(&f);
    assert(!pilot_preenable(&f.indio) && !pilot_submit(&f.queue, &f.block));
    arm_fault = true;
    assert(pilot_postenable(&f.indio) == -EIO && !strcmp(trace, "CVLDAS"));
    init(&f);
    assert(!pilot_preenable(&f.indio) && !pilot_submit(&f.queue, &f.block));
    assert(!pilot_postenable(&f.indio));
    mmio[PIL_STATUS / 4] |= PIL_QUEUED;
    drain_stuck = true;
    assert(pilot_predisable(&f.indio) == -ETIMEDOUT && f.st.recovery_failed);
    assert(status_polls == 8 && poll_timeout == 25000);
    assert(pilot_preenable(&f.indio) == -EINVAL && !strcmp(trace, "CVLDAS"));
    assert(mmio[PIL_STATUS / 4] & PIL_QUEUED); /* never clear an undrained promise */
    return 7;
}

static void snapshot_tests(void)
{
    struct fixture f;
    u32 words[PIL_WORDS], generation;
    unsigned int n;
    init(&f);
    for (n = 0; n < PIL_WORDS; n++)
        mmio[(PIL_SNAPSHOT / 4) + n] = 0x1000 + n;
    mutex_lock(&f.st.lock);
    assert(!pilot_snapshot(&f.st, words, &generation));
    mutex_unlock(&f.st.lock);
    assert(generation == 1 && snapshot_reads == 26);
    for (n = 0; n < PIL_WORDS; n++)
        assert(words[n] == 0x1000 + n);
    mmio[PIL_GENERATION / 4] = UINT32_MAX;
    mutex_lock(&f.st.lock);
    assert(!pilot_snapshot(&f.st, words, &generation) && generation == 1);
    mutex_unlock(&f.st.lock);
    latch_stuck = true;
    mutex_lock(&f.st.lock);
    assert(pilot_snapshot(&f.st, words, &generation) == -ETIMEDOUT);
    mutex_unlock(&f.st.lock);
    assert(poll_delay == 1 && poll_timeout == 10000);
    latch_stuck = false;
    snapshot_race = true;
    snapshot_reads = 0;
    mutex_lock(&f.st.lock);
    assert(pilot_snapshot(&f.st, words, &generation) == -EIO);
    mutex_unlock(&f.st.lock);
}

static unsigned int helper_geometry_tests(void)
{
    static const size_t cap[] = {0, 7, 8, 99999, 100000, UINT32_MAX, UINT32_MAX, UINT32_MAX};
    static const size_t align[] = {8, 8, 8, 8, 8, 8, 64, 131072};
    static const u32 expected[] = {0, 0, 8, 99992, 100000, 100000, 99968, 0};
    struct fixture f;
    unsigned int n;
    for (n = 0; n < sizeof(cap) / sizeof(cap[0]); n++) {
        init(&f);
        assert(!pilot_preenable(&f.indio));
        mock_dma.max_size = cap[n];
        mock_dma.align = align[n];
        /* Actual helper may own a truncated in-flight block already. The
         * driver must retain success to the core, not free that reference,
         * while its sticky error prevents postenable from arming the source.
         */
        assert(!pilot_submit(&f.queue, &f.block));
        assert(f.block.block.bytes_used == expected[n]);
        assert(dma_calls == 1 && f.st.dma_submitted == 1);
        if (expected[n] != 100000) {
            assert(f.st.dma_error == -EMSGSIZE);
            assert(pilot_postenable(&f.indio) == -EMSGSIZE && !strchr(trace, 'A'));
        } else {
            assert(!f.st.dma_error && !pilot_postenable(&f.indio));
        }
        assert(dma_inflight == (expected[n] != 0));
        assert(dma_completed == (expected[n] == 0));
    }
    return n;
}

int main(void)
{
    unsigned int geometry = geometry_tests();
    unsigned int admission = preenable_tests();
    unsigned int submission = submission_tests();
    unsigned int lifecycle = lifecycle_tests();
    unsigned int helper_cases = helper_geometry_tests();
    snapshot_tests();
    printf("PILOT_DRIVER_LIFECYCLE_PASS geometry_cases=%u admission=%u "
        "submission=%u lifecycle=%u helper_cap_alignment=%u snapshots=4 "
        "mock_only=1 no_dma_completion_claim=1\n",
        geometry, admission, submission, lifecycle, helper_cases);
    return 0;
}
