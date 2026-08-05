"""把 Achievement.icon 从 emoji 字符换成 iconify 图标名。

机房里的 Chrome 91 之类的老浏览器缺 emoji 字体，emoji 会渲染成方块。
iconify 出来的是 SVG，跟浏览器字体无关。

映射到 noto（Noto Color Emoji 的 SVG 版），视觉上和原 emoji 基本一致。
表里没有的 emoji 保持原值不动，前端会按纯文本兜底渲染，之后在管理后台手工补。
"""

from django.db import migrations

# 带 ️（variation selector-16）的 emoji 后台可能存成带或不带两种形态，
# 迁移时统一去掉再查表，所以这里的 key 一律不带 ️
EMOJI_TO_ICONIFY = {
    # 计划里首批成就用到的
    "🌱": "noto:seedling",
    "📗": "noto:green-book",
    "📚": "noto:books",
    "📅": "noto:calendar",
    "🗓": "noto:spiral-calendar",
    "🌐": "noto:globe-with-meridians",
    "🎖": "noto:military-medal",
    "🎯": "noto:direct-hit",
    "🏹": "noto:bow-and-arrow",
    "🦉": "noto:owl",
    "🌙": "noto:crescent-moon",
    "💥": "noto:collision",
    "🔥": "noto:fire",
    "⚡": "noto:high-voltage",
    "✂": "noto:scissors",
    "📜": "noto:scroll",
    "💎": "noto:gem-stone",
    "🏆": "noto:trophy",
    "❓": "noto:red-question-mark",
    # 其余常用图标，后台可能已经用上了
    "❔": "noto:white-question-mark",
    "📖": "noto:open-book",
    "🥇": "noto:1st-place-medal",
    "🥈": "noto:2nd-place-medal",
    "🥉": "noto:3rd-place-medal",
    "🏅": "noto:sports-medal",
    "⭐": "noto:star",
    "🌟": "noto:glowing-star",
    "✨": "noto:sparkles",
    "🎉": "noto:party-popper",
    "🎊": "noto:confetti-ball",
    "🚀": "noto:rocket",
    "💡": "noto:light-bulb",
    "🐛": "noto:bug",
    "👑": "noto:crown",
    "🥷": "noto:ninja",
    "🧠": "noto:brain",
    "💪": "noto:flexed-biceps",
    "🎓": "noto:graduation-cap",
    "📈": "noto:chart-increasing",
    "🎁": "noto:wrapped-gift",
    "🔮": "noto:crystal-ball",
    "🦄": "noto:unicorn",
    "🐢": "noto:turtle",
    "☕": "noto:hot-beverage",
    "🌈": "noto:rainbow",
    "⏰": "noto:alarm-clock",
    "📝": "noto:memo",
    "✅": "noto:check-mark-button",
    "🔒": "noto:locked",
    "🎮": "noto:video-game",
    "🧩": "noto:puzzle-piece",
    "🔧": "noto:wrench",
    "🐍": "noto:snake",
    "💻": "noto:laptop",
    "⌨": "noto:keyboard",
    "☀": "noto:sun",
    "😴": "noto:sleeping-face",
    "🤖": "noto:robot",
    "🔍": "noto:magnifying-glass-tilted-left",
    "🎨": "noto:artist-palette",
    "⚔": "noto:crossed-swords",
    "🛡": "noto:shield",
    "🏰": "noto:castle",
    "🗿": "noto:moai",
    "🌊": "noto:water-wave",
    "🍀": "noto:four-leaf-clover",
    "🔁": "noto:repeat-button",
    "🎪": "noto:circus-tent",
    "🦅": "noto:eagle",
    "🐉": "noto:dragon",
    "💫": "noto:dizzy",
    "🧭": "noto:compass",
    "🪄": "noto:magic-wand",
    "🔔": "noto:bell",
    "📌": "noto:pushpin",
    "🏁": "noto:chequered-flag",
    "🎢": "noto:roller-coaster",
}

ICONIFY_TO_EMOJI = {v: k for k, v in EMOJI_TO_ICONIFY.items()}


def _convert(apps, schema_editor, table):
    Achievement = apps.get_model("achievement", "Achievement")
    updated = []
    for a in Achievement.objects.all():
        key = (a.icon or "").replace("️", "").strip()
        new = table.get(key)
        if new and new != a.icon:
            a.icon = new
            updated.append(a)
    if updated:
        Achievement.objects.bulk_update(updated, ["icon"])


def emoji_to_iconify(apps, schema_editor):
    _convert(apps, schema_editor, EMOJI_TO_ICONIFY)


def iconify_to_emoji(apps, schema_editor):
    _convert(apps, schema_editor, ICONIFY_TO_EMOJI)


class Migration(migrations.Migration):
    dependencies = [("achievement", "0001_initial")]

    operations = [migrations.RunPython(emoji_to_iconify, iconify_to_emoji)]
