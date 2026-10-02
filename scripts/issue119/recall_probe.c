/* SPDX-License-Identifier: GPL-2.0 */
/* Interactive, bounded counter lease. EOF closes the descriptor and restores LO. */
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>
#include <linux/adi_rx_counter.h>
static uint32_t crc32(const unsigned char *data,size_t n) {
 uint32_t crc=~0U;
 for(size_t j=0;j<n;j++) {crc^=data[j]; for(int k=0;k<8;k++) crc=(crc>>1)^((crc&1)?0xedb88320U:0);}
 return crc^~0U;
}
int main(int argc,char **argv) {
 const char *path="/sys/bus/iio/devices/iio:device0/out_altvoltage0_RX_LO_fastlock_save";
 struct adi_rx_counter_scan_config cfg={.magic=ADI_RX_COUNTER_MAGIC,.version=1,.size=sizeof(cfg),.profile_mask=15};
 const uint64_t freq[]={959687500,1209687500,1459687500,1709687500};
 char line[512]; unsigned char values[16];
 if(argc!=2)return 2;
 for(int j=0;j<4;j++) {
  FILE *f=fopen(path,"w"); if(!f)return 3; fprintf(f,"%d\n",j); if(fclose(f))return 3;
  f=fopen(path,"r"); if(!f)return 3; if(!fgets(line,sizeof(line),f))return 3; fclose(f);
  char *s=strchr(line,' '); if(!s)return 3; s++;
  for(int k=0;k<16;k++){char *end;unsigned long v=strtoul(s,&end,10);if(end==s||v>255)return 3;values[k]=v;s=end+1;}
  cfg.profiles[j].frequency_hz=freq[j];cfg.profiles[j].crc32=crc32(values,16);
 }
 int fd=open("/dev/tandem-agc-events",O_RDWR);if(fd<0){perror("open");return 4;}
 struct adi_rx_counter_request req={.magic=ADI_RX_COUNTER_MAGIC,.version=1,.size=sizeof(req),.required_features=ADI_RX_COUNTER_FEATURES,.scan_mask=15,.sample_rate_hz=strtoul(argv[1],NULL,10),.samples_per_channel=16384};
 if(ioctl(fd,ADI_RX_COUNTER_IOC_ACQUIRE,&req)){perror("acquire");close(fd);return 5;}
 if(ioctl(fd,ADI_RX_COUNTER_IOC_CONFIGURE_SCAN,&cfg)){perror("configure");close(fd);return 6;}
 puts("READY");fflush(stdout);
 int n=0;
 while(n++<128 && fgets(line,sizeof(line),stdin)) {
  if(line[0]=='q')break;
  unsigned long profile=strtoul(line,NULL,10);if(profile>=4){close(fd);return 7;}
  struct adi_rx_counter_scan_recall r={.magic=ADI_RX_COUNTER_MAGIC,.version=1,.size=sizeof(r),.profile=profile};
  if(ioctl(fd,ADI_RX_COUNTER_IOC_RECALL,&r)){perror("recall");close(fd);return 8;}
  printf("{\"profile\":%u,\"profile_frequency_hz\":%" PRIu64 ",\"crc\":%u,\"before\":%u,\"after\":%u,\"ticks\":%u}\n",r.profile,(uint64_t)r.frequency_hz,r.profile_crc32,r.counter_before,r.counter_after,r.counter_after-r.counter_before);fflush(stdout);
 }
 struct adi_rx_counter_scan_release r={.magic=ADI_RX_COUNTER_MAGIC,.version=1,.size=sizeof(r)};
 if(ioctl(fd,ADI_RX_COUNTER_IOC_RELEASE_SCAN,&r)){perror("release");close(fd);return 9;}
 printf("{\"released_frequency_hz\":%" PRIu64 "}\n",(uint64_t)r.frequency_hz);close(fd);return 0;
}
