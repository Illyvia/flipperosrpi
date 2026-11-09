import hashlib,pathlib,runpy,tempfile,unittest
from unittest import mock
module=runpy.run_path(str(pathlib.Path(__file__).resolve().parents[1]/'scripts/prepare-release.py'))
class ReleasePackageTests(unittest.TestCase):
    def test_parts_reassemble_exactly_and_have_matching_checksums(self):
        package=module['package'];original=package.__globals__['CHUNK_BYTES'];package.__globals__['CHUNK_BYTES']=100
        try:
            with tempfile.TemporaryDirectory() as temp:
                root=pathlib.Path(temp);payload=bytes(range(256))*2
                for variant in ['hdmi','waveshare-7-e']:
                    folder=root/'input'/variant;folder.mkdir(parents=True)
                    image=folder/(variant+'.img.zst');image.write_bytes(payload)
                    image.with_suffix('.zst.sha256').write_text(hashlib.sha256(payload).hexdigest()+'  '+image.name)
                with mock.patch.object(module['subprocess'],'run'):
                    images=package(root/'input',root/'output')
                for image in images:
                    self.assertEqual(b''.join((root/'output'/p).read_bytes() for p in image['parts']),payload)
                for line in (root/'output/SHA256SUMS').read_text().splitlines():
                    expected,name=line.split()
                    if '.part' in name:self.assertEqual(hashlib.sha256((root/'output'/name).read_bytes()).hexdigest(),expected)
        finally:package.__globals__['CHUNK_BYTES']=original
