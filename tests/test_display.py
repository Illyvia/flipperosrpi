import copy
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT/'port/board-files/usr/local/sbin/flipper-display'
loader = importlib.machinery.SourceFileLoader('flipper_display', str(SCRIPT))
spec = importlib.util.spec_from_loader(loader.name, loader)
display = importlib.util.module_from_spec(spec)
loader.exec_module(display)


class DisplayTests(unittest.TestCase):
    def preset(self, name):
        return display.read_config(display.PRESETS/(name+'.json'))

    def test_presets_and_rejected_input(self):
        for name in ['hdmi', 'waveshare-7-e']:
            self.assertEqual(display.validate(self.preset(name))['version'], 1)
        for field, value in [('tint', 'purple'), ('rotation', 45), ('scale', True),
                             ('connector', 'HDMI-A-1; exec anything')]:
            c = self.preset('waveshare-7-e'); c[field] = value
            with self.assertRaises(ValueError): display.validate(c)
        c = self.preset('waveshare-7-e'); c['panel']['overlay'] = '../../escape'
        with self.assertRaises(ValueError): display.validate(c)
        c = self.preset('hdmi'); c['unknown'] = True
        with self.assertRaises(ValueError): display.validate(c)

    def test_firmware_transition_preserves_unrelated_settings(self):
        original = 'arm_64bit=1\nkernel=u-boot.bin\ndtparam=audio=on\n'
        dsi = display.firmware_text(original, self.preset('waveshare-7-e'))
        self.assertIn('vc4-kms-dsi-waveshare-panel,8_0_inch', dsi)
        hdmi = display.firmware_text(dsi, self.preset('hdmi'))
        self.assertNotIn('waveshare-panel', hdmi)
        self.assertIn('dtparam=audio=on', hdmi)
        self.assertEqual(hdmi, display.firmware_text(hdmi, self.preset('hdmi')))

    def test_auto_output_and_scaling_use_the_requested_connector_type(self):
        outputs = [
            {'name': 'DSI-1', 'current_mode': {'width': 1280, 'height': 800}},
            {'name': 'HDMI-A-1', 'current_mode': {'width': 1920, 'height': 1080}},
            {'name': 'HDMI-A-2', 'current_mode': None, 'modes': []},
        ]
        hdmi = self.preset('hdmi')
        selected = display.select_output(hdmi, outputs)
        self.assertEqual(selected['name'], 'HDMI-A-1')
        self.assertEqual(display.output_plan(hdmi, selected)['scale'], 7)
        dsi = self.preset('waveshare-7-e')
        self.assertEqual(display.output_plan(dsi, outputs[0])['scale'], 5)
        dsi['rotation'] = 90
        self.assertEqual(display.output_plan(dsi, outputs[0])['scale'], 3)
        dsi['scale'] = 10
        with self.assertRaises(ValueError): display.output_plan(dsi, outputs[0])
        with self.assertRaises(ValueError): display.select_output(hdmi, outputs[:1])

    def test_hdmi_restores_original_dtb_without_mutating_during_planning(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); dt = root/'usr/lib/linux-image-test/broadcom'; dt.mkdir(parents=True)
            base = dt/'bcm2711-rpi-4-b.dtb'; base.write_bytes(b'old-dsi-tree')
            backup = base.with_name(base.name+'.without-flipper-dsi'); backup.write_bytes(b'original-tree')
            changes = display.kernel_plan(root, 'test', self.preset('hdmi'))
            self.assertEqual(changes, [(base, b'original-tree')])
            self.assertEqual(base.read_bytes(), b'old-dsi-tree')

    def test_dsi_passes_only_validated_overlay_parameters_to_dtmerge(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); dt = root/'usr/lib/linux-image-test/broadcom'; dt.mkdir(parents=True)
            base = dt/'bcm2711-rpi-4-b.dtb'; base.write_bytes(b'original-tree')
            overlays = dt.parent/'overlays'; overlays.mkdir()
            (overlays/'vc4-kms-dsi-waveshare-panel.dtbo').write_bytes(b'overlay')
            calls = []
            def merge(argv, **kw):
                calls.append(argv)
                Path(argv[2]).write_bytes(b'merged-tree')
            with patch.object(display.subprocess, 'run', side_effect=merge):
                changes = display.kernel_plan(root, 'test', self.preset('waveshare-7-e'))
            self.assertEqual(calls[0][-1], '8_0_inch')
            self.assertEqual(changes[-1], (base, b'merged-tree'))
            self.assertEqual(base.read_bytes(), b'original-tree')

    def test_installer_creates_generic_service_and_legacy_alias(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root/'etc').mkdir()
            (root/'etc/os-release').write_text('IMAGE_ID=flipperos-rpi4\n')
            subprocess.run([sys.executable, str(PROJECT/'port/install-display.py'), str(root),
                            '--profile', 'Minimal', '--no-kernel'], check=True, capture_output=True)
            units = root/'etc/systemd/system'
            self.assertEqual((units/'flipctl-dsi.service').readlink(), Path('flipctl-display.service'))
            self.assertTrue((units/'multi-user.target.wants/flipctl-display.service').is_symlink())
            self.assertFalse((units/'multi-user.target.wants/flipctl.service').exists())


if __name__ == '__main__': unittest.main()
