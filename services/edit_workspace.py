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
        lighting_parameters(settings('editWorkspaceLight'))
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


CAMERA_SCENE_PROMPT = """Reconstruct the input image as the exact same frozen three-dimensional scene viewed from the requested new camera position.

ONLY THE CAMERA MAY MOVE. The entire scene must remain fixed in world space. Do not rotate, mirror, flip, translate, reposition, re-pose, reorient, or restage any subject, object, living being, structure, or scene element.

Preserve the exact world-space position, orientation, scale, pose, geometry, spacing, and spatial relationship of every visible and inferred scene element.

Preserve every subject's exact body orientation, limb positions, posture, head orientation, facial direction, and gaze vector in world space. A change in camera viewpoint must never cause a subject to turn toward the camera, look in another direction, straighten the head, or change pose.

Treat all scene elements as fixed three-dimensional objects. Render each element from the physically correct side that becomes visible from the requested camera position. Surfaces that were hidden in the source view must be reconstructed as the unseen parts of the same unchanged object or subject, consistent with its geometry, material, identity, orientation, and surrounding scene. Never duplicate, replace, relocate, redesign, or independently rotate an element to imitate a new viewpoint.

Reconstruct the newly visible parts of the environment according to the fixed spatial layout of the original scene. The new background and foreground must represent what would physically exist from the new camera position, not a mirrored or reused version of the original view.

Recalculate perspective, parallax, occlusion, visible surfaces, depth ordering, apparent screen-space direction, relative scale, reflections, highlights, and shadows according to the new camera position while preserving the same world-space geometry and lighting configuration.

Do not simulate a viewpoint change by mirroring the image, flipping the composition, rotating individual subjects, or turning scene elements toward the new camera.

Preserve identity, appearance, proportions, materials, colors, scene continuity, lighting setup, and original aspect ratio.

The result must represent a physically plausible photograph of the exact same frozen scene taken from the requested new camera position."""


def camera_prompt(camera):
    return (f"{CAMERA_SCENE_PROMPT}\n\n"
            f"Camera position: azimuth {camera['horizontal']:g}°, "
            f"elevation {camera['vertical']:g}°, zoom {camera['zoom']:g}/10.")


def lighting_parameters(settings):
    """Normalize old screen-position controls and new orbit angles to degrees."""
    coordinates = settings.get('coordinateSystem', 'legacy')
    if coordinates not in ('legacy', 'spherical-degrees'):
        raise ValueError('Неизвестная система координат света.')
    spherical = coordinates == 'spherical-degrees'
    layers = settings.get('layers', [settings])
    if not isinstance(layers, list) or not 1 <= len(layers) <= 8:
        raise ValueError('Допустимо от одного до восьми источников света.')
    normalized = []
    for layer in layers:
        if not isinstance(layer, dict):
            raise ValueError('Некорректный источник света.')
        horizontal = number(layer.get('horizontal'), 0 if spherical else -100, 360 if spherical else 100, 0)
        vertical = number(layer.get('vertical'), -90 if spherical else -100, 90 if spherical else 100, 0)
        color = str(layer.get('color') or '#ffffff')
        if not re.fullmatch(r'#[0-9a-fA-F]{6}', color):
            raise ValueError('Введите цвет в формате #RRGGBB.')
        normalized.append({
            'horizontal': horizontal if spherical else round((horizontal * .9) % 360, 6),
            'vertical': vertical if spherical else round(vertical * .9, 6),
            'brightness': number(layer.get('brightness'), 0, 2, 1),
            'color': color.lower(), 'enabled': layer.get('enabled') is not False,
        })
    if not any(layer['enabled'] and layer['brightness'] > 0 for layer in normalized):
        raise ValueError('Включите хотя бы один источник света с яркостью выше нуля.')
    return {'coordinateSystem': 'spherical-degrees', 'layers': normalized}


def lighting_prompt(lighting):
    descriptions = []
    directions = ('front', 'front-right', 'right', 'back-right', 'back', 'back-left', 'left', 'front-left')
    for index, layer in enumerate(lighting['layers']):
        if not layer['enabled'] or layer['brightness'] == 0:
            continue
        direction = directions[int((layer['horizontal'] + 22.5) // 45) % 8]
        descriptions.append(
            f"source {index + 1}: color {layer['color']}, azimuth {layer['horizontal']:g} degrees ({direction}), "
            f"elevation {layer['vertical']:g} degrees, brightness {layer['brightness']:g}/2")
    return (f"Relight using {len(descriptions)} light source(s): " + '; '.join(descriptions) + '. '
            "Azimuth is 0 front (camera side), 90 image-right, 180 behind the subject, 270 image-left; "
            "positive elevation is above, negative below. Brightness 1/2 is normal intensity, 2/2 is double. "
            "Combine all listed sources with their relative intensities and colors; back lights create rim lighting. "
            "Preserve the subject identity, pose, objects, background, camera viewpoint and composition. Change only illumination and shadows.")


def lighting_initial_latent(lighting):
    """IC-Light only supports a coarse directional hint; full angles stay in the prompt."""
    enabled = [layer for layer in lighting['layers'] if layer['enabled'] and layer['brightness'] > 0]
    dominant = max(enabled, key=lambda layer: layer['brightness'])
    h, v = math.radians(dominant['horizontal']), math.radians(dominant['vertical'])
    x, y = math.sin(h) * math.cos(v), math.sin(v)
    if max(abs(x), abs(y)) < .15:
        return 'None'
    if abs(x) >= abs(y):
        return 'Right' if x > 0 else 'Left'
    return 'Top' if y > 0 else 'Bottom'


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
