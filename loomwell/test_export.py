"""Integration smoke tests against the real PhotoCraft engine; standard library only."""
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

import export as workflow


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def png_image(path, width=120, height=60):
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind+data))
    rows = b''.join(b'\0' + bytes((184, 110, 77))*width for _ in range(height))
    path.write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
                     + chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b''))


def raster_data(path):
    """Compare the actual filtered pixel stream, independent of PNG compression/metadata."""
    data = path.read_bytes()
    position, pixels, header = 8, b'', None
    while position < len(data):
        size = struct.unpack('>I', data[position:position+4])[0]
        kind = data[position+4:position+8]
        payload = data[position+8:position+8+size]
        if kind == b'IHDR':
            header = payload
        if kind == b'IDAT':
            pixels += payload
        position += size+12
    return header, zlib.decompress(pixels)


class ContentTests(unittest.TestCase):
    def test_shared_string_content(self):
        content = workflow.validate_content(workflow.PACK/'content.example.json')
        self.assertEqual(content['headline'], ['Evaluate the hard cases.'])
        self.assertLessEqual(len(content['subheadline']), 2)

    def test_long_copy_and_unknown_fields_fail(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/'copy.json'
            for value in ({'headline': 'x'*29}, {'extra': 'unsupported'}, {'footer': ''}):
                path.write_text(json.dumps(value))
                with self.assertRaises(ValueError):
                    workflow.validate_content(path)


class EngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.cli = workflow.resolve_cli()
        except ValueError as error:
            raise unittest.SkipTest(str(error))
        cls.temporary = tempfile.TemporaryDirectory(prefix='loomwell-photocraft-test-')
        cls.root = Path(cls.temporary.name)
        cls.output = cls.root/'delivery'
        cls.execute('all', cls.output)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    @classmethod
    def execute(cls, template, output, *options, check=True):
        return subprocess.run([sys.executable, str(workflow.PACK/'export.py'), 'export', template,
                               '--output', str(output), '--cli', str(cls.cli), *map(str, options)],
                              check=check, text=True, capture_output=True, timeout=180)

    def test_native_sizes_layers_files_and_pixel_roundtrip(self):
        manifest = json.loads((self.output/'manifest.json').read_text())
        self.assertEqual(len(manifest['files']), 13)
        for name, metadata in workflow.load_json(workflow.PACK/'pack.json')['templates'].items():
            native = self.output/(name+'.pcraft')
            info = json.loads(workflow.run(self.cli, 'info', native, '--compact'))
            self.assertEqual((info['width'], info['height']), (metadata['width'], metadata['height']))
            self.assertGreater(len(info['layers']), 30)
            self.assertTrue(any(layer['name'] == 'Copy / headline 1' and layer['kind'] == 'Type'
                                for layer in info['layers']))
            for extension in ('.png', '.webp'):
                self.assertEqual(workflow.image_dimensions(self.cli, self.output/(name+extension)),
                                 (metadata['width'], metadata['height']))
            reopened = self.root/(name+'-reopened.pcraft')
            workflow.run(self.cli, 'run', native, '--out', reopened)
            roundtrip = self.root/(name+'-roundtrip.png')
            workflow.run(self.cli, 'convert', reopened, roundtrip, allow_flatten=True)
            self.assertEqual(raster_data(self.output/(name+'.png')), raster_data(roundtrip))
        for name, details in manifest['files'].items():
            self.assertEqual(digest(self.output/name), details['sha256'])
            self.assertEqual((self.output/name).stat().st_size, details['bytes'])

    def test_importable_palette(self):
        output = workflow.run(self.cli, 'run', '--new', '{"width":1,"height":1}',
                              '--cmd', 'swatches.import', '--params', json.dumps({
                                  'path': str(self.output/'loomwell.aco'), 'mode': 'replace', 'group': 'Loomwell'}),
                              '--cmd', 'swatches.list')
        replies = [json.loads(line) for line in output.splitlines() if line.strip()]
        serialized = json.dumps(replies[-1]).lower()
        for key, color in workflow.load_json(workflow.PACK/'brand.json').items():
            self.assertIn(color, serialized)
            self.assertIn('loomwell '+key, serialized)

    def test_native_copy_edit_survives_save_and_changes_pixels(self):
        edited = self.root/'edited.pcraft'
        workflow.run(self.cli, 'run', self.output/'social.pcraft', '--cmd', 'layer.select',
                     '--params', '{"name":"Copy / headline 1"}', '--cmd', 'type.edit',
                     '--params', '{"text":"A focused pilot."}', '--out', edited)
        details = workflow.run(self.cli, 'run', edited, '--cmd', 'layer.select',
                               '--params', '{"name":"Copy / headline 1"}', '--cmd', 'type.info')
        self.assertIn('A focused pilot.', details)
        rendered = self.root/'edited.png'
        workflow.run(self.cli, 'convert', edited, rendered, allow_flatten=True)
        self.assertNotEqual(raster_data(rendered), raster_data(self.output/'social.png'))

    def test_preparation_actions_preserve_aspect_and_original(self):
        originals = self.root/'originals'
        originals.mkdir()
        source = originals/'synthetic.png'
        png_image(source)
        before = digest(source)
        for preset, width in (('half-resolution', 60), ('website-width-1600', 1600),
                              ('social-width-1200', 1200), ('square-width-1080', 1080)):
            output = self.root/preset
            subprocess.run([str(self.cli), 'batch', '--actions',
                            str(workflow.PACK/'presets'/(preset+'.actions.json')),
                            '--in', str(originals), '--out', str(output), '--format', 'png'],
                           check=True, text=True, capture_output=True, timeout=180)
            self.assertEqual(workflow.image_dimensions(self.cli, output/'synthetic.png'), (width, width//2))
            self.assertEqual(digest(source), before)

    def test_input_preservation_aspect_fit_and_collision(self):
        source = self.root/'approved.png'
        png_image(source)
        before = digest(source)
        output = self.root/'with-image'
        self.execute('social', output, '--input', source)
        self.assertEqual(before, digest(source))
        info = json.loads(workflow.run(self.cli, 'info', output/'social.pcraft', '--compact'))
        objects = [layer for layer in info['layers'] if layer['kind'] == 'Smart Object']
        self.assertEqual(len(objects), 1)
        x, y, width, height = objects[0]['bounds']
        self.assertAlmostEqual(width/height, 2, delta=.03)
        self.assertGreaterEqual(x, 849)
        self.assertGreaterEqual(y, 135)
        self.assertLessEqual(width, 287)
        self.assertLessEqual(height, 287)
        collision = output/'social.png'
        original = digest(collision)
        rejected = self.execute('social', output, '--input', collision, check=False)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn('overwrite', rejected.stderr)
        self.assertEqual(original, digest(collision))

    def test_rendered_copy_overflow_preserves_existing_delivery(self):
        path = self.root/'too-wide.json'
        path.write_text(json.dumps({'headline': 'W'*28}))
        original = digest(self.output/'social.pcraft')
        rejected = self.execute('social', self.output, '--content', path, check=False)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn('Text exceeds', rejected.stderr)
        self.assertEqual(original, digest(self.output/'social.pcraft'))


if __name__ == '__main__':
    unittest.main()
