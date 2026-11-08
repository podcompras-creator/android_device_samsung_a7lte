#!/usr/bin/env python3
"""Read-only assessment of the selected Linux builder; never provisions a VM."""
import argparse,datetime,json,os,platform,shutil,subprocess,sys
from pathlib import Path

def read(path):
 try: return Path(path).read_text().strip()
 except OSError: return None

def assess(path,tree=None):
 path=path.resolve(strict=True); disk=shutil.disk_usage(path)
 cpu=os.cpu_count(); cpu_max=read('/sys/fs/cgroup/cpu.max')
 if cpu_max:
  quota,period=cpu_max.split()
  if quota!='max': cpu=min(cpu,int(quota)/int(period))
 meminfo={}
 for line in (read('/proc/meminfo') or '').splitlines():
  words=line.split()
  if len(words)>1 and words[1].isdigit(): meminfo[words[0].rstrip(':')]=int(words[1])*1024
 mem=meminfo.get('MemTotal',0); limit=read('/sys/fs/cgroup/memory.max')
 if limit and limit!='max': mem=min(mem,int(limit))
 swap=meminfo.get('SwapTotal',0); tools={n:shutil.which(n) for n in ['git','make','gcc','g++','python3','python2','java','javac','bison','flex','bc','m4','rsync','unzip','zip']}
 env={'checked_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'host':platform.platform(),'path':str(path),'disk_bytes':dict(zip(['total','used','free'],disk)),'cpu_available':cpu,'cpu_cgroup':cpu_max,'ram_bytes_limit':mem,'swap_bytes':swap,'tools':tools}
 env['sizing']={'minimum_free_bytes':200*1024**3,'recommended_free_bytes':300*1024**3,'disk_sufficient_for_full_sync_build':disk.free>=200*1024**3,'memory_and_swap_at_least_16GiB':mem+swap>=16*1024**3,'note':'Capacity thresholds are estimates, not a guarantee that a build will fit.'}
 if tree:
  tree=tree.resolve(); required=['build/envsetup.sh','build/soong/soong_ui.bash','bionic/Android.bp','frameworks/base/Android.bp','vendor/lineage/config/common_full_phone.mk']
  env['platform']={'path':str(tree),'required_files':{p:(tree/p).is_file() for p in required},'jdk8':(tree/'prebuilts/jdk/jdk8/linux-x86/bin/java').is_file()}
 java_version=None
 if tools['java']:
  q=subprocess.run([tools['java'],'-version'],text=True,capture_output=True)
  java_version=(q.stderr or q.stdout).splitlines()[0] if (q.stderr or q.stdout) else None
 env['java_version']=java_version
 env['missing_host_tools']=[n for n,path in tools.items() if not path]
 env['host_ready_for_sync']=env['sizing']['disk_sufficient_for_full_sync_build'] and bool(tools['git']) and sys.version_info>=(3,9)
 env['java8_available']=bool((tree and env['platform']['jdk8']) or (java_version and '1.8.' in java_version))
 env['host_ready_for_build']=env['host_ready_for_sync'] and env['sizing']['memory_and_swap_at_least_16GiB'] and not env['missing_host_tools'] and env['java8_available']
 env['full_builder_ready']=env['host_ready_for_build'] and bool(tree and all(env['platform']['required_files'].values()))
 return env

def main():
 p=argparse.ArgumentParser(description=__doc__); p.add_argument('--path',type=Path,default=Path.cwd()); p.add_argument('--android-tree',type=Path); p.add_argument('--output',type=Path); a=p.parse_args()
 try: r=assess(a.path,a.android_tree)
 except (OSError,ValueError) as e: p.exit(2,f'Cannot inspect builder: {e}\n')
 out=json.dumps(r,indent=2)+'\n'
 if a.output: a.output.write_text(out)
 print(out,end=''); return 0 if r['full_builder_ready'] else 78
if __name__=='__main__': raise SystemExit(main())
