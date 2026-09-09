"""AXI payload qualifiers retain dispatch timing under channel/response stalls."""
import subprocess

import numpy as np

from .test_capture_rtl import IP_ROOT


BENCH=r'''
`timescale 1ns/1ps
module tb;
reg clk=0,resetn=0;
always #5 clk=~clk;
reg s_axi_awvalid=0,s_axi_wvalid=0,s_axi_bready=0,s_axi_arvalid=0,s_axi_rready=0;
reg [11:0] s_axi_awaddr=0,s_axi_araddr=0;
reg [31:0] s_axi_wdata=0;
reg [3:0] s_axi_wstrb=0;
wire s_axi_awready,s_axi_wready,s_axi_bvalid,s_axi_arready,s_axi_rvalid;
wire [1:0] s_axi_bresp,s_axi_rresp;
wire [31:0] s_axi_rdata,up_wdata;
wire [3:0] up_wstrb,up_wdata_byte_zero;
wire up_wreq,up_rreq;
wire [9:0] up_waddr,up_raddr;
wire up_wack=up_wreq,up_rack=up_rreq;
wire [31:0] up_rdata=0;
starlink_glrt_axi_lite #(.AXI_ADDRESS_WIDTH(12)) dut(.*);
integer cycle=0,last_capture=0,requests=0;
reg [9:0] expected_address;
reg [31:0] expected_data;
reg [3:0] expected_strobe;
always @(posedge clk) begin
 cycle=cycle+1;
 if((s_axi_awvalid&&s_axi_awready)||(s_axi_wvalid&&s_axi_wready)) last_capture=cycle;
 #1;
 if(resetn) begin
  if(up_wdata_byte_zero !== {up_wdata[31:24]==0,up_wdata[23:16]==0,up_wdata[15:8]==0,up_wdata[7:0]==0})
   $fatal(1,"payload qualifiers are not aligned with unmasked data");
  if(up_wreq) begin
   if(cycle!=last_capture+1) $fatal(1,"request dispatch cycle changed");
   if({up_waddr,up_wdata,up_wstrb} !== {expected_address,expected_data,expected_strobe})
    $fatal(1,"request payload changed under channel skew");
   requests=requests+1;
  end
 end
end
integer fd,rc,address,value,strobe,aw_delay,w_delay,hold_cycles,n,count=0;
initial begin
 repeat(4) @(negedge clk);
 resetn=1;
 fd=$fopen("writes.txt","r");
 if(!fd) $fatal(1,"input missing");
 while(!$feof(fd)) begin
  rc=$fscanf(fd,"%h %h %h %d %d %d\n",address,value,strobe,aw_delay,w_delay,hold_cycles);
  if(rc!=6) $fatal(1,"bad input");
  expected_address=address>>2;expected_data=value;expected_strobe=strobe;
  fork
   begin
    repeat(aw_delay+1) @(negedge clk);
    s_axi_awaddr=address;s_axi_awvalid=1;
    do @(posedge clk); while(!s_axi_awready);
    @(negedge clk);s_axi_awvalid=0;s_axi_awaddr=12'hffc;
   end
   begin
    repeat(w_delay+1) @(negedge clk);
    s_axi_wdata=value;s_axi_wstrb=strobe;s_axi_wvalid=1;
    do @(posedge clk); while(!s_axi_wready);
    @(negedge clk);s_axi_wvalid=0;s_axi_wdata=~value;s_axi_wstrb=~strobe;
   end
  join
  do @(negedge clk); while(!s_axi_bvalid);
  repeat(hold_cycles) begin
   @(negedge clk);
   if(!s_axi_bvalid || s_axi_bresp!=0 || s_axi_awready || s_axi_wready)
    $fatal(1,"response was not held or accepted a second request");
  end
  s_axi_bready=1;
  @(negedge clk);s_axi_bready=0;
  count=count+1;
 end
 if(requests!=count) $fatal(1,"transaction request count mismatch");
 $display("PASS %d",count);
 $finish;
end
endmodule
'''


def test_byte_zero_payload_flags_preserve_axi_dispatch_and_stalls(tmp_path):
    rng=np.random.default_rng(61093)
    values=[value<<(8*byte) for byte in range(4) for value in range(256)]
    values += rng.integers(0,1<<32,256,dtype=np.uint64).tolist()
    rows=[f"{(n%256)*4:x} {value:x} {n%16:x} {n%4} {(n//4)%4} {n%7}"
          for n,value in enumerate(values)]
    (tmp_path/"writes.txt").write_text("\n".join(rows)+"\n")
    (tmp_path/"tb.sv").write_text(BENCH)
    built=subprocess.run(["iverilog","-g2012","-s","tb","-o",str(tmp_path/"sim"),
        str(tmp_path/"tb.sv"),str(IP_ROOT/"starlink_glrt_axi_lite.v")],capture_output=True,text=True)
    assert built.returncode==0,built.stdout+built.stderr
    ran=subprocess.run(["vvp",str(tmp_path/"sim")],cwd=tmp_path,capture_output=True,text=True,timeout=20)
    assert ran.returncode==0,ran.stdout+ran.stderr
    assert f"PASS {len(rows):11d}" in ran.stdout
