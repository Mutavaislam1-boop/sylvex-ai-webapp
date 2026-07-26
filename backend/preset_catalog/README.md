# Preset Catalog

Characters live in `characters/<slug>/`.
Objects live in `objects/<slug>/`.
Voice avatars live in `voice_avatars/<provider>/<voice_id>/`.

Each character/object folder can contain:

- `avatar.png`
- `reference_1.png`
- `reference_2.png`
- `reference_3.png`
- `video_reference.mp4` (optional, used only for HeyGen avatar/video-avatar flows)
- `heygen.json` (optional HeyGen IDs)
- `prompt.txt`

Example `heygen.json`:

```json
{
  "photoAvatarId": "heygen_photo_avatar_or_look_id",
  "videoAvatarId": "heygen_video_avatar_or_look_id",
  "avatarGroupId": "optional_heygen_avatar_group_id"
}
```

Each voice avatar folder can contain:

- `avatar.png`
