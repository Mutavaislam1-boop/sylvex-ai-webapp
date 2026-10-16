# Аудит тарификации AI API в SYLVEX

Дата проверки: **15 октября 2026 года**
Область: генерация изображений, видео, музыки, озвучки и текста в Pro Studio, Mini App и Edit.

## Статус исправления

Недочёты из этого аудита исправлены в версии тарификации `2026-10-audit-v2`.
Ниже сохранены исходные выводы аудита, чтобы было видно, почему менялась
каждая формула.

- Стоимость провайдера теперь рассчитывается отдельно по правилам конкретной
  модели: токены prompt и изображений, мегапиксели референсов, длительность
  входного видео, audio tier, resolution и число результатов учитываются там,
  где провайдер действительно за них списывает деньги.
- Если xAI, Runway, OpenAI Image, Google Image, Gemini TTS или ElevenLabs
  возвращают фактический usage/cost, итог пересчитывается по нему в пределах
  предварительно зарезервированной суммы.
- У SYLVEX остаётся отдельная продуктовая плата **1 ⚡ ($0.01)** за каждый
  уникальный используемый референс, встроенный стиль, объект или персонаж.
  Она не подменяет provider fee, показывается отдельно в price snapshot и не
  дублируется, если один asset передан через несколько совместимых alias-полей.
- Модели с официально закрытым API удалены из пользовательских списков и
  дополнительно блокируются сервером. Модели без подтверждённого тарифа
  fail-closed: запрос к провайдеру не запускается и баланс не списывается.

## Исходное состояние до исправления

Ниже сохранены исходные выводы аудита, на основании которых были внесены перечисленные выше исправления.

Текущую систему нельзя считать полностью соответствующей фактическим расходам провайдеров.

- Текстовые запросы резервируются до вызова и после ответа пересчитываются по фактическим `usage`-токенам. Это правильная основа, однако часть тарифов устарела, не учитываются tiered/long-context ставки и cached input.
- Изображения, видео, музыка и голос почти всегда списываются по локальной таблице до вызова провайдера. Фактическая стоимость из ответа провайдера не сверяется с резервом.
- Универсальная надбавка `0.3 ⚡` за каждый найденный reference применяется ко всем нетекстовым моделям, хотя провайдеры считают референсы по-разному: бесплатно, за изображение, за мегапиксель, за секунду входного видео или уже включают их в цену.
- Одинаковый reference может находиться под несколькими alias-полями и быть посчитан повторно, потому что список не дедуплицируется.
- Большой prompt влияет на цену только у токеновых моделей: текстовых, GPT Image, Gemini Image/TTS/Omni. У большинства классических image/video/music API prompt отдельно не тарифицируется.
- Есть модели, которые уже отключены официальными API, но остаются доступны в проекте: Sora 2/Pro, Imagen 4, Runway Gen-3 Alpha Turbo, Runway Aleph и Luma Dream Machine/Ray 1.6.

## Как именно данные запроса влияют на цену

| Состав запроса | Где влияет на себестоимость | Где обычно не влияет отдельно |
|---|---|---|
| Длинный пользовательский или встроенный style/system prompt | Все text-модели; GPT Image; Gemini Image; Gemini TTS; Gemini Omni | Ideogram, Recraft, Seedream, Qwen Image 2, FLUX Kontext, Grok Image, большинство video/music API |
| История диалога | Text-модели: каждый переданный turn входит во входные токены | Image/video/music API без токеновой тарификации |
| Фото для анализа текстовой моделью | Входит в multimodal input tokens OpenAI/Gemini/xAI | Сейчас Qwen/BytePlus vision в Text UI не отправляются и правильно блокируются для image prompt |
| Фото-референсы для генерации изображения | GPT Image, Gemini Image, FLUX.2, Grok Image; Seedream 5 Pro со второго ref | Qwen Image 2, обычные Seedream 4/4.5/5 Lite, многие fixed-price image API |
| Начальный/конечный кадр видео | Иногда включён, иногда платится как reference image | Зависит от конкретной модели, общей формулы нет |
| Входное/reference video | Runway Seedance/Omni, Wan R2V/Edit, Grok Video edit, PixVerse video-reference, Luma V2V | Не может оцениваться как обычный image reference |
| Разрешение, качество, число результатов | Почти все image/video API | — |
| Длительность видео/аудио | Почти все video API, STS, dubbing, isolation, sound effects | — |
| Звук в видео | Veo, Seedance, Kling и некоторые PixVerse/другие тарифы | Модели, где native audio уже обязателен и включён |

## Общая логика SYLVEX

Формула проекта объявлена как `ceil(provider_cost_usd × 1.5 × 100)`. Она реализована корректно через `Decimal` в `services/price_engine.py`, но значительная часть базовых `provider_cost_usd` либо не используется, либо уже содержит наценку, либо заменена вручную заданными кредитами.

Критические места:

1. `services/price_engine.py:26-70` добавляет style/character/object и универсальные reference-надбавки независимо от реального тарифа провайдера.
2. `services/price_engine.py:61-63` суммирует пять alias-полей без дедупликации URL/asset ID.
3. `services/price_engine.py:92-120` замораживает расчёт до отправки. Для media-моделей отсутствует последующее сравнение с provider usage/cost.
4. `main.py:5079-5108` имеет единственную пару input/output ставок на text-модель и не может корректно выразить long context, thinking/non-thinking, cache, service tier и региональный коэффициент.
5. `main.py:5120-5136` извлекает только aggregate input/output usage. Cached input теряется и тарифицируется как обычный input.
6. `services/video_router.py:1764-1868` считает почти все видео только по duration/resolution/sound и не включает реальную стоимость входных media.

## Изображения

### OpenAI — `gpt_image_1`, `gpt_image_2`, `gpt_image_2_5_sunburst`

**Провайдер списывает:** text input tokens + image input tokens + image output tokens. Поэтому большой встроенный prompt, каждое reference-фото, detail/fidelity, размер, качество и число outputs меняют цену. Высокая fidelity референсов увеличивает image input tokens.

**В проекте:** локальная фиксированная цена только по quality и output count. Prompt и references не входят в базовую формулу; вместо них может добавиться универсальная `0.3 ⚡` надбавка.

**Вердикт:** критический недоучёт/искажение. Для GPT Image нужно считать по provider `usage` после ответа либо точно воспроизводить token calculation до вызова. Для Sunburst, если он вызывается через Runway, официальный Runway тариф — per output quality/resolution + 1 Runway credit за reference на каждый output; если он вызывается напрямую через OpenAI, применяется OpenAI token billing. Нельзя смешивать эти схемы.

### Ideogram — `ideogram_3_0`, `ideogram_4_0`

**Провайдер списывает:** за успешно сгенерированный output, с отдельными ставками Turbo/Default/Quality; у Ideogram 3 character reference имеет отдельный более дорогой тариф. Длина prompt отдельно не тарифицируется.

**В проекте:** output count и rendering speed учтены. Обычный reference затем может получить универсальную надбавку, а character reference должен считаться специальной ставкой модели.

**Вердикт:** базовая формула близка, generic reference surcharge нужно убрать и применять только официальный character-reference тариф там, где этот режим реально отправлен.

### Recraft — `recraft_v4_1`, `recraft_v4_1_pro`, `recraft_v3`

**Провайдер списывает:** за output или конкретную operation (generation, image-to-image, remove background, vectorize, upscale и т. п.). Длина prompt и обычное число refs не образуют универсальную надбавку.

**В проекте:** V4.1 provider cost `$0.035` соответствует официальному, но user price хранится как `$0.0525`; V3 provider cost `$0.04` соответствует. Для V4.1 Pro в конфигурации `provider_cost_usd` ошибочно равен `$0.21` при официальной цене `$0.21`, но user credits также равны 21 — 50% наценка не применена. Tool operations имеют отдельную внутреннюю таблицу, которую надо сверить построчно.

**Вердикт:** частично корректно; исправить семантику provider/user cost и убрать generic refs.

### BytePlus Seedream — `seedream_5_0_lite`, `seedream_5_0_pro`, `seedream_4_5`, `seedream_4_0`

**Провайдер списывает:** за каждый output. 5 Pro дополнительно берёт `$0.003` за каждое входное изображение начиная со второго; первый ref бесплатный. Lite/4.5/4.0 не имеют отдельной reference-оплаты. 5 Pro имеет два output price tier по размеру.

**В проекте:** outputs и два Pro tier учтены, input refs Pro не учтены, зато всем вариантам добавляется generic `0.3 ⚡` за каждый ref.

**Вердикт:** неверно для refs. Формула Pro: output tier + `max(0, reference_count - 1) × $0.003`; у остальных refs = `$0`.

### Black Forest Labs — `flux_pro_kontext`, `flux_2`, `flux_2_turbo`

**Провайдер списывает:** Kontext Pro — flat per output. FLUX.2 Pro — первый output MP `$0.03`, последующие MP `$0.015`; каждый reference `$0.015/MP`. FLUX.2 Flex — `$0.05/MP` для output и каждого reference. Каждый MP округляется вверх отдельно.

**В проекте:** все варианты имеют fixed credits per output, без output MP и reference MP.

**Вердикт:** Kontext близок; FLUX.2 Pro/Flex критически неверны при размере больше 1 MP и при refs.

### Qwen — `qwen_image`, `qwen_image_2`, `qwen_image_2_pro`

**Провайдер списывает:** для используемой серии Qwen Image 2.0 — только за успешно сгенерированные output images. Prompt и refs отдельной строкой не тарифицируются.

**В проекте:** базовые output цены близки к официальным, но generic `0.3 ⚡` за refs создаёт лишнее списание.

**Вердикт:** удалить reference surcharge для этих моделей; output count оставить.

### Google — `nano_banana_2`, `nano_banana_2_lite`, `nano_banana_pro`, `nano_banana`

**Провайдер списывает:** text/image input tokens + output image tokens. Значит длинный prompt и каждое reference-фото влияют на цену. Output зависит от resolution/model. `nano_banana` → `gemini-2.5-flash-image` отключён 2 октября 2026 года.

**В проекте:** учитывается output resolution/count, input cost равен нулю. Фактический provider usage не используется.

**Вердикт:** недоучёт prompt/refs. `nano_banana` нужно убрать или перенаправить только после отдельного согласованного product migration.

### Google Imagen — `imagen_4_fast`, `imagen_4_standard`, `imagen_4_ultra`

**Провайдер списывал:** flat per output по tier; prompt отдельно не тарифицировался.

**Состояние API:** все три модели официально отключены 17 августа 2026 года.

**Вердикт:** критическая недоступность. Их нельзя показывать как рабочие модели.

### xAI — `grok`, `grok_pro`

**Провайдер списывает:** output image по model/resolution + каждое input image. Prompt length отдельно не тарифицируется. Ответ xAI теперь содержит точный `usage.cost_in_usd_ticks`.

**В проекте:** учитывается только бинарный `has_input_image`, то есть 1 и 5 refs стоят одинаково. Provider-reported exact cost игнорируется.

**Вердикт:** недоучёт нескольких refs. Лучший источник истины — `usage.cost_in_usd_ticks`, с предварительным верхним резервом.

## Видео

### Runway — `runway_gen4_5`, `runway_gen4_turbo`, `runway_aleph2`, `runway_aleph`, `runway_gen3a_turbo`, `runway_happyhorse_1_0`, `gemini_omni_flash` и Runway Seedance variants

**Провайдер списывает:** provider credits по duration; для части моделей отдельно refs, input/reference video, start image и professional/HDR format. Model-router response сообщает фактически выбранную модель и realized credits.

**В проекте:** основные per-second ставки Gen 4.5, Gen 4 Turbo и Aleph2 близки после наценки. Не учитываются professional/HDR surcharge и многие reference/input fees. HappyHorse 1080p занижен (`28.8` вместо provider `30` credits/sec до наценки). `gemini_omni_flash` ошибочно всегда считается как text-to-video и не учитывает +start frame либо input video/refs.

**Недоступные модели:** Runway Gen-3 Alpha Turbo и старый Aleph сняты 30 июля 2026 года, но остаются в UI/маршрутизации.

**Вердикт:** использовать realized provider credits из metadata. Убрать старые модели. До ответа резервировать worst-case по operation, input duration, refs и format.

### OpenAI Sora — `sora_2`, `sora_2_pro`

**Состояние API:** Videos API и обе модели отключены 24 сентября 2026 года.

**Вердикт:** маршруты гарантированно не должны считаться рабочими. Удалить из доступного каталога; текущая цена не имеет значения.

### Google Veo — `veo_3_1`, `veo_3_1_fast`

**Провайдер списывает:** за output second по model/resolution; в прямом Gemini Veo 3.1 audio включён в тариф модели. Standard: `$0.40/sec` для 720/1080 и `$0.60/sec` для 4K; Fast: `$0.10/$0.12/$0.30`.

**В проекте:** переключатель sound меняет цену standard с 60 на 30 credits/sec и fast между отдельными audio/no-audio ставками. Для прямого Gemini маршрута это создаёт занижение при sound=false.

**Вердикт:** критическая ошибка тарифа прямого Veo. Если запрос идёт через Runway, применять именно Runway audio/no-audio тариф; если напрямую к Google — тариф Google. Provider route должен входить в price key.

### Gemini Omni Flash — `gemini_omni_flash`

**Провайдер списывает:** input text/image/video/audio tokens + output video tokens. 720p output оценивается примерно `$0.10/sec`, но входные media дают дополнительную стоимость.

**В проекте:** flat `15 ⚡/sec`, что близко к output с 50% наценкой, но все input tokens бесплатны.

**Вердикт:** добавить input usage и settlement по provider usage.

### xAI Grok Video — `grok_video`, `grok_video_edit`

**Провайдер списывает:** output по seconds/resolution; input image за штуку, input video за секунду. Текущие официальные wire IDs — `grok-imagine-video` / `grok-imagine-video-1.5`, а response содержит exact cost.

**В проекте:** default IDs `grok-video-1` и `grok-video-1-edit` не совпадают с публичными текущими IDs; input fees игнорируются; 720p ставка проекта соответствует 1.5, хотя configured model похож на legacy.

**Вердикт:** критическая несовместимость model/rate. Пиновать точный provider ID и рассчитывать по exact response cost.

### Luma — `luma_ray_v3_2`, `luma_dream_machine`

**Провайдер списывает:** Ray 3.2 по request type (T2V/I2V, edit, reframe, extend), resolution, duration и SDR/HDR/EXR. I2V refs входят в generation tier; V2V/edit намного дороже.

**В проекте:** одна T2V/I2V таблица применяется также к edit/reframe. `luma_dream_machine` отправляет устаревший `ray-1-6`, который новый Agents API не принимает.

**Вердикт:** критический недоучёт edit/reframe и недоступная legacy-модель.

### Alibaba Wan — `wan_2_6`, `wan_2_7`, `wan_2_7_edit`

**Провайдер списывает:** T2V/I2V output seconds по resolution; reference-to-video и video edit могут считать сумму billable input video seconds + output seconds. Reference images и first frame могут быть бесплатны, но reference videos платны по длительности.

**В проекте:** одна output-only per-second ставка для T2V/I2V/R2V/edit. В `wan_2_7_edit` default wire model остаётся `wan2.1-vace-plus`, хотя product label 2.7.

**Вердикт:** T2V/I2V базово близки; video references/edit недоучтены, mapping модели требует исправления.

### BytePlus Seedance — `seedance_1_5_pro`, `seedance_2_fast`, `seedance_2_0`

**Провайдер списывает:** video tokens, зависящие от output duration/resolution/fps и, в video-to-video, от input duration; audio меняет tier. Prompt length и обычный image start frame не имеют отдельной flat надбавки.

**В проекте:** simplified per-second таблица по output + sound; input video duration не входит.

**Вердикт:** T2V/I2V можно оценивать таблицей, V2V должен включать input video token cost и желательно settlement по usage.

### PixVerse — `pixverse_v6`

**Провайдер списывает:** output duration/resolution/audio; video-reference режим имеет повышенную/удвоенную ставку. Prompt и обычный start image отдельно не оплачиваются.

**В проекте:** output duration/resolution/audio учтены; video-reference tier отсутствует.

**Вердикт:** обычная генерация близка, video references недоучтены.

### MiniMax — `minimax_hailuo_2_3`

**Провайдер списывает:** по выбранной модели, resolution и duration/request tier. Точная цена должна соответствовать прямому MiniMax PAYG contract конкретного account/region.

**В проекте:** hardcoded request table. Официальный публичный каталог уже смещён к H3/Hailuo 3, поэтому Hailuo 2.3 нельзя безопасно оценивать по текущей общей странице.

**Вердикт:** до получения invoice/usage API MiniMax считать тариф неподтверждённым; не добавлять generic refs.

### HeyGen — `heygen_v3_video_agent`, `heygen_avatar_iii`, `heygen_avatar_iv`, `heygen_avatar_v`, `heygen_image_video`, `heygen_cinematic_avatar`

**Провайдер списывает:** главным образом за фактические секунды output; engine/look type меняет ставку. Video Agent тарифицируется за минуту результата; Avatar IV/Avatar V дороже; 4K и custom expressive motion могут добавлять стоимость. Длина script сама по себе не отдельная строка, но увеличивает фактическую длительность видео.

**В проекте:** UI принудительно использует duration=5 для части HeyGen, а price считается по заданным 5 секундам, не по фактической длительности ответа. Cinematic Avatar — неподтверждённый fixed charge.

**Вердикт:** возможен крупный недоучёт длинного script. Резервировать по ожидаемой speech duration, затем settle по фактическим output seconds/provider cost.

### Kling — все `kling_*`

Модели: `kling_3_0_turbo`, `kling_3_0`, `kling_o3_omni`, `kling_o3_edit`, `kling_motion_2_6`, `kling_motion_3_0`, `kling_effects`, `kling_o1`, `kling_2_6`, `kling_2_5_turbo`, `kling_2_1`, `kling_2_1_master`, `kling_2_0_master`, `kling_1_6`, `kling_1_5`, `kling_1_0`, `kling_lip_sync`.

**В проекте:** это единственное video-семейство с отдельной matrix по model/variant/resolution/duration и различиями standard/native audio/video input/motion/effects/lip sync.

**Ограничение аудита:** публичная официальная pricing page Kling блокирует автоматическое чтение, а API response cost в проекте не сохраняется как источник истины. Поэтому соответствие чисел прямому account tariff не доказано.

**Вердикт:** структура расчёта разумная, но ставки требуют сверки с Kuaishou/Kling billing dashboard или invoice API. Generic reference surcharge поверх matrix применять нельзя без отдельного тарифного правила.

## Музыка

### Google Lyria — `google_lyria_3_clip`, `google_lyria_3_pro`

**Провайдер списывает:** `$0.04` за 30-second clip и `$0.08` за full song. Prompt/style/lyrics не тарифицируются отдельно.

**В проекте:** `6 ⚡` и `12 ⚡`, что точно соответствует 50% наценке.

**Вердикт:** корректно.

### `google_lyria_realtime`

**В проекте:** experimental model имеет произвольную fixed цену `10 ⚡`. Подтверждённой публичной per-request ставки нет.

**Вердикт:** неподтверждённый тариф; должен быть blocked до определения метрики session/audio duration.

### Suno — `suno_chirp_3_5`, `suno_chirp_4_0`, `suno_chirp_4_5`, `suno_chirp_4_5_plus`, `suno_chirp_5`, `suno_chirp_5_5`

**Фактический поставщик проекта:** не прямой Suno API, а сторонний `https://udioapi.pro/api/v2/generate`.

**В проекте:** fixed `8/10/12/14/16/18 ⚡`; комментарий прямо говорит, что значения назначены относительно Lyria до подтверждения тарифа агрегатора.

**Вердикт:** цены нельзя считать аудированными по Suno, пока не получен тариф udioapi.pro. Большой prompt/style/lyrics влияют только если агрегатор считает tokens/credits по request payload; локальный код этого не знает.

### MiniMax Music — `minimax_music_2_5`

**Фактический поставщик проекта:** тот же сторонний `udioapi.pro`, endpoint `/v2/minimax/generate`, не прямой MiniMax.

**В проекте:** произвольные `10 ⚡`. MiniMax Music удалён из Token Plan с 20 августа 2026 года; это не доказывает прекращение стороннего PAYG, но делает старую оценку ещё менее надёжной.

**Вердикт:** тариф неподтверждён, нужен invoice/API usage агрегатора.

## Озвучка и аудио

### ElevenLabs direct

Модели: `elevenlabs_eleven_v3`, `elevenlabs_multilingual_v2`, `elevenlabs_flash_v2_5`, `elevenlabs_flash_v2`, `elevenlabs_turbo_v2_5`, `elevenlabs_turbo_v2`, `elevenlabs_english_sts_v2`, `elevenlabs_multilingual_sts_v2`.

**Провайдер списывает:** v3 и Multilingual — `$0.10/1K chars`; Flash/Turbo — `$0.05/1K chars`; Voice Changer/Isolation/SFX — по минутам; Dubbing — по source audio minutes. Response headers возвращают `character-cost`.

**В проекте:** все TTS-модели считаются одинаково как `2 ⚡` за каждые 50 chars (`40 ⚡/1K`), что намного выше тарифа direct ElevenLabs. Все non-TTS tools блокируются как unpriced; STS-модели автоматически переводятся в STS и затем блокируются.

**Вердикт:** безопасно по отсутствию бесплатных non-TTS вызовов, но TTS сильно завышен и не различает model tiers. Использовать `character-cost`/точный model tariff.

### Runway audio — `runway_eleven_multilingual_v2` и tools

**Провайдер списывает:** TTS — 1 Runway credit/50 chars; SFX — 1/sec или 2 flat; isolation — 1/6 sec; dubbing — 1/2 sec; STS — 1/3 sec. Один Runway credit = `$0.01`.

**В проекте:** почти везде умножается на `2 ⚡` за provider credit вместо применения общей формулы 1.5 с округлением только итоговой суммы.

**Вердикт:** примерно 33% лишней наценки сверх заявленных 50%.

### Gemini TTS — `gemini_3_1_flash_tts_preview`, `gemini_2_5_flash_preview_tts`, `gemini_2_5_pro_preview_tts`

**Провайдер списывает:** text input tokens + audio output tokens. Для 3.1 Flash TTS `$1/M` text input и `$20/M` audio output; audio соответствует 25 tokens/sec. 2.5 variants также имеют token-based input/output ставки.

**В проекте:** ошибочно считается как 15/30 credits за миллион **символов**, output audio duration полностью игнорируется. Обычно срабатывает минимум `1 ⚡` независимо от длины записи.

**Вердикт:** критический недоучёт. Нужен output audio token usage или измеренная duration × 25 tokens/sec плюс input tokens.

## Текст и мультимодальный чат

### Что сделано правильно

- В reservation входят system prompt, до 10 сообщений истории, prompt пользователя, document text и верхняя граница image tokens.
- После ответа используются provider-reported input/output usage; reasoning/thinking включаются в output для Gemini.
- При меньшем фактическом usage разница reservation возвращается пользователю.
- Audio/video attachments блокируются до вызова, потому что для них нет настроенного тарифа.

Следовательно, **длинный prompt, скрытый style/system prompt, история и фото действительно влияют на итоговое списание в Text**, если provider usage присутствует и ставка модели корректна.

### Проблемы общей реализации

1. Cached input не выделяется из total input и оплачивается пользователем как uncached input.
2. Tiered/long-context ставки отсутствуют; одна пара тарифов применяется ко всему запросу.
3. Региональный/priority/service-tier коэффициент не учитывается.
4. Если provider не вернул usage, пользователь платит весь worst-case reservation, а не фактическую стоимость.
5. Image tokens входят только через aggregate usage; это правильно, но нельзя применять одновременно generic reference surcharge.

### OpenAI text

Модели: `gpt-5.6`, `gpt-5.5`, `gpt-5`, `gpt-5-mini`, `gpt-4.1`, `gpt-4.1-mini`, `gpt-4o`, `gpt-4o-mini`.

**Charge drivers:** все input tokens (system/style/history/user/image), cached input по отдельной сниженной ставке, output и reasoning tokens; у очень длинных contexts возможны другие ставки.

**Проект:** базовые uncached rates в основном соответствуют текущим short-context list prices. Не учитываются cached input и long-context tiers. `gpt-5.6` 4/20 сейчас совпадает с официальной promotional ставкой.

### Google text

Модели: `gemini_3_1_pro`, `gemini_3_1_flash`, `gemini_2_5_pro`, `gemini_2_5_flash`.

**Charge drivers:** input tokens по modality, output + thinking tokens, context cache; у Pro ставка меняется при prompt >200K. Grounding/Search, если будет включён, добавляет per-query fee.

**Проект:** short-context rates в основном правильны; long-context Pro tiers и cache отсутствуют. Для фото aggregate usage учитывает image tokens. Прямые audio/video requests пока блокируются.

### xAI text

Модели UI: `grok_4_1`, `grok_4_fast`, `grok_3`.

**Charge drivers:** input/cached/output/reasoning tokens; long context после threshold удваивает ставки; priority ×2; US regional endpoint ×1.1; server tools имеют per-call fees. Exact cost доступен в `usage.cost_in_usd_ticks`.

**Проект:** model IDs и rates относятся к прежнему каталогу, тогда как текущий публичный каталог — Grok 4.6/4.5/4.3/4.20. Exact cost игнорируется, long context/priority/region/tools отсутствуют.

**Вердикт:** пиновать текущие provider IDs или регулярно синхронизировать каталог; settle по `cost_in_usd_ticks`.

### Qwen text

Модели: `qwen_plus`, `qwen_turbo`, `qwen_max`.

**Charge drivers:** input/output tokens; для Plus/Max есть context tiers, thinking output может стоить иначе, cache/batch имеют скидки.

**Проект:** `qwen_turbo 0.05/0.20` совпадает с international standard. `qwen_plus 0.40/1.60` не соответствует alias: current non-thinking output `$1.20`, thinking `$4.00`, а >256K применяется `$1.20/$3.60/$12.00`. `qwen_max 1.60/6.40` устарел относительно текущего alias. В request Qwen thinking явно не отключён.

**Вердикт:** существенный риск и overcharge, и undercharge в зависимости от thinking/context.

### BytePlus text

Модель: `byteplus_seed_2_lite` → `seed-2-0-lite-260228`.

**Charge drivers:** input/output tokens, cache, context tier; image/video/audio input включаются в multimodal tokens при поддержке модели.

**Проект:** thinking явно отключён; standard short-context `0.25/2.00` соответствует тарифу. Для >128K должны применяться `0.50/4.00`; это не реализовано. Text UI сейчас не отправляет image vision в BytePlus, поэтому reference-фото там фактически не участвует.

## Приоритет исправлений

### P0 — остановить гарантированно неверные маршруты

1. Скрыть/заблокировать Sora 2/Pro, Imagen 4, Runway Gen3A/Aleph и Luma Dream Machine.
2. Убрать глобальный `REFERENCE_CREDITS`; reference cost должен принадлежать provider/model/operation calculator.
3. Дедуплицировать refs по нормализованному URL/asset ID до любого расчёта.
4. Исправить Gemini TTS на input/output token billing.
5. Разделить direct Google Veo и Runway-hosted Veo pricing.

### P1 — settlement по фактической стоимости

1. Сохранять provider usage/cost metadata для всех media jobs.
2. xAI: использовать `usage.cost_in_usd_ticks` для text/image/video.
3. Runway: использовать realized credits/model из response metadata.
4. OpenAI/Google image: использовать token usage.
5. ElevenLabs: использовать `character-cost` и duration/source-minute metrics.
6. При отсутствии exact cost применять provider-specific estimator; generic estimator запрещён.

### P2 — точные калькуляторы

1. FLUX.2: отдельное округление MP каждого output/reference.
2. Seedream 5 Pro: refs со второго.
3. Wan/Seedance/Grok/Luma video: input video duration и operation type.
4. Text: cached tokens, context tier, thinking mode, region/service tier.
5. HeyGen: expected speech duration reserve + actual generated seconds settlement.

### P3 — неподтверждённые контракты

До получения реальных billing данных заблокировать либо пометить как `pricing_not_configured`:

- все Suno models через `udioapi.pro`;
- `minimax_music_2_5` через `udioapi.pro`;
- `google_lyria_realtime`;
- direct Kling rates, если нет выгрузки тарифа account;
- MiniMax Hailuo 2.3, если account не возвращает usage/cost.

## Требуемая модель данных для безопасного биллинга

Каждый job должен сохранять:

- `provider`, точный `provider_model`, endpoint/region/service tier;
- нормализованный prompt token count;
- список уникальных refs с type, pixels/MP или duration;
- output count, resolution, quality, duration, audio, operation type;
- provider request ID;
- provider-reported usage/cost/credits;
- estimated provider cost, actual provider cost, variance;
- зарезервированные и окончательно списанные SYLVEX credits;
- версию тарифа и URL официального источника.

Правильный поток: **provider-specific worst-case reserve → API call → provider usage/cost settlement → возврат разницы или безопасное доначисление в пределах подтверждённого пользователю maximum**.

## Официальные источники

- OpenAI pricing and models: https://developers.openai.com/api/docs/pricing
- OpenAI Image generation: https://developers.openai.com/api/docs/guides/image-generation/
- OpenAI deprecations: https://developers.openai.com/api/docs/deprecations
- Google Gemini pricing: https://ai.google.dev/gemini-api/docs/pricing
- Google deprecations: https://ai.google.dev/gemini-api/docs/deprecations
- xAI pricing: https://docs.x.ai/developers/pricing
- xAI exact cost tracking: https://docs.x.ai/developers/cost-tracking
- Alibaba/Qwen/Wan pricing: https://www.alibabacloud.com/help/en/model-studio/model-pricing
- BytePlus ModelArk pricing: https://docs.byteplus.com/en/docs/modelark/model-pricing
- Black Forest Labs pricing: https://bfl.ai/pricing?category=flux.2
- Recraft API pricing: https://www.recraft.ai/pricing?tab=api
- Ideogram pricing: https://ideogram.ai/pricing/?tool=ideogram
- Runway pricing: https://docs.dev.runwayml.com/guides/pricing/
- Runway changelog: https://docs.dev.runwayml.com/api-details/api_changelog/
- Luma Agents pricing: https://docs.agents.lumalabs.ai/guides/pricing
- Luma migration: https://docs.agents.lumalabs.ai/guides/videos/migration/
- HeyGen API pricing explanation: https://help.heygen.com/en/articles/10060327-heygen-api-pricing-explained
- ElevenLabs API pricing: https://elevenlabs.io/pricing/api
- PixVerse pricing: https://docs.platform.pixverse.ai/pricing-796039m0

## Границы проверки

- Проверены все model IDs, доступные в текущих image/video/music/voice/text каталогах проекта.
- Публичная Kling pricing page не была доступна для машинной проверки; для окончательного подтверждения Kling нужна выгрузка billing dashboard/API текущего аккаунта.
- Тариф Suno и MiniMax Music определяется сторонним `udioapi.pro`, поэтому официальный тариф самих Suno/MiniMax не подтверждает стоимость конкретного ключа агрегатора.
- Никакие цены и provider routes в коде в рамках этого аудита не изменялись.
