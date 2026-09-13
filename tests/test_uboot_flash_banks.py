"""Compile the active U-Boot C routines against a fake SPI flash transport."""
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_active_uboot_bank_driver(tmp_path):
    source = (ROOT / "u-boot-xlnx/drivers/mtd/spi/spi_flash.c").read_text()
    def function(name):
        match = re.search(r"(?:static )?int " + name + r"\([^;]+?\n\{.*?\n\}", source, re.S)
        assert match, name
        return match.group()
    header = r'''
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <assert.h>
#include <errno.h>
typedef uint8_t u8;
typedef uint32_t u32;
#define CONFIG_SPI_FLASH_BAR 1
#define SPI_FLASH_16MB_BOUN 0x1000000
#define SPI_XFER_U_PAGE 1
#define SF_DUAL_STACKED_FLASH 2
#define SF_SINGLE_FLASH 0
#define SPI_4BYTE_MODE 4
#define SPI_FLASH_CMD_LEN 4
#define SPI_FLASH_PROG_TIMEOUT 1
#define SPI_FLASH_PAGE_ERASE_TIMEOUT 2
#define SPI_XFER_MMAP 1
#define SPI_XFER_MMAP_END 2
#define debug(...) ((void)0)
struct spi_slave {int flags,bytemode;};
struct spi_flash {struct spi_slave *spi; u32 size; u8 shift,bank_curr,upage_prev,
 dual_flash,bank_read_cmd,bank_write_cmd,read_cmd,dummy_byte; void *memory_map;};
static int physical_bank, wel, fail_wren, fail_write, fail_read, ignore_write;
static int claim_error, claims, releases, data_reads, allocations;
static void *tracked_calloc(size_t a,size_t b) {allocations++;return calloc(a,b);}
static void tracked_free(void *p) {if(p)allocations--;free(p);}
#define calloc tracked_calloc
#define free tracked_free
static int spi_claim_bus(struct spi_slave *s) {claims++;return claim_error;}
static void spi_release_bus(struct spi_slave *s) {releases++;}
static int spi_flash_cmd_write_enable(struct spi_flash *f) {if(fail_wren)return -EIO;wel=1;return 0;}
static int spi_flash_cmd_write(struct spi_slave *s,const u8 *cmd,size_t n,const void *data,size_t len) {
 assert(n==1 && len==1 && cmd[0]==0xc5);
 if(fail_write)return -ETIMEDOUT;
 if(wel && !ignore_write)physical_bank=*(u8*)data;
 wel=0;return 0;
}
static int spi_flash_cmd_wait_ready(struct spi_flash *f,unsigned long timeout) {return 0;}
static int spi_flash_read_common(struct spi_flash *f,const u8 *cmd,size_t n,void *data,size_t len) {
 if(cmd[0]==0xc8) {assert(n==1 && len==1);if(fail_read)return -EIO;*(u8*)data=physical_bank;return 0;}
 assert(cmd[0]==3 && n==4);data_reads++;memset(data,physical_bank?0x22:0x11,len);return 0;
}
static void spi_flash_addr(u32 addr,u8 *cmd,int four) {cmd[1]=addr>>16;cmd[2]=addr>>8;cmd[3]=addr;}
static void spi_flash_copy_mmap(void *to,void *from,size_t len) {memcpy(to,from,len);}
static int spi_xfer(struct spi_slave *s,int a,void*b,void*c,int d) {return 0;}
int spi_flash_write_common(struct spi_flash*,const u8*,size_t,const void*,size_t);
'''
    main = r'''
int main(void) {
 struct spi_slave spi={.bytemode=3};
 struct spi_flash flash={.spi=&spi,.size=0x2000000,.bank_curr=0,
  .bank_read_cmd=0xc8,.bank_write_cmd=0xc5,.read_cmd=3};
 unsigned char buf[4];
 assert(spi_flash_cmd_read_ops(&flash,0xfffffe,sizeof(buf),buf)==0);
 assert(buf[0]==0x11 && buf[1]==0x11 && buf[2]==0x22 && buf[3]==0x22);
 assert(allocations==0);
 assert(spi_flash_write_bar(&flash,0)==0 && physical_bank==0);
 // First chunk succeeds, second bank selection fails. Old code returned 0.
 fail_write=1; data_reads=0;
 assert(spi_flash_cmd_read_ops(&flash,0xfffffe,sizeof(buf),buf)==-ETIMEDOUT);
 assert(data_reads==1 && allocations==0 && flash.bank_curr==0xff);
 fail_write=0;
 assert(spi_flash_write_bar(&flash,0x1000000)==1 && physical_bank==1);
 assert(spi_flash_write_bar(&flash,0)==0 && physical_bank==0);
 ignore_write=1;
 assert(spi_flash_write_bar(&flash,0x1000000)==-EIO && flash.bank_curr==0xff);
 ignore_write=0;fail_read=1;
 assert(spi_flash_write_bar(&flash,0x1000000)==-EIO && flash.bank_curr==0xff);
 fail_read=0;fail_wren=1;
 assert(spi_flash_write_bar(&flash,0)==-EIO);
 assert(claims==releases);
 fail_wren=0;
 assert(spi_flash_write_bar(&flash,0)==0 && physical_bank==0);
 assert(claims==releases);
 puts("PASS: U-Boot physical banks, partial-read error, readback, retry and bus/heap cleanup");
}
'''
    c = tmp_path / "uboot_banks.c"
    c.write_text(header + function("spi_flash_write_common") + function("spi_flash_write_bar")
                 + function("spi_flash_cmd_read_ops") + main)
    binary = tmp_path / "uboot_banks"
    compilation = subprocess.run(["cc", "-std=gnu99", "-Wall", "-Wextra", "-Wno-unused-parameter", "-Wno-sign-compare", "-Werror",
                    str(c), "-o", str(binary)], capture_output=True, text=True)
    assert compilation.returncode == 0, compilation.stderr
    result = subprocess.run([str(binary)], check=True, capture_output=True, text=True)
    assert "PASS:" in result.stdout
