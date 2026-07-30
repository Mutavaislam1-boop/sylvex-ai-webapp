# Каталог фотографий

Каталог заполняется только разработчиком. Создайте для каждой карточки отдельную папку:

```text
photo-catalog/
├── 01/
│   ├── photo.jpg
│   └── template.json
├── 02/
│   ├── photo.png
│   └── template.json
```

Поддерживаемые имена изображения: `photo.jpg`, `photo.jpeg`, `photo.png`, `photo.webp`,
`preview.jpg`, `preview.png`, `preview.webp`. Если такого имени нет, backend возьмёт первое
поддерживаемое изображение из папки.

Папка без изображения в каталоге не отображается. После изменения файлов каталог обновляется
не позднее чем через 60 секунд или после перезапуска приложения.

Пример `template.json`:

```json
{
  "id": "fashion_01",
  "title": "Fashion portrait",
  "description": "Студийный fashion-портрет",
  "prompt": "Create a premium studio fashion portrait",
  "aspect_ratio": "9:16",
  "model": "seedream_5_0_lite"
}
```
