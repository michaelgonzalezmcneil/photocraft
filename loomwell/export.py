#!/usr/bin/env python3
"""Render Loomwell's editable PhotoCraft website and social templates.

Standard-library Python only. Uses the actual PhotoCraft command engine; no
third-party application or cloud service is involved.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import textwrap

PACK = Path(__file__).resolve().parent
REPO = PACK.parent


def load_json(path):
    with Path(path).open(encoding='utf-8') as stream:
        return json.load(stream)


def resolve_cli(explicit=None):
    if explicit:
        path = Path(explicit).expanduser().resolve()
        if not path.is_file():
            raise ValueError('PhotoCraft CLI does not exist: ' + str(path))
        return path
    candidates = [REPO / 'target' / 'release' / 'photocraft-cli']
    if os.environ.get('PHOTOCRAFT_CLI'):
        candidates.insert(0, Path(os.environ['PHOTOCRAFT_CLI']))
    # Atlas keeps maintained per-app build targets outside each source checkout.
    candidates.append(REPO.parent.parent / 'build' / 'photocraft' / 'release' / 'photocraft-cli')
    found = shutil.which('photocraft-cli')
    if found:
        candidates.append(Path(found))
    for path in candidates:
        if path.is_file():
            return path.resolve()
    raise ValueError('Build photocraft-cli or pass --cli /absolute/path/to/photocraft-cli')


def run(cli, *args, allow_flatten=False):
    env = os.environ.copy()
    # Do not import a person's installed app preferences or alter their profile.
    env['PHOTOCRAFT_CONFIG_DIR'] = str(PACK / 'exports' / '.profile')
    result = subprocess.run([str(cli), *map(str, args)], check=True, capture_output=True,
                            text=True, env=env, timeout=180)
    warnings = [line for line in result.stderr.splitlines() if line.strip()]
    unexpected = [line for line in warnings if not (allow_flatten and
                  ((line.startswith('warning: ') and 'layer(s) flattened; layers, masks and blend modes are not kept' in line)
                   or line == 'warning: resolution (DPI) not supported; it will be dropped'))]
    if unexpected:
        raise ValueError('PhotoCraft reported a warning: ' + '\n'.join(unexpected))
    return result.stdout


def validate_content(path):
    content = load_json(PACK / 'content.json')
    if path:
        updates = load_json(path)
        if not isinstance(updates, dict) or set(updates) - set(content):
            raise ValueError('Content must be an object using only keys from content.json')
        content.update(updates)
    for key in ('headline', 'subheadline'):
        value = content[key]
        maximum = 28 if key == 'headline' else 45
        if isinstance(value, str):
            value = [part for line in value.splitlines()
                     for part in textwrap.wrap(line, width=maximum, break_long_words=False,
                                               break_on_hyphens=False)]
            content[key] = value
        if (not isinstance(value, list) or not 1 <= len(value) <= 2 or
                any(not isinstance(line, str) or not line or len(line) > maximum or '\n' in line for line in value)):
            raise ValueError(f'{key} must contain one or two nonempty lines of at most {maximum} characters')
    for key in ('eyebrow', 'button', 'footer'):
        value = content[key]
        maximum = 26 if key == 'button' else 44
        if not isinstance(value, str) or not value or len(value) > maximum or '\n' in value:
            raise ValueError(f'{key} must be a nonempty line of at most {maximum} characters')
    return content


class Document:
    def __init__(self, colors):
        self.colors = colors
        self.steps = []

    def add(self, command, **params):
        self.steps.append({'command': command, 'params': params})

    def rect(self, name, x, y, width, height, color, radius=0, stroke=None):
        self.add('shape.create', kind='roundedRect' if radius else 'rect',
                 rect=[x, y, width, height], radii=radius, fill=color, stroke=stroke, name=name)

    def text(self, name, x, y, text, size, color, display=False):
        # Inter is supplied by PhotoCraft; it keeps templates portable without font copies.
        self.add('type.create', name=name, x=x, y=y, text=text, size=size,
                 font='Inter', color=color)
        if display:
            self.add('type.setStyle', weight=500, tracking=-35)

    def weave(self, cx, cy, radius):
        count = 7
        pitch, width = radius * 2 / 7.8, radius * 2 / 7.8 * .64
        points = [(index - 3) * pitch for index in range(count)]
        for i, x in enumerate(points):
            extent = math.sqrt(radius * radius - x * x)
            self.rect(f'Artwork / warp {i+1}', cx+x-width/2, cy-extent, width, extent*2,
                      self.colors['forest'], width*.42)
        for j, y in enumerate(points):
            extent = math.sqrt(radius * radius - y * y)
            color = self.colors['terracotta'] if j == 3 else self.colors['sage']
            self.rect(f'Artwork / weft {j+1}', cx-extent, cy+y-width/2, extent*2, width,
                      color, width*.42)
        for i, x in enumerate(points):
            for j, y in enumerate(points):
                if (i+j) % 2 == 0 and x*x+y*y < (radius-width/2)**2:
                    self.rect(f'Artwork / overpass {i+1}-{j+1}', cx+x-width/2,
                              cy+y-width/2-1, width, width+2, self.colors['forest'])


def image_dimensions(cli, path):
    info = json.loads(run(cli, 'info', path, '--compact'))
    width, height = info.get('width'), info.get('height')
    if not isinstance(width, int) or not isinstance(height, int) or not width or not height:
        raise ValueError('Cannot read the input image dimensions')
    return width, height


def recipe(name, metadata, colors, content, cli, image=None):
    width, height = metadata['width'], metadata['height']
    art = Document(colors)
    forest, paper, sage, clay = (colors[k] for k in ('forest', 'paper', 'sage', 'terracotta'))
    for key, value in colors.items():
        art.add('swatches.add', color=value, name='Loomwell ' + key.title(), group='Loomwell')
    art.rect('Background / paper', 0, 0, width, height, paper)
    top = 120 if name == 'website' else 0
    if top:
        art.rect('Header / forest', 0, 0, width, top, forest)
    square = name == 'square'
    pad = 72 if name == 'website' else 54
    brand_y = 83 if name == 'website' else 82 if square else 66
    brand_size = 48 if name == 'website' or square else 38
    art.text('Brand / wordmark', pad, brand_y, 'loomwell', brand_size, paper if top else forest, True)
    if name == 'website':
        eyebrow_y, headline_y, headline_size, line_step = 205, 305, 72, 90
        body_y, body_size, body_step = 505, 25, 39
        button_y, footer_y = 635, 850
    elif name == 'social':
        eyebrow_y, headline_y, headline_size, line_step = 142, 244, 57, 73
        body_y, body_size, body_step = 400, 21, 32
        button_y, footer_y = None, 584
    else:
        eyebrow_y, headline_y, headline_size, line_step = 162, 262, 66, 84
        body_y, body_size, body_step = 427, 24, 36
        button_y, footer_y = None, 1023
    art.text('Copy / eyebrow', pad, eyebrow_y, content['eyebrow'], 13, clay)
    for i, text in enumerate(content['headline']):
        art.text(f'Copy / headline {i+1}', pad-3, headline_y+i*line_step, text,
                 headline_size, forest, True)
    for i, text in enumerate(content['subheadline']):
        art.text(f'Copy / description {i+1}', pad, body_y+i*body_step, text, body_size, '#56645a')
    if button_y:
        art.rect('Website / button background', pad, button_y, 300, 62, forest, 5)
        art.text('Website / button label', pad+23, button_y+40, content['button'], 20, paper)
    x, y, w, h = metadata['image_slot']
    if image:
        iw, ih = image_dimensions(cli, image)
        art.add('file.placeEmbedded', path=str(image), fit=False, smartObject=True,
                scale=min(w/iw, h/ih)*100, center=[x+w/2, y+h/2])
    else:
        art.weave(x+w/2, y+h/2, min(w, h)*.46)
    # Safe replacement bounds stay in the recipe metadata and named artwork layers.
    rule_y = height-92
    art.rect('Footer / rule', pad, rule_y, width-pad*2, 1, '#c5cebe')
    art.text('Footer / status', pad, footer_y, content['footer'], 12, '#56645a')
    label = f'{width} × {height}'
    art.text('Footer / dimensions', width-pad-(140 if square else 150), footer_y, label, 12, '#56645a')
    return art.steps


def export_template(cli, name, metadata, output, content, colors, image):
    native = output / (name + '.pcraft')
    png = output / (name + '.png')
    webp = output / (name + '.webp')
    if image and image.resolve() in {native.resolve(), png.resolve(), webp.resolve()}:
        raise ValueError('An output would overwrite the input image')
    steps = recipe(name, metadata, colors, content, cli, image)
    args = ['run', '--new', json.dumps({'width': metadata['width'], 'height': metadata['height'],
                                     'background': 'transparent'})]
    for step in steps:
        args.extend(['--cmd', step['command'], '--params', json.dumps(step['params'], separators=(',', ':'))])
    args.extend(['--out', str(native)])
    stdout = run(cli, *args)
    replies = [json.loads(line) for line in stdout.splitlines() if line.strip()]
    warnings = [item for reply in replies for item in reply.get('warnings', [])]
    if warnings:
        raise ValueError('Template render warning: ' + '; '.join(map(str, warnings)))
    info = json.loads(run(cli, 'info', native, '--compact'))
    copy_right = metadata['image_slot'][0]-42 if name != 'square' else metadata['width']-54
    for layer in info.get('layers', []):
        bounds = layer.get('bounds')
        if layer.get('kind') != 'Type' or not bounds:
            continue
        x, y, width, height = bounds
        if x < 0 or y < 0 or x+width > metadata['width'] or y+height > metadata['height']:
            raise ValueError('Text exceeds canvas: ' + layer.get('name', 'unnamed layer'))
        if layer.get('name', '').startswith('Copy /') and x+width > copy_right:
            raise ValueError('Text exceeds the copy safe area: ' + layer['name'])
        if layer.get('name') == 'Website / button label' and x+width > 349:
            raise ValueError('Text exceeds the button safe area')
    run(cli, 'convert', native, png, allow_flatten=True)
    run(cli, 'convert', native, webp, allow_flatten=True)  # Default WebP is lossless.
    data = png.read_bytes()
    if data[:8] != b'\x89PNG\r\n\x1a\n' or struct.unpack('>II', data[16:24]) != (metadata['width'], metadata['height']):
        raise ValueError('Unexpected rendered image dimensions')
    (output / (name + '.recipe.json')).write_text(json.dumps({
        'template': name, 'canvas': [metadata['width'], metadata['height']],
        'safe_image_slot': metadata['image_slot'], 'commands': steps,
    }, indent=2) + '\n')
    return {'canvas': [metadata['width'], metadata['height']], 'image_slot': metadata['image_slot'],
            'layer_count': len(info.get('layers', [])),
            'files': {path.name: {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                                 'bytes': path.stat().st_size,
                                 **({'width': metadata['width'], 'height': metadata['height']}
                                    if path.suffix != '.json' else {})}
                      for path in (native, png, webp, output/(name+'.recipe.json'))}}


def export_palette(cli, output, colors):
    args = ['run', '--new', '{"width":1,"height":1,"background":"transparent"}']
    for name, color in colors.items():
        args += ['--cmd', 'swatches.add', '--params', json.dumps({
            'color': color, 'name': 'Loomwell ' + name.title(), 'group': 'Loomwell'})]
    args += ['--cmd', 'swatches.export', '--params', json.dumps({
        'format': 'aco', 'group': 'Loomwell', 'path': str(output/'loomwell.aco')})]
    run(cli, *args)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest='action', required=True)
    actions.add_parser('list')
    export = actions.add_parser('export')
    export.add_argument('template', choices=['website', 'social', 'square', 'all'])
    export.add_argument('--output', type=Path, default=PACK / 'exports')
    export.add_argument('--cli')
    export.add_argument('--content', type=Path)
    export.add_argument('--input', type=Path, help='Optional replacement image, fitted without stretching')
    args = parser.parse_args()
    pack = load_json(PACK / 'pack.json')
    if args.action == 'list':
        for name, item in pack['templates'].items():
            print(f'{name:8} {item["width"]}x{item["height"]} -> editable .pcraft, PNG, lossless WebP')
        return
    colors = load_json(PACK / 'brand.json')
    if set(colors) != {'forest', 'paper', 'sage', 'terracotta'} or any(
            not isinstance(v, str) or len(v) != 7 or not v.startswith('#') or
            any(c not in '0123456789abcdefABCDEF' for c in v[1:]) for v in colors.values()):
        raise ValueError('brand.json must contain four named #rrggbb colors')
    content = validate_content(args.content)
    cli = resolve_cli(args.cli)
    image = args.input.expanduser().resolve() if args.input else None
    if image and not image.is_file():
        raise ValueError('Input image does not exist')
    output = args.output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    selected = pack['templates'] if args.template == 'all' else {args.template: pack['templates'][args.template]}
    if image and any(image == (output / (name+ext)).resolve()
                     for name in selected for ext in ('.pcraft', '.png', '.webp')):
        raise ValueError('An output would overwrite the input image')
    # Validate and render a whole delivery before replacing existing output files.
    with tempfile.TemporaryDirectory(prefix='.loomwell-', dir=output) as temporary:
        staging = Path(temporary)
        records = {name: export_template(cli, name, item, staging, content, colors, image)
                   for name, item in selected.items()}
        export_palette(cli, staging, colors)
        version = run(cli, '--version').strip()
        manifest = {'tool': 'photocraft', 'renderer': version, 'brand': colors,
                'content': content, 'templates': records,
                'files': {name: details for record in records.values()
                          for name, details in record['files'].items()},
                'raster_export_notes': ['PNG/WebP flatten layers; .pcraft preserves editable layers.',
                                        'WebP omits print-resolution metadata. WebP output is lossless.'],
                'publication_status': 'Original brand template; no customer data or performance claim'}
        palette = staging/'loomwell.aco'
        manifest['files'][palette.name] = {'sha256': hashlib.sha256(palette.read_bytes()).hexdigest(),
                                       'bytes': palette.stat().st_size}
        (staging/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
        for path in staging.iterdir():
            path.replace(output/path.name)
    for name in records:
        print(f'{name}: exported .pcraft + PNG + lossless WebP to {output}')


if __name__ == '__main__':
    try:
        main()
    except subprocess.CalledProcessError as exc:
        print((exc.stderr or '').strip() or str(exc), file=sys.stderr)
        raise SystemExit(1)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
