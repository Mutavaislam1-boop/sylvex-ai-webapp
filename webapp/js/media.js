/*
 * SYLVEX Media — one browsing layer over the media catalogs that already
 * exist in SYLVEX. Nothing here is a copy of a catalog: every item comes
 * from the same public endpoints Pro Studio reads (main.py), and media
 * files are loaded from the backend that serves those catalogs.
 *
 *   video styles      GET /api/public/prostudio/video-templates
 *   video effects     GET /api/public/prostudio/kling/effects
 *   image styles      GET /api/public/prostudio/quick-image-catalog  (styles)
 *   photo references  GET /api/public/prostudio/quick-image-catalog  (references, popular_references)
 *   catalog photos    GET /api/public/prostudio/photo-catalog
 *   tool examples     GET /api/public/prostudio/photo-tool-demos
 *   references        GET /api/public/prostudio/references (published by admins;
 *                     category "featured"/"trending" feeds the moving row)
 *   Media blocks      published from the Admin Console's Media constructor,
 *                     inside the video template and photo catalogs above
 *                     (`media_block` on the item)
 *
 * Characters and Objects are deliberately left out of this page.
 */
(function (global) {
  'use strict';

  var CATEGORIES = [
    { id: 'video_styles', label: 'Video Styles', mode: 'video' },
    { id: 'image_styles', label: 'Image Styles', mode: 'image' },
    { id: 'photo_references', label: 'Photo References', mode: 'image' },
    { id: 'video_references', label: 'Video References', mode: 'video' },
    { id: 'video_effects', label: 'Video Effects', mode: 'video' },
    { id: 'catalog_photos', label: 'Catalog Photos', mode: 'image' },
    { id: 'references', label: 'References', mode: 'image' },
    { id: 'tool_examples', label: 'Tool Examples', mode: 'image' },
  ];
  var EXCLUDED = /^(characters?|objects?|персонаж\w*|объект\w*)$/i;
  var FEATURED = /^(featured|trending|viral|reels|tiktok)$/i;
  var VIDEO_EXT = /\.(mp4|webm|mov|m4v)(\?|#|$)/i;
  var SOURCES = {
    videoTemplates: '/api/public/prostudio/video-templates',
    videoEffects: '/api/public/prostudio/kling/effects',
    quickImage: '/api/public/prostudio/quick-image-catalog',
    photoCatalog: '/api/public/prostudio/photo-catalog',
    toolDemos: '/api/public/prostudio/photo-tool-demos',
    references: '/api/public/prostudio/references',
  };

  function absolute(base, path) {
    var value = String(path || '').trim();
    if (!value) return '';
    if (/^(https?:)?\/\//i.test(value) || /^data:/i.test(value)) return value;
    return String(base || '').replace(/\/$/, '') + (value.charAt(0) === '/' ? '' : '/') + value;
  }

  // "9:16" -> 0.5625 (width / height); 0 when unknown.
  function ratio(value) {
    var match = /^(\d+(?:\.\d+)?)\s*[:/x]\s*(\d+(?:\.\d+)?)$/i.exec(String(value || '').trim());
    return match && Number(match[2]) ? Number(match[1]) / Number(match[2]) : 0;
  }

  function cleanTitle(value) {
    var text = String(value || '').trim();
    // File-name titles (UUIDs, "IMG_0042") say nothing to a visitor.
    if (!text || /^[0-9a-f-]{16,}$/i.test(text) || /^(img|dsc|photo)[_-]?\d+$/i.test(text) || text === 'Название фотографии') return '';
    return text;
  }

  function item(category, fields) {
    var src = fields.video || fields.image || '';
    if (!src) return null;
    return {
      id: category + ':' + (fields.id || src),
      // The item's id in its own catalog - Pro Studio finds its block by it.
      sourceId: String(fields.id || ''),
      aspect: String(fields.aspect || ''),
      prompt: String(fields.prompt || ''),
      cost: Number(fields.cost || 0),
      category: category,
      kind: fields.video ? 'video' : 'image',
      title: cleanTitle(fields.title),
      description: String(fields.description || '').trim(),
      image: fields.image || '',
      video: fields.video || '',
      ratio: fields.ratio || 0,
      // A Media block built in the Admin Console opens its own window
      // (js/media-blocks.js) with the upload fields its admin set up.
      block: fields.block || null,
    };
  }

  // Turns the raw catalog responses into one list of media items.
  // `sources` holds each endpoint's JSON (or null when it failed).
  function collect(sources, base) {
    var s = sources || {};
    var out = [];
    var push = function (value) { if (value) out.push(value); };

    ((s.videoTemplates && s.videoTemplates.templates) || []).forEach(function (t) {
      var video = t.preview_exists === false ? '' : absolute(base, t.preview_video || t.reference_video);
      var poster = t.poster_exists === false ? '' : absolute(base, t.poster_url);
      push(item('video_styles', { id: t.id, title: t.title || t.name, description: t.description, video: video, image: poster, ratio: ratio(t.aspect_ratio), aspect: t.aspect_ratio, cost: t.cost_credits || t.cost, block: t.media_block }));
    });
    ((s.videoEffects && s.videoEffects.effects) || []).forEach(function (e) {
      push(item('video_effects', { id: e.id || e.effect_scene, title: e.title || e.name, description: e.description, video: absolute(base, e.preview_video), image: absolute(base, e.poster_url), ratio: ratio(e.aspect_ratio), aspect: e.aspect_ratio, cost: e.cost_credits || e.cost }));
    });
    var quick = (s.quickImage && s.quickImage.catalog) || {};
    (quick.styles || []).forEach(function (q) {
      push(item('image_styles', { id: q.id, title: q.title, description: q.description, image: absolute(base, q.image_url), block: q.media_block }));
    });
    (quick.references || []).concat(quick.popular_references || []).forEach(function (q) {
      push(item('photo_references', { id: q.id, title: q.title, description: q.description, image: absolute(base, q.image_url), block: q.media_block }));
    });
    ((s.photoCatalog && s.photoCatalog.photos) || []).forEach(function (p) {
      push(item('catalog_photos', { id: p.id, title: p.title, description: p.description, image: absolute(base, p.image_url), ratio: ratio(p.aspect_ratio), prompt: p.prompt }));
    });
    var demos = (s.toolDemos && s.toolDemos.demos) || {};
    Object.keys(demos).forEach(function (key) {
      var demo = demos[key] || {};
      push(item('tool_examples', { id: key, title: key.replace(/_/g, ' ').replace(/\b\w/g, function (c) { return c.toUpperCase(); }), image: absolute(base, demo.after || demo.before) }));
    });
    var featured = [];
    ((s.references && s.references.items) || []).forEach(function (r) {
      var category = String(r.category || '').trim();
      if (EXCLUDED.test(category)) return;
      var url = absolute(base, r.preview_url || r.source_url);
      var isVideo = String(r.kind || '').toLowerCase() === 'video' || VIDEO_EXT.test(url);
      var entry = item(isVideo ? 'video_references' : (/photo|reference/i.test(category) ? 'photo_references' : 'references'), {
        id: 'ref' + r.id, title: r.name, description: r.description,
        video: isVideo ? url : '', image: isVideo ? '' : url,
      });
      if (!entry) return;
      if (FEATURED.test(category)) featured.push(entry); else out.push(entry);
    });

    // The same file can be listed by more than one catalog: keep it once.
    var seen = {};
    var unique = out.filter(function (entry) {
      var key = (entry.video || entry.image).split('?')[0];
      if (seen[key]) return false;
      seen[key] = true;
      return true;
    });
    return { items: unique, featured: featured };
  }

  // The "All" wall mixes categories instead of showing them in blocks:
  // one item from each category in turn, in category order.
  function interleave(items) {
    var buckets = {};
    var order = [];
    items.forEach(function (entry) {
      if (!buckets[entry.category]) { buckets[entry.category] = []; order.push(entry.category); }
      buckets[entry.category].push(entry);
    });
    order.sort(function (a, b) { return categoryIndex(a) - categoryIndex(b); });
    var result = [];
    for (var round = 0; result.length < items.length; round += 1) {
      order.forEach(function (key) { if (buckets[key][round]) result.push(buckets[key][round]); });
    }
    return result;
  }

  function categoryIndex(id) {
    for (var i = 0; i < CATEGORIES.length; i += 1) if (CATEGORIES[i].id === id) return i;
    return CATEGORIES.length;
  }

  function category(id) {
    return CATEGORIES[categoryIndex(id)] || { id: id, label: id, mode: 'image' };
  }

  // Which of Pro Studio's catalog generations an item uses.
  // Catalog photos and admin references are references of their own (their
  // ids are not Pro Studio catalog ids): the photo + the reference + its prompt.
  var GENERATION_KINDS = {
    video_styles: 'video_template', video_effects: 'video_effect', video_references: 'video_reference',
    catalog_photos: 'image_reference', references: 'image_reference', tool_examples: 'tool',
  };
  function generationKind(entry) {
    if (entry && entry.block) return 'media_block';
    if (entry && entry.category === 'photo_references' && /^ref/.test(entry.sourceId)) return 'image_reference';
    return GENERATION_KINDS[entry && entry.category] || 'image';
  }

  // The extra inputs some styles take, as Pro Studio's catalog block asks
  // for them (quickImageStyleFields in studio/js/website-studio.js).
  var STYLE_FIELDS = {
    photo_09: [{ key: 'artist', label: 'Artist name' }, { key: 'song', label: 'Song title' }, { key: 'album_cover', label: 'Player cover', type: 'image' }],
    photo_37: [{ key: 'artist', label: 'Artist name' }, { key: 'song', label: 'Song title' }, { key: 'album_cover', label: 'Player cover', type: 'image' }],
    photo_29: [{ key: 'beanie_color', label: 'Beanie colour' }, { key: 'beanie_stickers', label: 'Stickers: smileys, flag or badges' }],
    photo_32: [
      { key: 'instagram_profile_image', label: 'Profile photo', type: 'image' },
      { key: 'instagram_username', label: 'Username' }, { key: 'instagram_display_name', label: 'Display name' },
      { key: 'instagram_caption', label: 'Caption' }, { key: 'instagram_likes', label: 'Likes' },
      { key: 'instagram_location', label: 'Location' },
    ],
  };
  function styleFields(entry) {
    return (entry && entry.category === 'image_styles' && STYLE_FIELDS[entry.sourceId]) || [];
  }

  // Every catalog from the backend at `base`; a catalog that fails is skipped.
  function load(base) {
    var keys = Object.keys(SOURCES);
    return Promise.all(keys.map(function (key) {
      return fetch(base + SOURCES[key], { credentials: 'omit' })
        .then(function (response) { return response.ok ? response.json() : null; })
        .catch(function () { return null; });
    })).then(function (results) {
      var sources = {};
      keys.forEach(function (key, index) { sources[key] = results[index]; });
      return collect(sources, base);
    });
  }

  global.SYLVEX_MEDIA = {
    CATEGORIES: CATEGORIES,
    load: load,
    collect: collect,
    interleave: interleave,
    category: category,
    generationKind: generationKind,
    styleFields: styleFields,
    absolute: absolute,
    ratio: ratio,
  };
})(typeof window !== 'undefined' ? window : globalThis);
