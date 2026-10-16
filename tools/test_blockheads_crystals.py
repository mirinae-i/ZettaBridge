#!/usr/bin/env python3
"""Execute authored ARM handlers + original CrystalManager arithmetic under Unicorn.
Only Objective-C/Foundation and persistence/UI boundaries are modeled; not Android gameplay.
"""
import argparse,hashlib,io,json,struct
from pathlib import Path
from elftools.elf.elffile import ELFFile
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
from unicorn.arm_const import *
p=argparse.ArgumentParser();p.add_argument('--game',type=Path,required=True);p.add_argument('--code',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
raw=a.game.read_bytes();assert hashlib.sha256(raw).hexdigest()=='733d821027d69de329d0ba171df2e6013d612edf5a4d327badd001acc30b94c7'
elf=ELFFile(io.BytesIO(raw));syms=elf.get_section_by_name('.dynsym');blob=a.code.read_bytes()
results=[]
def case(base,index,old=40,setup=False,bad_check=False):
 u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u.mem_map(base,0x1100000);u.mem_map(0x25000000,0x200000);u.mem_map(0x30000000,0x100000)
 for seg in elf.iter_segments():
  if seg['p_type']=='PT_LOAD':u.mem_write(base+seg['p_vaddr'],seg.data())
 def w(p):return struct.unpack('<I',u.mem_read(p,4))[0]
 def put(p,v):u.mem_write(p,struct.pack('<I',v&0xffffffff))
 funcs={};nextfn=0x30000000
 for sn in ('.rel.dyn','.rel.plt'):
  for r in elf.get_section_by_name(sn).iter_relocations():
   addr=base+r['r_offset'];t=r['r_info_type'];s=syms.get_symbol(r['r_info_sym']) if r['r_info_sym'] else None
   if t==23:put(addr,w(addr)+base)
   elif s and t in (2,21,22):
    if s['st_shndx']=='SHN_UNDEF':value=nextfn;funcs[value]=s.name;nextfn+=4
    else:value=base+s['st_value']
    put(addr,value+(w(addr) if t==2 else 0))
 u.mem_write(base+0xb60380,blob)
 self=0x25010000;manager=0x25020000;buttons=[0x25030000+i*256 for i in range(4)];title=0x25040000
 def field(o,offset):return o+w(base+offset)
 put(field(self,0xf35258),title)
 for i,v in enumerate(buttons):put(field(self,0xf35268)+4*i,v)
 put(field(manager,0xf349cc),old);put(field(manager,0xf349d8),0x25050000)
 put(field(manager,0xf349c8),0x25051000)
 strings={};alloc=0x25060000;calls=[];changes=[];enabled=[];titles=[]
 def st(p):return bytes(u.mem_read(p,256)).split(b'\0')[0].decode()
 def txt(p):
  if p in strings:return strings[p]
  return st(w(p+8))
 def string(s):
  nonlocal alloc
  alloc+=256;strings[alloc]=s;return alloc
 def finish(value=0):u.reg_write(UC_ARM_REG_R0,value);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
 def hook(uc,addr,size,_):
  if addr==0x300ffffc:u.emu_stop();return
  r=[u.reg_read(reg) for reg in (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3)]
  if addr==base+0x9f3b14:finish(manager);return
  if addr==base+0xb611c0:calls.append('close');finish();return
  if addr==base+0xd10c30:titles.append((r[0],txt(r[2])));finish();return
  if addr==base+0xd10fc4:enabled.append((r[0],r[2]));finish();return
  if addr==base+0x526560:titles.append((r[0],txt(r[2])));finish();return
  if addr not in funcs:return
  name=funcs[addr]
  if name=='objc_msgSend':
   sel=st(r[1])
   if sel=='stringWithUTF8String:':finish(string(st(r[2])))
   elif sel=='stringWithFormat:':finish(string(txt(r[2])%r[3]))
   elif sel=='stringFromMD5':finish(string(hashlib.md5(txt(r[0]).encode()).hexdigest()))
   elif sel=='isEqualToString:':finish(int(txt(r[0])==txt(r[2])))
   elif sel=='retain':finish(r[0])
   elif sel=='crystalCountChanged:':changes.append(r[2]);finish()
   elif sel=='addOperationWithBlock:':calls.append('queued-save');finish()
   elif sel=='save':u.reg_write(UC_ARM_REG_PC,base+0x9f4f34)
   else:raise AssertionError(('unexpected selector',sel))
  elif name=='dispatch_async':calls.append('queued-save');finish()
  else:raise AssertionError(('unexpected import',name))
 u.hook_add(UC_HOOK_CODE,hook);u.reg_write(UC_ARM_REG_SP,0x251f0000);u.reg_write(UC_ARM_REG_LR,0x300ffffc)
 u.reg_write(UC_ARM_REG_R0,self);u.reg_write(UC_ARM_REG_R1,0);u.reg_write(UC_ARM_REG_R2,buttons[index] if index in range(4) else 0x25080000)
 start=base+0xb60380
 if setup:
  fp=0x251f0000;u.reg_write(UC_ARM_REG_FP,fp);u.reg_write(UC_ARM_REG_SP,fp-0x700)
  for i in range(7):put(fp-24+i*4,0x7770+i)
  put(fp+4,0x300ffffc);start=base+0xb60394
 if bad_check:
  start=base+0x9f4f74;u.reg_write(UC_ARM_REG_R0,manager);u.reg_write(UC_ARM_REG_R2,(-200)&0xffffffff);u.reg_write(UC_ARM_REG_R3,string('wrong'))
 u.emu_start(start,0x300ffffc,count=100000)
 assert u.reg_read(UC_ARM_REG_PC)==0x300ffffc,'did not return'
 amount=w(field(manager,0xf349cc));valid=index in range(4) and old<=10000000-[200,1200,3000,10000][index] and old>=0
 if setup:
  assert enabled==[(b,1) for b in buttons]
  assert titles==[(b,'ADD') for b in buttons]+[(title,'LOCAL CRYSTALS')]
  assert u.reg_read(UC_ARM_REG_R0)==self and u.reg_read(UC_ARM_REG_SP)==fp+8
 elif valid and not bad_check:
  wanted=old+[200,1200,3000,10000][index];assert amount==wanted,(amount,wanted)
  assert changes==[1] and calls==['queued-save','close'],(changes,calls)
  assert txt(w(field(manager,0xf349d0)))==hashlib.md5(('7acfe93afc08%dc65ae2c54ecaf07f'%wanted).encode()).hexdigest()
  assert u.mem_read(field(manager,0xf349d4),1)==b'\0'
 else:assert amount==old and not calls and not changes
 results.append(dict(base=hex(base),button=index,starting_balance=old,setup=setup,consistency_rejection=bad_check,passed=True))
for base in (0x10000000,0x40000000):
 for index in range(4):case(base,index)
 case(base,99);case(base,3,10000000);case(base,0,40,True);case(base,0,40,False,True)
a.out.write_text(json.dumps(dict(checks=results,original_modify_executed=True,persistence_boundary='original commit enqueues save; disk/Android not emulated',android_device_tested=False),indent=2)+'\n');print('ARM local-crystal contracts PASS:',len(results))
