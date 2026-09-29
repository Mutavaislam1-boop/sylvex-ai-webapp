"""Validation and pixel operations for the isolated Pro Studio Edit workspace."""
import io
import math
import re

from PIL import Image, ImageOps

MODES = {'edit', 'retouch', 'resize', 'background', 'expand', 'upscale', 'lighting', 'camera', 'translate'}
MAX_CANVAS_PIXELS = 16_777_216


def number(value, minimum, maximum, default=None):
    if value is None and default is not None:
        value = default
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError('Укажите корректное числовое значение.')
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise ValueError(f'Значение должно быть от {minimum} до {maximum}.')
    return result


def dimensions(settings, max_edge=8192, max_pixels=MAX_CANVAS_PIXELS):
    width = int(number(settings.get('width'), 1, max_edge))
    height = int(number(settings.get('height'), 1, max_edge))
    if width * height > max_pixels:
        raise ValueError('Слишком большое изображение. Уменьшите размеры.')
    return width, height


def validate_options(opts):
    mode = str(opts.get('editWorkspaceMode') or 'edit').strip().lower()
    if mode not in MODES:
        raise ValueError('Неизвестный инструмент Edit.')
    if not str(opts.get('editWorkspaceSourceUrl') or '').strip():
        raise ValueError('Загрузите исходное изображение.')
    prompt = str(opts.get('editWorkspacePrompt') or '').strip()
    if len(prompt) > 8000:
        raise ValueError('Описание должно быть не длиннее 8000 символов.')
    def settings(key):
        value = opts.get(key, {})
        if not isinstance(value, dict):
            raise ValueError('Некорректные настройки Edit.')
        return value
    if mode == 'edit' and not prompt:
        raise ValueError('Опишите, что нужно изменить.')
    if mode == 'retouch':
        brush = settings('editWorkspaceBrush')
        if brush.get('mode') not in {'erase', 'replace'}:
            raise ValueError('Выберите Replace или Erase.')
        if not opts.get('editWorkspaceMaskUrl'):
            raise ValueError('Выделите область кистью.')
        if brush.get('mode') == 'replace' and not prompt:
            raise ValueError('Опишите, чем заменить выделенную область.')
    if mode == 'background':
        if opts.get('editWorkspaceBackgroundMode') not in {'transparent', 'replace'}:
            raise ValueError('Выберите режим фона.')
        if opts.get('editWorkspaceBackgroundMode') == 'replace' and not prompt:
            raise ValueError('Опишите новый фон.')
    if mode == 'translate' and not str(opts.get('editWorkspaceTranslateLanguage') or '').strip():
        raise ValueError('Выберите язык перевода.')
    if mode == 'resize':
        dimensions(settings('editWorkspaceResize'))
    if mode == 'expand':
        expansion = settings('editWorkspaceExpand')
        if not any(number(expansion.get(key), 0, 4096, 0) for key in ('left', 'right', 'top', 'bottom')):
            raise ValueError('Добавьте пространство хотя бы с одной стороны.')
        for key in ('left', 'right', 'top', 'bottom'):
            number(expansion.get(key), 0, 4096, 0)
    if mode == 'camera':
        camera = settings('editWorkspaceCamera')
        number(camera.get('horizontal'), 0, 360, 0)
        number(camera.get('vertical'), -30, 90, 0)
        number(camera.get('zoom'), 0, 10, 5)
    if mode == 'lighting':
        light = settings('editWorkspaceLight')
        layers = light.get('layers', [light])
        if not isinstance(layers, list) or not 1 <= len(layers) <= 8:
            raise ValueError('Допустимо от одного до восьми источников света.')
        enabled = []
        for layer in layers:
            if not isinstance(layer, dict):
                raise ValueError('Некорректный источник света.')
            number(layer.get('horizontal'), -100, 100, 0)
            number(layer.get('vertical'), -100, 100, 0)
            brightness = number(layer.get('brightness'), 0, 2, 1)
            if not re.fullmatch(r'#[0-9a-fA-F]{6}', str(layer.get('color') or '#ffffff')):
                raise ValueError('Введите цвет в формате #RRGGBB.')
            if layer.get('enabled') is not False and brightness > 0:
                enabled.append(layer)
        if not enabled:
            raise ValueError('Включите хотя бы один источник света с яркостью выше нуля.')
    if mode == 'upscale':
        upscale = settings('editWorkspaceUpscale')
        dimensions(upscale, 24000, 100_000_000)
        for key in ('sharpness', 'denoise', 'strength', 'creativity', 'modelStrength', 'fixCompression'):
            if key in upscale:
                number(upscale[key], 1 if key == 'modelStrength' else 0, 100)
        if upscale.get('subject', 'All') not in {'All', 'Foreground', 'Background', 'Face', 'None'}:
            raise ValueError('Выберите область улучшения.')
    return mode


def camera_parameters(settings):
    """The exact same angles are used for numeric controls, prompt and history."""
    return {key: number(settings.get(key), low, high, default) for key, low, high, default in (
        ('horizontal', 0, 360, 0), ('vertical', -30, 90, 0), ('zoom', 0, 10, 5))}


def camera_prompt(camera):
    return (f"Camera azimuth {camera['horizontal']:g} degrees (0 front, 90 right, 180 back, 270 left); "
            f"elevation {camera['vertical']:g} degrees; zoom {camera['zoom']:g}/10 (0 far, 10 close). "
            "Preserve the same subject identity, clothing, scene objects, environment and overall style.")


def png(image):
    output = io.BytesIO()
    image.save(output, format='PNG')
    return output.getvalue()


def normalize_source(raw):
    with Image.open(io.BytesIO(raw)) as image:
        if image.width * image.height > 100_000_000:
            raise ValueError('Изображение превышает 100 мегапикселей.')
        oriented = ImageOps.exif_transpose(image).convert('RGBA')
        return png(oriented), oriented.size


def prepare_expansion(source_png, settings):
    """Transparent new canvas, with the original pixels protected by an alpha mask."""
    with Image.open(io.BytesIO(source_png)) as source:
        offsets = {key: int(number(settings.get(key), 0, 4096, 0)) for key in ('left', 'right', 'top', 'bottom')}
        size = dimensions({'width': source.width + offsets['left'] + offsets['right'],
                           'height': source.height + offsets['top'] + offsets['bottom']})
        canvas = Image.new('RGBA', size)
        canvas.paste(source, (offsets['left'], offsets['top']))
        mask = Image.new('RGBA', size)
        mask.paste((0, 0, 0, 255), (offsets['left'], offsets['top'], offsets['left'] + source.width, offsets['top'] + source.height))
        return png(canvas), png(mask), size, offsets


def resize_image(source_png, size):
    with Image.open(io.BytesIO(source_png)) as source:
        return png(source.convert('RGBA').resize(size, Image.Resampling.LANCZOS))


def composite_expansion(source_png, generated, size, offsets):
    with Image.open(io.BytesIO(generated)) as image:
        canvas = image.convert('RGBA').resize(size, Image.Resampling.LANCZOS)
    with Image.open(io.BytesIO(source_png)) as source:
        canvas.paste(source, (offsets['left'], offsets['top']))
    return png(canvas)


def output_size(size):
    """Closest valid GPT Image size, retaining the requested aspect ratio."""
    width, height = size
    # Fit extreme input ratios to the API's 3:1 envelope. Pixel operations
    # below restore the exact requested canvas and preserve original pixels.
    width, height = max(width, height / 3), max(height, width / 3)
    scale = min(1, 3840 / max(width, height), math.sqrt(8_000_000 / (width * height)))
    if width * height * scale * scale < 700_000:
        scale = math.sqrt(700_000 / (width * height))
    width, height = int(math.ceil(width * scale / 16)) * 16, int(math.ceil(height * scale / 16)) * 16
    return f'{width}x{height}'


def instruction(opts):
    mode = opts.get('editWorkspaceMode', 'edit')
    user = str(opts.get('editWorkspacePrompt') or '').strip()
    tasks = {
        'edit': 'Apply the requested edit. Preserve all unrequested details and subject identity.',
        'retouch': ('Remove the content inside the masked area and reconstruct the background naturally.'
                    if (opts.get('editWorkspaceBrush') or {}).get('mode') == 'erase' else
                    'Replace only the masked area according to the instruction. Preserve everything outside it.'),
        'background': ('Remove the background. Keep the foreground subject, fine hair and edges. Return true transparency.'
                       if opts.get('editWorkspaceBackgroundMode') == 'transparent' else
                       'Replace only the background. Keep the foreground subject and its identity unchanged.'),
        'expand': 'Fill only the transparent canvas margins. Continue the scene naturally. Preserve the original image in place without moving, scaling or duplicating its subjects.',
        'translate': 'Translate all visible text into ' + str(opts.get('editWorkspaceTranslateLanguage') or '') + '. Preserve layout, fonts, typography, colors and all non-text content.',
    }
    return tasks.get(mode, 'Preserve the original image content.') + ('\nUser instruction: ' + user if user else '')


def is_free_resize(payload):
    opts = payload.get("image_options") or {}
    return str(payload.get("mode") or payload.get("category") or "").lower() == "image" and str(opts.get("tool") or "").strip().lower() == "edit_workspace" and str(opts.get("editWorkspaceMode") or "").strip().lower() == "resize"
