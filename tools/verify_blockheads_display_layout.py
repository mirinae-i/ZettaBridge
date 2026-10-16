#!/usr/bin/env python3
"""Verify the native display layout against the user's original game library."""
import argparse
import hashlib
import io
import json
import struct
from pathlib import Path
from elftools.elf.elffile import ELFFile

CLASSES = {
 'UIApplication': (0xe8e500, {'_delegate':0xf3135c,'_applicationState':0xf31358}),
 'EvolutionAppDelegate': (0xe92218, {'_viewController':0xf358a0}),
 'EvolutionViewController': (0xe90f80, {
  'context':0xf33868,'animating':0xf3386c,'animationFrameInterval':0xf33870,
  'displayLink':0xf33890,'openGLInitialized':0xf33888,'gameView':0xf33864,
  'isActive':0xf3387c,'frameHasBeenDrawnSinceActivate':0xf33880,'gdprCheckIsComplete':0xf33874}),
 'GameView': (0xe91520, {'glView':0xf34328,'windowInfo':0xf34334,'projectionMatrix':0xf34370}),
 'EAGLView': (0xe918b8, {'framebufferWidth':0xf34998,'framebufferHeight':0xf3499c}),
 'CADisplayLink': (0xe8df38, {'_timer':0xf31020,'_paused':0xf30ffc,'_suspended':0xf3101c,
  '_timestamp':0xf31004,'_frameInterval':0xf31010,'_frameIndex':0xf31028})
}

def verify(path):
 raw=path.read_bytes();elf=ELFFile(io.BytesIO(raw));data=bytearray(raw)
 segments=[s for s in elf.iter_segments() if s['p_type']=='PT_LOAD']
 def offset(a):
  for s in segments:
   if s['p_vaddr']<=a<s['p_vaddr']+s['p_filesz']:return s['p_offset']+a-s['p_vaddr']
  raise ValueError('unmapped file address '+hex(a))
 def word(a):return struct.unpack_from('<I',data,offset(a))[0]
 def string(a):i=offset(a);return bytes(data[i:data.index(0,i)]).decode()
 build_id=raw[offset(0x158):offset(0x158)+20].hex()
 assert build_id=='81b7aa3ed0b95082858efc0a7a710115221c26b9'
 fingerprints={0x240c68:0xe92d4c10,0x7816e8:0xe92d4df0,0x781a44:0xe92d4df0,0x9c5234:0xe92d4df0,0x9c5260:0xe300500b,0x496074:0xe12fff30}
 for a,v in fingerprints.items():assert word(a)==v,(hex(a),hex(word(a)))
 syms=elf.get_section_by_name('.dynsym')
 for rel in elf.get_section_by_name('.rel.dyn').iter_relocations():
  if rel['r_info_type'] in (2,21,22) and rel['r_info_sym']:
   sym=syms.get_symbol(rel['r_info_sym'])
   if sym['st_shndx']!='SHN_UNDEF':
    a=rel['r_offset'];v=sym['st_value']+(word(a) if rel['r_info_type']==2 else 0)
    struct.pack_into('<I',data,offset(a),v&0xffffffff)
 verified={}
 for name,(expected,fields) in CLASSES.items():
  addr=syms.get_symbol_by_name('OBJC_CLASS_$_'+name)[0]['st_value'];assert addr==expected
  ro=word(addr+16)&~3;ivars=word(ro+28);found={}
  for i in range(word(ivars+4)):
   entry=ivars+8+i*word(ivars);found[string(word(entry+4))]=word(entry)
  for field,rva in fields.items():assert found[field]==rva,(name,field,hex(found[field]))
  verified[name]={'class_rva':hex(addr),'offset_variables':{k:hex(v) for k,v in fields.items()}}
 assert any(s['p_vaddr']+s['p_filesz']<=0x106055c<s['p_vaddr']+s['p_memsz'] for s in segments)
 assert any(s['p_vaddr']+s['p_filesz']<=0x10628c8<s['p_vaddr']+s['p_memsz'] for s in segments)
 return dict(checks_passed=True,sha256=hashlib.sha256(raw).hexdigest(),build_id=build_id,
  classes=verified,code_fingerprints={hex(a):hex(v) for a,v in fingerprints.items()},
  singleton_in_bss=True,dynamic_ivar_offsets_required=True,android_device_tested=False)

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('library',type=Path);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
 result=verify(a.library);a.out.write_text(json.dumps(result,indent=2)+'\n');print('Native layout verification PASS')
