#!/usr/bin/env python3
"""Compare nabu's two CRC-verified boot captures without flashing anything.

A successful UEFI handoff or a living SpringBoard is not evidence of a visible
desktop. Require a submitted and presented frame for that narrower proof.
"""
import argparse,json,re
from pathlib import Path

def last_match(text,pattern):
    matches=list(re.finditer(pattern,text,re.M))
    if not matches:return None
    return [int(n) for n in matches[-1].groups()]
def snapshot(path):
    text=Path(path).read_text(encoding="utf-8",errors="replace")
    swaps=last_match(text,r"NABU DISPLAY swaps accepted=(\d+) rejected=(\d+)")
    frames=last_match(text,r"NabuGPU: writer_scanout=\d+ ready=(\d+) pending=(\d+) offered=(\d+) done=(\d+) fallback=(\d+)")
    v=last_match(text,r"NABU DISPLAY vsync hz=\d+ armed=(\d+) sent=(\d+)")
    wg=last_match(text,r"NabuGPU: writer_probe=\d+ now_us=\d+ opens=(\d+) closes=(\d+) calls=(\d+)")
    ms=last_match(text,r"NabuGPU: writer_smp=\d+ req=(\d+) run=(\d+) conduit=(\d+) boot=[0-9a-f]+ ncpus=(\d+)")
    return dict(boot_log=str(Path(path)),mode_published="NABU DISPLAY iomfb-modes published" in text,
      mode_block_provided="NABU DISPLAY iomfb-mode block=0x40" in text,
      compat_selectors_executed=len(re.findall(r"NABU DISPLAY iomfb-compat selector=",text)),
      swaps_accepted=swaps[0] if swaps else None,swaps_rejected=swaps[1] if swaps else None,
      scanout_offered=frames[2] if frames else None,scanout_completed=frames[3] if frames else None,
      vsync_sent=v[1] if v else None,plugin_userclient_calls=wg[2] if wg else None,
      smp_active_cores=ms[3] if ms else None,
      springboard_alive=bool(re.search(r"NabuUI: sample=\d+ target=SpringBoard .*status=sample_ok",text)),
      backboardd_alive=bool(re.search(r"NabuUI: sample=\d+ target=backboardd .*status=sample_ok",text)),
      gpu_shader_selftest_errors=len(re.findall(r"writer_row=\d+ r=4[567] .*Compile\(NeedsInput",text)),
      visible_frame_proven=bool(swaps and swaps[0]>0 and frames and frames[2]>0 and frames[3]>0))
def main():
    p=argparse.ArgumentParser();p.add_argument("--baseline",type=Path,required=True);p.add_argument("--candidate",type=Path,required=True);p.add_argument("--out",type=Path,required=True)
    a=p.parse_args();base=snapshot(a.baseline);new=snapshot(a.candidate)
    result=dict(status="LIVE_UI_NOT_PROVEN",baseline=base,candidate=new,
      interpretation=[
        "IOMFB mode publication was reached" if new["mode_published"] else "IOMFB mode publication not confirmed",
        "Mode block 0x40 delivered" if new["mode_block_provided"] else "Mode block 0x40 not confirmed",
        "No display swaps or scanout offers" if new["swaps_accepted"]==0 and new["scanout_offered"]==0 else "Display swap path requires detailed review",
        "QuartzCore TileAttachments lines are OFFLINE plugin self-test output, not proof of live render cause",
        "USB absence after RAM boot does not establish complete iPadOS boot",
        "Do not flash another IOMFB-only patch without a mapped runtime rendering defect",
      ])
    if new["visible_frame_proven"]:result["status"]="FRAME_COUNTERS_NONZERO_SCREEN_UNVERIFIED"
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print("DIAGNOSIS",result["status"])
    for k in ("mode_published","mode_block_provided","swaps_accepted","scanout_offered","scanout_completed","vsync_sent","smp_active_cores","plugin_userclient_calls"):
        print(k,base.get(k),"->",new.get(k))
if __name__=="__main__":main()
