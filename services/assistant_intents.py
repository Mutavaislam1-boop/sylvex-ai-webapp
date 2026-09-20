"""SYLVEX Assistant - Guide Mode deterministic intent router and templates.

Guide Mode never calls OpenAI (see /api/web/assistant/message in main.py -
the subscription check happens BEFORE this module is ever invoked, and this
module makes no network calls of its own at all). It is a scored,
data-driven intent matcher: keywords and phrases are weighted per intent,
the highest-scoring intent above a confidence floor becomes primary, other
intents scoring above a lower floor become secondary action hints. This is
deliberately not a chain of per-keyword if/elif branches - adding a new
intent means adding one entry to INTENTS, not new control flow.

Every response is centralized here (never scattered across frontend JS),
returned as plain text + structured actions - never raw HTML - so the
frontend can render safely without interpreting user-influenced strings as
markup. Action routes are internal Website paths only.
"""
import re


def _action(label, kind, **kwargs):
    action = {"label": label, "type": kind}
    action.update(kwargs)
    return action


def open_route(label, route):
    return _action(label, "open_route", route=route)


def open_pro_studio(label="Open Pro Studio", mode=None, model=None):
    return _action(label, "open_pro_studio", mode=mode or "", model=model or "")


def upgrade_action(label="Upgrade to SYLVEX Pro"):
    return _action(label, "open_subscription_modal")


WELCOME = {
    "id": "WELCOME",
    "text": (
        "Welcome to SYLVEX.\n\n"
        "SYLVEX lets you create images, video, music, voice and text, work with AI models, "
        "and build complete projects in Pro Studio. I can help you choose a tool, explain how "
        "SYLVEX works, or show you how to turn your idea into a finished project."
    ),
    "actions": [
        open_route("What can SYLVEX do?", "/assistant.html?q=what+can+sylvex+do"),
        open_pro_studio("Create an image", mode="image"),
        open_pro_studio("Create a video", mode="video"),
        open_pro_studio("Open Pro Studio"),
        open_route("Explore AI models", "/pro-studio.html?view=tools"),
        upgrade_action("SYLVEX Pro"),
    ],
}

FALLBACK = {
    "id": "FALLBACK",
    "text": (
        "I can help you learn how to create images, video, voice, music and text in SYLVEX, "
        "choose an AI model, understand Pro Studio, pricing, credits or subscriptions.\n\n"
        "What would you like to work with?"
    ),
    "actions": [
        open_pro_studio("Images", mode="image"),
        open_pro_studio("Video", mode="video"),
        open_pro_studio("Voice", mode="voice"),
        open_pro_studio("Music", mode="music"),
        open_route("Pro Studio", "/pro-studio.html"),
        open_route("Pricing", "/store.html"),
    ],
}

# Each intent: id, priority (lower = more specific, wins ties/near-ties),
# keywords {word: weight}, phrases {phrase: weight}, text, actions,
# subscription_cta (bool - whether this response IS or ends with an upgrade nudge).
INTENTS = [
    {
        "id": "GREETING", "priority": 5,
        "keywords": {"hi": 3, "hello": 3, "hey": 3, "yo": 2, "sup": 2},
        "phrases": {"good morning": 4, "good afternoon": 4, "good evening": 4, "how are you": 3},
        "text": "Hey! I'm SYLVEX Assistant. Ask me anything about creating images, video, voice, music or text, or tell me what you're trying to make.",
        "actions": [
            open_route("What can SYLVEX do?", "/assistant.html?q=what+can+sylvex+do"),
            open_pro_studio("Create an image", mode="image"),
            open_pro_studio("Create a video", mode="video"),
        ],
    },
    {
        "id": "THANKS", "priority": 5,
        "keywords": {"thanks": 3, "thank": 3, "thx": 3, "appreciate": 2},
        "phrases": {"thank you": 4},
        "text": "You're welcome! Let me know if there's anything else you'd like to create or explore.",
        "actions": [],
    },
    {
        "id": "WHAT_IS_SYLVEX", "priority": 10,
        "keywords": {"sylvex": 2, "platform": 1, "app": 1},
        "phrases": {"what is sylvex": 5, "what does sylvex do": 5, "how does sylvex work": 5, "tell me about sylvex": 4},
        "text": (
            "SYLVEX is an all-in-one AI creation platform. You can generate images, video, music, "
            "voice and text using leading AI models, keep consistent characters and objects across "
            "projects, and work in Pro Studio - a full creative workspace with Grid Mode for "
            "multi-step projects."
        ),
        "actions": [open_pro_studio("Open Pro Studio"), open_route("Explore AI models", "/pro-studio.html?view=tools"), upgrade_action("SYLVEX Pro")],
    },
    {
        "id": "PRICING", "priority": 3,
        "keywords": {"price": 3, "prices": 3, "pricing": 3, "cost": 3, "costs": 3, "expensive": 2, "cheap": 2, "fee": 2},
        "phrases": {"how much does it cost": 6, "how much does video cost": 6, "how much is a subscription": 6, "what does it cost": 5, "how much are credits": 5, "how much": 3},
        "text": (
            "SYLVEX Pro is a monthly or yearly subscription that unlocks unlimited generations, a "
            "priority queue and every AI model in Pro Studio. If you'd rather pay as you go, credit "
            "packages let you buy generations individually with no subscription."
        ),
        "actions": [open_route("View Pricing", "/store.html"), open_route("View Credit Packages", "/store.html"), upgrade_action()],
    },
    {
        "id": "SUBSCRIPTION", "priority": 4,
        "keywords": {"subscription": 3, "subscribe": 3, "pro": 1, "upgrade": 3, "plan": 1, "monthly": 2, "yearly": 2},
        "phrases": {"sylvex pro": 4, "become a subscriber": 5, "upgrade my account": 5, "unlock ai assistant": 5, "try sylvex pro": 5},
        "text": (
            "SYLVEX Pro unlocks unlimited generations, priority processing, every AI model in Pro "
            "Studio, and the full AI-powered SYLVEX Assistant - real conversation, file analysis and "
            "voice mode. You can subscribe monthly or yearly right here."
        ),
        "actions": [upgrade_action("Upgrade to SYLVEX Pro"), open_route("View Pricing", "/store.html")],
        "subscription_cta": True,
    },
    {
        "id": "CREDITS", "priority": 3,
        "keywords": {"credit": 3, "credits": 3, "balance": 3, "token": 1, "buy": 1, "topup": 3},
        "phrases": {"how do i buy credits": 6, "buy credits": 5, "add credits": 5, "how do credits work": 5, "what are credits": 4, "top up": 4, "top-up": 4},
        "text": (
            "Credits (⚡) are SYLVEX's pay-as-you-go currency - each generation costs a set number of "
            "credits depending on the mode and model. Credits never expire and work across every Pro "
            "Studio mode. You can buy a credit package any time from the Store."
        ),
        "actions": [open_route("View Credit Packages", "/store.html"), open_route("Open Profile", "/account/profile.html")],
    },
    {
        "id": "PAYMENTS", "priority": 4,
        "keywords": {"payment": 3, "paypal": 3, "card": 1, "billing": 3, "invoice": 2, "refund": 2},
        "phrases": {"payment methods": 5, "how do i pay": 5, "can i pay with card": 5, "payment failed": 4},
        "text": (
            "SYLVEX accepts payment through PayPal, including direct credit/debit card checkout - you "
            "don't need a PayPal account to pay by card. Apple Pay and Google Pay are available when "
            "supported by your device."
        ),
        "actions": [open_route("View Pricing", "/store.html"), open_route("Open Profile", "/account/profile.html")],
    },
    {
        "id": "IMAGE_TO_VIDEO", "priority": 6,
        "keywords": {"animate": 3},
        "phrases": {"animate a photo": 6, "turn image into video": 6, "image to video": 6, "animate my picture": 6, "photo to video": 6, "bring a photo to life": 6, "animate this": 5},
        "text": (
            "You can animate any photo into a short video clip - upload or select an image in Pro "
            "Studio's Video mode and choose an image-to-video model. It works great combined with a "
            "generated voiceover."
        ),
        "actions": [open_pro_studio("Open Image-to-Video", mode="video"), open_pro_studio("Open Pro Studio")],
    },
    {
        "id": "VIDEO", "priority": 8,
        "keywords": {"video": 3, "clip": 2, "movie": 2, "footage": 2},
        "phrases": {"create a video": 5, "make a video": 5, "generate a video": 5, "video generation": 4},
        "text": (
            "SYLVEX Video generation turns a text prompt (or a reference image) into a video clip "
            "using leading AI video models. Open Pro Studio's Video mode, describe the shot, and "
            "choose a model that fits your style and budget."
        ),
        "actions": [open_pro_studio("Open Video Models", mode="video"), open_pro_studio("Open Pro Studio")],
    },
    {
        "id": "IMAGE", "priority": 8,
        "keywords": {"image": 3, "photo": 1, "picture": 1, "art": 1, "artwork": 1, "illustration": 1},
        "phrases": {"create an image": 5, "generate an image": 5, "make a picture": 5, "ai art": 4},
        "text": (
            "SYLVEX Image generation creates original images from a text prompt using several AI "
            "image models, with support for consistent characters, objects and reference images."
        ),
        "actions": [open_pro_studio("Open Image Models", mode="image"), open_pro_studio("Open Pro Studio")],
    },
    {
        "id": "TEXT", "priority": 8,
        "keywords": {"write": 2, "writing": 1, "copywriting": 2},
        "phrases": {"write text": 5, "generate text": 5, "ai writing": 4, "write a script": 5},
        "text": "SYLVEX Text generation can write copy, scripts, captions and more using AI text models - open Pro Studio's Text mode and describe what you need.",
        "actions": [open_pro_studio("Open Text Models", mode="text"), open_pro_studio("Open Pro Studio")],
    },
    {
        "id": "VOICE", "priority": 7,
        "keywords": {"voice": 3, "voiceover": 3, "narration": 2, "speech": 1, "tts": 3},
        "phrases": {"add a voice": 5, "create a voiceover": 5, "text to speech": 5, "ai voice": 4},
        "text": "SYLVEX Voice generation turns text into natural speech, and can also add a voiceover to an existing video or image project.",
        "actions": [open_pro_studio("Open Voice Models", mode="voice"), open_pro_studio("Open Pro Studio")],
    },
    {
        "id": "MUSIC", "priority": 7,
        "keywords": {"music": 3, "song": 2, "soundtrack": 2, "melody": 2, "beat": 1},
        "phrases": {"create music": 5, "generate a song": 5, "make a soundtrack": 5, "ai music": 4},
        "text": "SYLVEX Music generation creates original songs and soundtracks from a text description - genre, mood and instrumentation all included.",
        "actions": [open_pro_studio("Open Music Models", mode="music"), open_pro_studio("Open Pro Studio")],
    },
    {
        "id": "PROMPT_HELP", "priority": 5,
        "keywords": {"prompt": 3, "wording": 1},
        "phrases": {"help me write a prompt": 6, "write a prompt": 5, "prompt ideas": 5, "how do i prompt": 5, "good prompt": 4},
        "text": (
            "A strong prompt usually names: the subject, the setting, the style or mood, and any "
            "specific details (lighting, camera angle, colors). For example: 'a cozy coffee shop "
            "interior, warm morning light, shot on 35mm film, inviting atmosphere.'\n\n"
            "For a custom prompt built specifically around your idea, SYLVEX Pro's AI Assistant can "
            "write and refine one with you."
        ),
        "actions": [open_pro_studio("Open Pro Studio"), upgrade_action()],
        "subscription_cta": True,
    },
    {
        "id": "PRO_STUDIO", "priority": 6,
        "keywords": {"prostudio": 3, "studio": 1},
        "phrases": {"what is pro studio": 6, "how does pro studio work": 6, "open pro studio": 5},
        "text": (
            "Pro Studio is SYLVEX's full creative workspace - generate images, video, voice, music "
            "and text side by side, reuse characters and objects across a project, and chain steps "
            "together in Grid Mode for multi-part productions."
        ),
        "actions": [open_pro_studio("Open Pro Studio")],
    },
    {
        "id": "GRID_MODE", "priority": 4,
        "keywords": {"grid": 3},
        "phrases": {"what is grid mode": 6, "grid mode": 5},
        "text": "Grid Mode lets you lay out a multi-step project - several images, video segments or a full storyboard - side by side in Pro Studio, keeping everything organized in one workspace.",
        "actions": [open_pro_studio("Open Pro Studio", mode="grid")],
    },
    {
        "id": "CHARACTERS", "priority": 5,
        "keywords": {"character": 3, "characters": 3, "persona": 2},
        "phrases": {"create a character": 5, "character consistency": 5, "save a character": 5},
        "text": "SYLVEX Characters let you save a consistent character's look once and reuse it across every generation - image, video or grid project - without re-describing it each time.",
        "actions": [open_pro_studio("Learn About Characters"), open_pro_studio("Open Pro Studio")],
    },
    {
        "id": "OBJECTS", "priority": 5,
        "keywords": {"object": 3, "objects": 3, "product": 1},
        "phrases": {"create an object": 5, "product placement": 5, "save an object": 5},
        "text": "SYLVEX Objects work like Characters, but for products or items - save a reference once (a bottle, a logo, a piece of furniture) and reuse it consistently across generations.",
        "actions": [open_pro_studio("Learn About Objects"), open_pro_studio("Open Pro Studio")],
    },
    {
        "id": "TOOLS", "priority": 6,
        "keywords": {"tool": 1, "tools": 1, "faceswap": 3, "upscale": 3, "upscaling": 3},
        "phrases": {"ai tools": 4, "face swap": 5, "remove background": 5, "upscale an image": 5},
        "text": "SYLVEX AI Tools cover face swap, background removal, upscaling and other one-click utilities alongside the main generators.",
        "actions": [open_route("Open AI Tools", "/ai-tools.html")],
    },
    {
        "id": "AI_MODELS", "priority": 6,
        "keywords": {"model": 1, "models": 1},
        "phrases": {"which models": 5, "what models are available": 5, "ai models": 4, "video models": 4, "image models": 4, "best model": 4},
        "text": "SYLVEX gives you access to a curated catalog of leading AI models for every mode - image, video, voice, music and text - so you can pick the one that fits your project.",
        "actions": [open_route("Explore AI Models", "/pro-studio.html?view=tools")],
    },
    {
        "id": "FILES", "priority": 5,
        "keywords": {"file": 1, "upload": 3, "attach": 2, "document": 2, "pdf": 2},
        "phrases": {"upload a file": 5, "upload a photo": 4, "analyze this file": 5, "attach a document": 5},
        "text": (
            "You can attach a photo or document right here in SYLVEX Assistant - use the + button "
            "next to the message box. Real file and document analysis (summarizing, extracting "
            "prompts, understanding a reference photo) is available with SYLVEX Pro."
        ),
        "actions": [upgrade_action("Unlock SYLVEX Pro")],
        "subscription_cta": True,
    },
    {
        "id": "ACCOUNT", "priority": 8,
        "keywords": {"account": 1, "profile": 1, "settings": 1, "password": 2},
        "phrases": {"my account": 4, "change my email": 5, "update my profile": 5, "my settings": 4},
        "text": "You can manage your email, password and linked accounts from your SYLVEX profile and settings pages.",
        "actions": [open_route("Open Profile", "/account/profile.html")],
    },
    {
        "id": "HISTORY", "priority": 6,
        "keywords": {"history": 3, "past": 1, "previous": 1, "generations": 2},
        "phrases": {"where is my history": 6, "my past generations": 5, "view my history": 5},
        "text": "Every generation you've made is saved in your history - open Pro Studio and check the History view, or find your recent items in the sidebar here.",
        "actions": [open_route("View History", "/pro-studio.html?view=history")],
    },
    {
        "id": "HELP", "priority": 9,
        "keywords": {"help": 1, "support": 1, "stuck": 1, "confused": 1},
        "phrases": {"i need help": 4, "can you help me": 4, "how does this work": 4},
        "text": "I'm here to help. I can explain how SYLVEX works, help you choose a tool or model, or point you toward pricing, credits and your account.",
        "actions": [open_route("What can SYLVEX do?", "/assistant.html?q=what+can+sylvex+do"), open_pro_studio("Open Pro Studio")],
    },
]

_INTENTS_BY_ID = {intent["id"]: intent for intent in INTENTS}

MIN_CONFIDENCE = 3
SECONDARY_THRESHOLD = 3
MAX_SECONDARY = 2

_SYNONYMS = {
    "pic": "image", "pics": "images", "picture": "image", "pictures": "images",
    "vid": "video", "vids": "videos", "clip": "video", "movie": "video",
    "voiceover": "voice", "narration": "voice",
    "song": "music", "soundtrack": "music",
    "pricing": "price", "costs": "cost",
}

_PUNCT_RE = re.compile(r"[^\w\s]")
_WS_RE = re.compile(r"\s+")


def normalize(message):
    text = (message or "").lower().strip()
    text = _PUNCT_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text).strip()
    if not text:
        return text
    words = [_SYNONYMS.get(w, w) for w in text.split(" ")]
    return " ".join(words)


def _score(normalized, intent):
    score = 0.0
    words = normalized.split(" ") if normalized else []
    word_set = set(words)
    for kw, weight in intent.get("keywords", {}).items():
        if kw in word_set:
            score += weight
    for phrase, weight in intent.get("phrases", {}).items():
        if phrase in normalized:
            score += weight
    return score


def route_intent(message):
    """Score `message` against every intent; return the routing decision.

    Returns {"primary": intent_dict, "secondary": [intent_dict, ...]} -
    "primary" is always a full intent dict (falls back to FALLBACK), never
    None, so callers never need a null check.
    """
    normalized = normalize(message)
    if not normalized:
        return {"primary": FALLBACK, "secondary": []}

    scored = []
    for intent in INTENTS:
        s = _score(normalized, intent)
        if s > 0:
            scored.append((s, intent["priority"], intent))

    if not scored:
        return {"primary": FALLBACK, "secondary": []}

    # Highest score wins; ties broken by priority (lower = more specific).
    scored.sort(key=lambda row: (-row[0], row[1]))
    top_score, _, top_intent = scored[0]
    if top_score < MIN_CONFIDENCE:
        return {"primary": FALLBACK, "secondary": []}

    secondary = [
        intent for score, _, intent in scored[1:]
        if score >= SECONDARY_THRESHOLD and intent["id"] != top_intent["id"]
    ][:MAX_SECONDARY]

    return {"primary": top_intent, "secondary": secondary}


def intent_by_id(intent_id):
    return _INTENTS_BY_ID.get(intent_id)
