#!/usr/bin/env python3
"""Reproduce Pie sepolicy_neverallows m4/checkpolicy assembly outside Android.
Uses source-selected non-Treble Samsung/Qcom/Lineage policy; not the platform's
split/CIL/image build and does not replace m sepolicy_tests on a full checkout.
"""
from pathlib import Path
import subprocess,json,glob,argparse,shutil,hashlib
root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--android-tree',type=Path)
parser.add_argument('--m4')
parser.add_argument('--checkpolicy')
parser.add_argument('--checkfc')
args=parser.parse_args()
sp=root/'sources/platform-sepolicy'; qp=root/'sources/sepolicy-legacy'; lp=root/'sources/lineage-sepolicy'; ap=root/'templates/device/a7lte/sepolicy'
if args.android_tree:
    tree=args.android_tree.resolve()
    sp=tree/'system/sepolicy'; qp=tree/'device/qcom/sepolicy-legacy'; lp=tree/'device/lineage/sepolicy'; ap=tree/'device/samsung/a7lte/sepolicy'
for p in [sp/'public/te_macros',qp/'sepolicy.mk',lp/'common/public/attributes',ap/'file_contexts']:
    if not p.is_file(): parser.error(f'policy source missing: {p}; restore pinned sources or pass --android-tree')
def tool(name,override):
    result=override or (str(root/'host/usr/bin'/name) if (root/'host/usr/bin'/name).is_file() else shutil.which(name))
    if not result: parser.error(f'{name} not installed')
    return result
m4=tool('m4',args.m4); checkpolicy=tool('checkpolicy',args.checkpolicy)
(root/'logs').mkdir(exist_ok=True)
def label(p):
    try: return str(p.relative_to(root))
    except ValueError: return str(p)

dirs=[sp/'public',lp/'common/public',qp/'public',sp/'private',lp/'common/private',qp/'private',lp/'qcom/private',sp/'vendor',lp/'common/dynamic',lp/'common/vendor',qp/'common',qp/'ssg',qp/'msm8916',qp/'legacy-common',lp/'qcom/dynamic',lp/'qcom/vendor',ap]
patterns='security_classes initial_sids access_vectors global_macros neverallow_macros mls_macros mls_decl mls policy_capabilities te_macros attributes ioctl_defines ioctl_macros *.te roles_decl roles users initial_sid_contexts fs_use genfs_contexts port_contexts'.split()
files=[p for pattern in patterns for d in dirs for p in sorted(d.glob(pattern))]
cmd=[m4,'-Dmls_num_sens=1','-Dmls_num_cats=1024','-Dtarget_build_variant=userdebug','-Dtarget_with_dexpreopt=true','-Dtarget_arch=arm','-Dtarget_with_asan=false','-Dtarget_full_treble=false','-Dtarget_compatible_property=false','-Dtarget_has_legacy_camera_hal1=true','-Dtarget_needs_platform_text_relocations=false','-s',*map(str,files)]
m4_flags=cmd[1:12]
out=root/'out/policy-audit'; out.mkdir(parents=True,exist_ok=True)
with (out/'policy.conf').open('w') as fp, (root/'logs/sepolicy-audit-m4.log').open('w') as err:
 result=subprocess.run(cmd,stdout=fp,stderr=err)
meta={'m4_exit_code':result.returncode,'policy_directories':list(map(lambda p:label(p),dirs)),'policy_files':list(map(lambda p:label(p),files)),'definitions':cmd[1:12]}
if result.returncode==0:
 cmd=[checkpolicy,'-M','-c','30','-o',str(out/'sepolicy'),str(out/'policy.conf')]
 with (root/'logs/sepolicy-audit-checkpolicy.log').open('w') as log: result=subprocess.run(cmd,stdout=log,stderr=log)
 meta['checkpolicy_command']=cmd;meta['checkpolicy_exit_code']=result.returncode
 meta['policy_sha256']=hashlib.sha256((out/'sepolicy').read_bytes()).hexdigest() if result.returncode==0 else None
if result.returncode==0:
 checkfc=args.checkfc or (str(root/'host/bin/checkfc') if (root/'host/bin/checkfc').is_file() else shutil.which('checkfc'))
 if checkfc:
  ctx=[p for d in dirs for p in sorted(d.glob('file_contexts'))]
  with (out/'file_contexts').open('w') as fp, (root/'logs/sepolicy-audit-context-m4.log').open('w') as err:
   result=subprocess.run([m4,*m4_flags,*map(str,ctx)],stdout=fp,stderr=err)
  meta['context_m4_exit_code']=result.returncode
  meta['context_files']=[label(p) for p in ctx]
  if result.returncode==0:
   for name,contexts in [('device',ap/'file_contexts'),('combined',out/'file_contexts')]:
    with (root/f'logs/sepolicy-audit-checkfc-{name}-portable.log').open('w') as log:
     result=subprocess.run([checkfc,str(out/'sepolicy'),str(contexts)],stdout=log,stderr=log)
    meta['checkfc_'+name+'_exit_code']=result.returncode
    if result.returncode: break
 else: meta['checkfc']='not installed; context validation not rerun'
(root/'logs/sepolicy-audit-build.json').write_text(json.dumps(meta,indent=2)+'\n')
print(json.dumps({k:v for k,v in meta.items() if k!='policy_files'},indent=2))
raise SystemExit(result.returncode)
