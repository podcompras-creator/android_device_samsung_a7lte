import importlib.util,tempfile,unittest
from pathlib import Path
p=Path(__file__).resolve().parents[1]/'scripts/extract-stock.py'
s=importlib.util.spec_from_file_location('props',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
BASE='ro.product.model=SM-A700FD\nro.product.manufacturer=samsung\nro.product.device=a7lte\nro.build.PDA=A700FDXXS1CSB1\nro.build.version.incremental=A700FDXXS1CSB1\n'
class Overrides(unittest.TestCase):
 def read(self,extra):
  with tempfile.TemporaryDirectory() as t:
   r=Path(t);(r/'build.prop').write_text(BASE+extra);events=[];v,h=m.properties(r,events);return v,h,events
 def test_samsung_dalvik_override(self):
  v,h,events=self.read('dalvik.vm.heapsize=256m\ndalvik.vm.heapsize=512m\n');self.assertEqual(v['dalvik.vm.heapsize'],'512m');self.assertEqual(len(events),1);self.assertEqual(len(h),64)
 def test_unrelated_read_only_override(self):
  v,_,e=self.read('ro.sf.lcd_density=320\nro.sf.lcd_density=480\n');self.assertEqual(v['ro.sf.lcd_density'],'480');self.assertEqual(e[0]['key'],'ro.sf.lcd_density')
 def test_identity_conflict_still_rejected(self):
  with self.assertRaisesRegex(ValueError,'conflicting identity property'):self.read('ro.product.model=OTHER\n')
 def test_pda_conflict_still_rejected(self):
  with self.assertRaisesRegex(ValueError,'conflicting identity property'):self.read('ro.build.PDA=OTHER\n')
if __name__=='__main__':unittest.main()
