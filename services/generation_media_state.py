"""Lossless result merges for independent history, storage and thumbnail writers."""
from __future__ import annotations


MEDIA_FIELDS = (
    'image_url','images','thumbnail_url','thumb_url','thumbnails',
    'svg_url','svg_download_url','svg_urls','video_url','videos',
    'audio_url','audio_urls','audios','music_url','result_url','full_url','url',
    'file_url','files','cover_url','artwork_url','storage_status','thumbnail_status',
)


def _urls(value, fallback=''):
    values=value if isinstance(value,list) else []
    result=[item for item in values if isinstance(item,str) and item]
    return result or ([fallback] if isinstance(fallback,str) and fallback else [])


def align_media_metadata(result: dict) -> dict:
    """Output aliases follow the committed media, while inputs/settings stay intact."""
    out=dict(result)
    metadata=dict(out.get('metadata') or {}) if isinstance(out.get('metadata'),dict) else {}
    images=_urls(out.get('images'),out.get('image_url'))
    videos=_urls(out.get('videos'),out.get('video_url'))
    audios=_urls(out.get('audios') or out.get('audio_urls'),out.get('audio_url') or out.get('music_url'))
    thumbs=_urls(out.get('thumbnails'),out.get('thumbnail_url') or out.get('thumb_url'))
    mode=str(out.get('type') or metadata.get('type') or '').lower()
    if images:metadata.update(result_images=images,image_url=images[0])
    if videos:metadata.update(videos=videos,video_url=videos[0])
    if audios:metadata.update(audios=audios,audio_url=audios[0])
    if thumbs:metadata.update(result_thumbnails=thumbs,thumbnail_url=thumbs[0],thumb_url=thumbs[0])
    primary=(videos if mode=='video' else audios if mode in {'voice','music'} else images)
    if primary:metadata.update(result_url=primary[0],full_url=primary[0],preview_fallback_url=primary[0])
    for key in ('svg_url','svg_download_url'):
        if out.get(key):metadata[key]=out[key]
    if mode in {'music','voice'} and images:metadata['image_url_cover']=images[0]
    if metadata or 'metadata' in out:out['metadata']=metadata
    return out


def merge_generation_result_fields(current: dict, fields: dict, *, preserve_existing_media=False) -> dict:
    """Late history completion enriches the result; storage alone advances media."""
    current=dict(current or {});fields=dict(fields or {})
    if preserve_existing_media:
        for key in MEDIA_FIELDS:
            if key in current:fields.pop(key,None)
    old_metadata=current.get('metadata')
    new_metadata=fields.get('metadata')
    if isinstance(old_metadata,dict) or isinstance(new_metadata,dict):
        fields['metadata']={**(old_metadata if isinstance(old_metadata,dict) else {}),
                            **(new_metadata if isinstance(new_metadata,dict) else {})}
    return align_media_metadata({**current,**fields})


def history_generation_id(metadata: dict, response: dict) -> str:
    for value in (response.get('job_id'),metadata.get('job_id'),metadata.get('charge_id'),response.get('charge_id')):
        if isinstance(value,str) and 0 < len(value.strip()) <= 200:return value.strip()
    return ''


def overlay_stored_history_media(history: dict, committed: dict) -> dict:
    """Use only verified storage output, keeping history inputs/title/favorites intact."""
    if not isinstance(committed,dict):return dict(history)
    if committed.get('storage_status')!='completed' and committed.get('storage_recovery_version')!=1:return dict(history)
    fields={key:committed[key] for key in MEDIA_FIELDS if key not in {'storage_status','thumbnail_status'} and committed.get(key)}
    return merge_generation_result_fields(history,fields)
