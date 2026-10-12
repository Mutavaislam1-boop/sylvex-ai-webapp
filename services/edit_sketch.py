"""Bounded editable drawing documents in private Edit session history."""
import json
import math
import re

STROKES = {'pen', 'pencil', 'brush', 'marker', 'eraser'}
SHAPES = {'line', 'arrow', 'rectangle', 'ellipse', 'triangle', 'star', 'diamond', 'pentagon', 'hexagon', 'cross', 'speech', 'text', 'sticker'}


def validate_sketch(value):
    def fail():
        raise ValueError('invalid_edit_sketch')

    def number(v, low, high):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not low <= v <= high:
            fail()

    def color(v):
        if not isinstance(v, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', v):
            fail()

    if not isinstance(value, dict) or value.get('version') != 1:
        fail()
    for field in ('width', 'height'):
        number(value.get(field), 256, 4096)
        if not isinstance(value[field], int):
            fail()
    color(value.get('background'))
    items = value.get('items')
    if not isinstance(items, list) or len(items) > 500 or len(json.dumps(value)) > 2_000_000:
        fail()
    for item in items:
        if not isinstance(item, dict) or item.get('type') not in STROKES | SHAPES:
            fail()
        for field in ('x', 'y'):
            number(item.get(field), -100000, 100000)
        for field in ('sx', 'sy'):
            number(item.get(field), .001, 1000)
        number(item.get('rotation'), 0, 360)
        number(item.get('size'), 1, 100)
        number(item.get('opacity'), 0, 1)
        color(item.get('color'))
        color(item.get('fill'))
        if item['type'] in STROKES:
            points = item.get('points')
            if not isinstance(points, list) or not 1 <= len(points) <= 4096:
                fail()
            for point in points:
                if not isinstance(point, list) or len(point) != 3:
                    fail()
                number(point[0], -100000, 100000)
                number(point[1], -100000, 100000)
                number(point[2], 0, 1)
        else:
            for field in ('w', 'h'):
                number(item.get(field), -100000 if item['type'] in {'line', 'arrow'} else 0, 100000)
            if item['type'] in {'text', 'sticker'} and (not isinstance(item.get('text'), str) or len(item['text']) > 320):
                fail()
