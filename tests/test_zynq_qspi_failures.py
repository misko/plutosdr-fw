"""Exercise the actual controller operation function with phase/IRQ mocks."""
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_incomplete_wire_transaction_stops_controller(tmp_path):
    source = (ROOT / "linux/drivers/spi/spi-zynq-qspi.c").read_text()
    function = re.search(r"static int zynq_qspi_exec_mem_op\([^;]+?\n\{.*?\n\}", source, re.S).group()
    header = r'''
#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>
#include <errno.h>
typedef uint8_t u8;
#define ZYNQ_QSPI_MAX_ADDR_WIDTH 3
#define ZYNQ_QSPI_FIFO_DEPTH 63
#define ZYNQ_QSPI_IEN_OFFSET 1
#define ZYNQ_QSPI_IDIS_OFFSET 2
#define ZYNQ_QSPI_ENABLE_OFFSET 3
#define ZYNQ_QSPI_IXR_RXTX_MASK 7
#define ZYNQ_QSPI_IXR_ALL_MASK 255
#define SPI_MEM_DATA_OUT 2
#define GFP_KERNEL 0
#define dev_dbg(...) ((void)0)
struct completion {int unused;};
struct zynq_qspi {void *dev;u8 *txbuf,*rxbuf;int tx_bytes,rx_bytes,irq;
 struct completion data_completion;bool faulted,is_dual,is_stripe;};
struct spi_device {struct zynq_qspi *master;};
struct spi_mem {struct spi_device *spi;};
struct spi_mem_op {struct {int opcode,nbytes,buswidth;} cmd;
 struct {int nbytes,buswidth;uint32_t val;} addr;
 struct {int nbytes,buswidth;} dummy;
 struct {int nbytes,buswidth,dir;union {void*in;const void*out;} buf;} data;};
static int phases,fail_phase,irq_disabled,synchronized,allocations,cs,alloc_fail;
static void *kzalloc(size_t n,int flags) {if(alloc_fail)return NULL;allocations++;return calloc(1,n);}
static void kfree(void *p) {if(p){if(fail_phase==3)assert(synchronized);allocations--;free(p);}}
static struct zynq_qspi *spi_controller_get_devdata(struct zynq_qspi *q) {return q;}
static void zynq_qspi_chipselect(struct spi_device *s,bool selected) {cs=selected;}
static void zynq_qspi_config_op(struct zynq_qspi *q,struct spi_device*s) {}
static void reinit_completion(struct completion*c) {}
static int msecs_to_jiffies(int n) {return n;}
static void zynq_qspi_write_op(struct zynq_qspi *q,int depth,bool empty) {phases++;}
static void zynq_qspi_write(struct zynq_qspi*q,int offset,int val) {if(offset==2)irq_disabled=1;}
static int wait_for_completion_timeout(struct completion*c,int j) {return phases!=fail_phase;}
static void synchronize_irq(int irq) {assert(irq_disabled);synchronized=1;}
static bool update_stripe(const struct spi_mem_op *op) {return true;}
'''
    main = r'''
int main(void) {
 struct zynq_qspi q={0};struct spi_device spi={&q};struct spi_mem mem={&spi};
 u8 byte=7; struct spi_mem_op op={.cmd={3,1,1},.addr={3,1,0},.dummy={1,1},
  .data={.nbytes=1,.buswidth=1,.dir=2,.buf.out=&byte}};
 for(int i=1;i<=4;i++) {
  memset(&q,0,sizeof(q));phases=irq_disabled=synchronized=0;fail_phase=i;
  assert(zynq_qspi_exec_mem_op(&mem,&op)==-ETIMEDOUT);
  assert(phases==i && cs==0 && q.faulted && allocations==0 && synchronized);
  assert(q.txbuf==NULL && q.rxbuf==NULL);
  assert(zynq_qspi_exec_mem_op(&mem,&op)==-EIO && phases==i);
 }
 memset(&q,0,sizeof(q));phases=irq_disabled=synchronized=0;fail_phase=0;alloc_fail=1;
 assert(zynq_qspi_exec_mem_op(&mem,&op)==-ENOMEM);
 assert(phases==2 && cs==0 && q.faulted && allocations==0);
 memset(&q,0,sizeof(q));phases=0;alloc_fail=0;
 assert(zynq_qspi_exec_mem_op(&mem,&op)==0 && phases==4 && !q.faulted && cs==0 && allocations==0);
}
'''
    c = tmp_path / "controller.c"
    c.write_text(header + function + main)
    binary = tmp_path / "controller"
    build = subprocess.run(["cc", "-std=c99", "-Wall", "-Wextra", "-Wno-unused-parameter",
                            "-Werror", str(c), "-o", str(binary)], capture_output=True, text=True)
    assert build.returncode == 0, build.stderr
    subprocess.run([str(binary)], check=True)
