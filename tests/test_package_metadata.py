import pathlib,runpy,unittest
module=runpy.run_path(str(pathlib.Path(__file__).resolve().parents[1]/'port/prepare-board-inputs.py'))
class KernelDependencyTests(unittest.TestCase):
    def test_kernel_need_not_be_first_dependency(self):
        metadata='Package: linux-image-rpi-v8\nDepends: linux-base-rpi-v8 (= 1:6.18.60-1+rpt1), linux-image-6.18.60+rpt-rpi-v8 (= 1:6.18.60-1+rpt1)\n'
        self.assertEqual(module['kernel_dependency'](metadata),'linux-image-6.18.60+rpt-rpi-v8')
    def test_missing_versioned_image_is_rejected(self):
        with self.assertRaises(ValueError):module['kernel_dependency']('Depends: linux-base-rpi-v8\n')
