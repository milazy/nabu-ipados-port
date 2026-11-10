#!/usr/bin/env python3
"""Prepare a verified, NON-INSTALLED eight-core ADT + boot-menu candidate.

The nabu 6 GiB device currently reaches SpringBoard userspace but boots with
one core because the installed ADT only publishes cpu0.  The reference nabu
source records eight MPIDR affinities 0x000..0x700 and PSCI SMC. This builds
an isolated candidate, preserving every non-CPU ADT property byte-for-byte.
It does not assume that correcting SMP is sufficient for a working GUI.
"""
from pathlib import Path
import hashlib,struct,sys,json,copy,tomllib

ROOT=Path(__file__).resolve().parents[2]
LIB=ROOT/'UniXNU-core/scripts'
sys.path.insert(0,str(LIB))
from unixnu.devicetree import node

SOURCE=ROOT/'build-artifacts/nabu-memory-ui-20261110/kernel-memory-ui.macho.adt'
MENU=ROOT/'build-artifacts/nabu-iomfb-modes-20261110/unixnu.iomfb-modes.toml'
KERNEL=ROOT/'build-artifacts/nabu-iomfb-modes-20261110/kernel-iomfb-compat.macho'
OUT=ROOT/'build-artifacts/nabu-smp-integrated-host-20261110'
# The owner-bound mode candidate has a different filename than the first
# IOMFB candidate. Select only by the verified SHA when the alias differs.
KERNEL_ALT=ROOT/'build-artifacts/nabu-iomfb-modes-20261110/kernel-iomfb-modes.macho'
SOURCE_SHA='0b6e519bf5b187fe5c311639f4b121a91dce820e25aaeba29a0525fd0d443b69'
MENU_SHA='7387bc2b95b876bb715107a5427728cd1f2115d06af3155aa7f20da5606278bb'
KERNEL_SHA='7291773563faf2791ca4e874117b9c517437791f0d8efe98cb3838a16839b60d'
def sha(b):return hashlib.sha256(b).hexdigest()
def need(ok,msg):
 if not ok:raise RuntimeError('PREP STOP: '+msg)
def read(data,pos=0,depth=0):
 need(depth<48 and pos+8<=len(data),'ADT node header')
 nprops,nchildren=struct.unpack_from('<II',data,pos);pos+=8
 need(nprops<512 and nchildren<128,'ADT node count')
 props=[]
 for _ in range(nprops):
  need(pos+36<=len(data),'ADT property header')
  raw,n=struct.unpack_from('<32sI',data,pos);pos+=36
  key=raw.split(b'\0',1)[0].decode('ascii')
  need(bool(key) and n<=len(data)-pos,'ADT property value')
  props.append((key,data[pos:pos+n]));pos+=(n+3)&~3
 need(bool(props) and props[0][0]=='name','ADT node name')
 name=props[0][1].rstrip(b'\0').decode('ascii')
 children=[]
 for _ in range(nchildren):
  child,pos=read(data,pos,depth+1);children.append(child)
 return {'name':name,'props':props[1:],'children':children},pos
def encode(t):return node(t['name'],t['props'],[encode(x) for x in t['children']])
def find(t,name):
 xs=[x for x in t['children'] if x['name']==name]
 need(len(xs)==1,'Expected unique node '+name)
 return xs[0]
def root_properties_without_cpu(t):
 return [(name,dict(n['props'])) for name,n in [(x['name'],x) for x in t['children']] if name not in ('cpus','psci')]

def main():
 need(not OUT.exists(),'Candidate directory exists; no overwrite')
 source=SOURCE.read_bytes();need(sha(source)==SOURCE_SHA,'Source ADT differs from live verified sidecar')
 tree,end=read(source);need(end==len(source) and encode(tree)==source,'Source ADT roundtrip failed')
 need(tree['name']=='device-tree','Unexpected ADT root')
 cpus=find(tree,'cpus')
 need(len(cpus['children'])==1 and cpus['children'][0]['name']=='cpu0','Expected cpu0-only source')
 cpu0=cpus['children'][0]
 origprops=dict(cpu0['props'])
 need(origprops.get('reg')==struct.pack('<I',0) and origprops.get('device_type')==b'cpu\0','CPU0 identification mismatch')
 need(origprops.get('state')==b'running\0','Unexpected CPU0 state')
 need('psci' not in [x['name'] for x in tree['children']],'PSCI already present')
 io=find(tree,'arm-io');gic=find(io,'intc')
 gp=dict(gic['props'])
 need(gp.get('compatible')==b'arm,gic-v3\0','GIC v3 contract changed')
 need(gp.get('redistributor-stride')==struct.pack('<Q',0x20000),'GIC redistributor stride mismatch')
 regs=gp.get('reg',b'')
 need(len(regs)==32,'GIC range tuple malformed')
 need(struct.unpack('<QQQQ',regs)[3]>=8*0x20000,'GICR range too short for eight cores')
 before=encode(tree)
 for i in range(1,8):
  fresh=copy.deepcopy(cpu0)
  fresh['name']=f'cpu{i}'
  fresh['props']=[(k,struct.pack('<I',i<<8) if k=='reg' else b'stopped\0' if k=='state' else v) for k,v in fresh['props']]
  cpus['children'].append(fresh)
 tree['children'].append({'name':'psci','props':[('compatible',b'arm,psci-0.2\0'),('method',b'smc\0')],'children':[]})
 output=encode(tree)
 rebuilt,end=read(output)
 need(end==len(output) and encode(rebuilt)==output,'Mutated ADT roundtrip failed')
 need(root_properties_without_cpu(tree)==root_properties_without_cpu(read(source)[0]),'Non CPU/PSCI properties drifted')
 c=find(rebuilt,'cpus')
 need(len(c['children'])==8,'CPU topology count mismatch')
 for i,item in enumerate(c['children']):
  props=dict(item['props'])
  need(item['name']==f'cpu{i}' and props['reg']==struct.pack('<I',i<<8),'MPIDR mismatch')
  need(props['device_type']==b'cpu\0','CPU node type')
  need(props['state']==(b'running\0' if i==0 else b'stopped\0'),'CPU initial state')
 need(dict(find(rebuilt,'psci')['props'])['method']==b'smc\0','PSCI conduit mismatch')
 before_props=root_properties_without_cpu(read(before)[0])
 after_props=root_properties_without_cpu(rebuilt)
 need(before_props==after_props,'Protected ADT property change')
 txt=MENU.read_text(encoding='utf-8');need(sha(MENU.read_bytes())==MENU_SHA,'Installed-menu baseline mismatch')
 menu=tomllib.loads(txt)
 need(menu['boot']['default']=='xnu-existing-ui-policy','Default menu changed')
 entries=[x for x in menu['entry'] if x['id']=='xnu-existing-ui-policy'];need(len(entries)==1,'Target entry missing')
 args=entries[0]['args'];tokens=args.split()
 for flag in ('cpus=8','armcpu-self-ipi=1','nabu-iomfb-compat=1','sheng-gpu-addon=1','nabu-gpu-scanout=1'):
  need(tokens.count(flag)==1,'Missing baseline flag '+flag)
 need(not any(x.startswith('sheng-smp=') for x in tokens),'SMP already enabled')
 need(len((args+' sheng-smp=1').encode('ascii'))<1024,'Boot arguments too long')
 old='args = "'+args+'"'
 need(txt.count(old)==1,'Menu args ambiguity')
 newtxt=txt.replace(old,'args = "'+args+' sheng-smp=1"',1)
 oldtitle='iPadOS 17.7 IOMFB MODES + METAL (UNVERIFIED)'
 need(txt.count(oldtitle)==1,'Old title drift')
 newtxt=newtxt.replace(oldtitle,'iPadOS 17.7 EIGHTCORE + IOMFB + METAL (UNVERIFIED)',1)
 parsed=tomllib.loads(newtxt)
 target=next(x for x in parsed['entry'] if x['id']=='xnu-existing-ui-policy')
 need(target['args'].split().count('sheng-smp=1')==1,'SMP bootarg missing')
 backupentry=next(x for x in parsed['entry'] if x['id']=='xnu-crypto384')
 need(backupentry['path']!=target['path'],'Fallback path must be independent')
 kpath=KERNEL if KERNEL.exists() and sha(KERNEL.read_bytes())==KERNEL_SHA else KERNEL_ALT
 need(kpath.exists() and sha(kpath.read_bytes())==KERNEL_SHA,'Verified kernel with ArmCpu not found')
 need(b'sheng-smp' in kpath.read_bytes(),'Compiled ArmCpu does not expose SMP feature')
 OUT.mkdir(parents=True,exist_ok=False)
 (OUT/'kernel-eightcore.adt').write_bytes(output)
 (OUT/'unixnu.eightcore.toml').write_text(newtxt,encoding='utf-8',newline='\n')
 safe=newtxt.replace('default = "xnu-existing-ui-policy"','default = "xnu-crypto384"',1)
 need(tomllib.loads(safe)['boot']['default']=='xnu-crypto384','Fallback menu invalid')
 (OUT/'unixnu.eightcore-safe.toml').write_text(safe,encoding='utf-8',newline='\n')
 report={'status':'EIGHTCORE_ADT_MENU_HOST_PREP_PASS_NOT_FLASHED','base_adt_sha256':SOURCE_SHA,
  'new_adt_sha256':sha(output),'base_menu_sha256':MENU_SHA,'new_menu_sha256':sha(newtxt.encode()),
  'kernel_sha256':KERNEL_SHA,'kernel_file':str(kpath),'cpu_affinities':[hex(i<<8) for i in range(8)],
  'psci_method':'smc','psci_node_added':True,'gicr_bytes':struct.unpack('<QQQQ',regs)[3],
  'protected_adt_properties_unchanged':True,'ios_ui_boot_verified':False,'device_modified':False}
 (OUT/'preflight.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2))
if __name__=='__main__':main()
