"""Allow the two independent frontend fixes on nabu's four-patch desktop baseline."""
import argparse, hashlib, json
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--device',type=Path,required=True)
a=p.parse_args()
def replace(path,old,new):
    text=path.read_text(); assert text.count(old)==1, 'Source drift: '+str(path)
    path.write_text(text.replace(old,new,1))
plugin=a.device/'source-ci/nabu_metal_plugin_ci.py'
turnip=a.device/'source-ci/nabu_turnip_ci.py'
replace(plugin,
    "    if sum((fps_opt, async_fix, completion_fix)) > 1:\n        raise ValueError('Keep the async creation, FPS and completion-wait experiments separate')\n    if async_fix:\n        return ASYNC_PATCHES\n",
    "    if fps_opt and (async_fix or completion_fix):\n        raise ValueError('FPS changes are separate from frontend deadlock repairs')\n    if async_fix:\n        return ASYNC_PATCHES + ((COMPLETION_PATCH,) if completion_fix else ())\n")
replace(turnip,
    "    require(sum((args.fps_opt, args.async_fix, args.completion_fix)) <= 1,\n            'Keep the async creation, FPS and completion-wait experiments separate')\n",
    "    require(not args.fps_opt or not (args.async_fix or args.completion_fix),\n            'FPS changes are separate from frontend deadlock repairs')\n")
print('JOINT_FRONTEND_FIX_SOURCE_PREPARED; CoreImage experiment excluded; hardware unverified')
