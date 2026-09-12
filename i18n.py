"""Minimal i18n: Chinese/English UI text with runtime switching.

Usage:
    import i18n
    i18n.set_lang("zh")            # or "en"
    label = i18n.tr("Start Game")  # key == the English source text
"""

from constants import (PLANT_PEASHOOTER, PLANT_SUNFLOWER, PLANT_WALLNUT,
                       PLANT_CHERRYBOMB, PLANT_FUMESHROOM, PLANT_LILYPAD,
                       PLANT_SNOWPEA)

_current = "zh"

# zh: Chinese translations. Any text without a key falls back to the key (en).
_ZH = {
    "Day": "白天",
    "Night": "夜晚",
    "Pool": "池塘",
    "Fog": "迷雾",
    "Roof": "屋顶",

    # --- menu ---
    "Start Game": "开始游戏",
    "How to Play": "玩法说明",
    "Quit": "退出",
    "Python Edition": "Python 复刻版",
    "Click a seed packet, then click the lawn to plant": "点击种子卡，再点击草坪即可种植",
    "Click falling suns to collect them": "点击落下的阳光进行收集",
    "Select Game Mode": "选择游戏模式",
    "Adventure": "冒险模式",
    "Survival": "生存模式",
    "Adventure Mode": "冒险模式",
    "Survival Mode": "生存模式",
    "Endless waves": "无尽波次",
    "Classic day lawn": "经典白天草坪",
    "Dark with mushrooms": "黑暗蘑菇之夜",
    "Water with lily pads": "池塘与睡莲",
    "Thick fog rolls in": "浓雾弥漫",
    "On the roof": "屋顶战场",
    "Click to go back": "点击返回",
    "Click card to select  |  Backspace to return": "点击卡片进入 ｜ 退格键返回",
    "LOCKED": "未解锁",
    "16 levels, 5 worlds": "16 个关卡 · 5 大场景",
    "Level 1-1": "关卡 1-1",
    "BOSS: The Zomboss": "Boss：僵王博士",
    "plants": "植物",
    "waves": "波次",

    # --- seed select ---
    "Choose your plants": "选择你的植物",
    "Available plants — click to include in your pack:": "可用植物 —— 点击加入背包：",
    "IN PACK": "已选择",
    "off": "未选",
    "Start!": "开始！",
    "Back": "返回",
    "1-6 keys pick seeds in-game · Space skips the wait between waves": "对局中按 1-6 选种子 · 空格跳过波次等待",
    "Collect falling plant food, then click a plant to feed it": "点击收集掉落的能量豆，再点击植物使用它",
    "Speed x2": "2倍速",
    "Your pack": "你的背包",

    # --- in-game states ---
    "Game Over!": "游戏结束！",
    "Click to return to menu": "点击返回主菜单",
    "Victory! You saved the house!": "胜利！你守住了房子！",
    "Click to play again": "点击返回继续游玩",
    "PAUSED": "已暂停",
    "Press P to resume": "按 P 恢复",
    "Click to return": "点击返回",
    "Resume": "继续游戏",
    "Restart": "重新开始",
    "Main Menu": "主菜单",
    "Retry": "再试一次",
    "Next Level": "下一关",
    "Back to Map": "返回关卡地图",

    # --- tooltips / cards ---
    "Cost": "阳光",
    "Cooldown": "冷却",
    "Shovel: dig up a plant": "铲子：铲除植物",
    "Shoots peas at zombies in its lane": "向本行发射豌豆攻击僵尸",
    "Produces extra sun for your defense": "定期产出阳光，经济核心",
    "A tough shell that blocks zombies": "坚硬外壳，阻挡僵尸前进",
    "Explodes all zombies in a 3x3 area": "炸毁 3×3 范围内的所有僵尸",
    "Sprays fumes that damage zombies": "喷出毒雾伤害僵尸",
    "Grows on water and carries one plant": "种在水面上，可承载一株植物",
    "Plant again on the same plant to upgrade (max Lv3)": "在同一株植物上再种同款即可升级（最高3级）",

    # --- plant food / new zombies ---
    "Plant food!": "能量豆！",
    "Plant food storage is full!": "能量豆已满！",
    "A Bungee Zombie stole your plant!": "蹦极僵尸偷走了你的植物！",
    "Already at max level!": "已是最高等级！",

    # --- messages ---
    "Not enough sun!": "阳光不足！",
    "Plant cooling down!": "植物冷却中！",
    "Cell occupied!": "该格已有植物！",
    "Need a Lily Pad first!": "请先种下睡莲！",
    "Lily Pads only grow on water!": "睡莲只能种在水面上！",
    "Night! No sun falls from the sky. Plant Sunflowers!": "夜晚！天上不会掉阳光，快种向日葵吧！",
    "Sound ON": "声音已开启",
    "Sound OFF": "声音已关闭",
    "Click seed → Click lawn. Collect sun. Stop zombies!": "点种子 → 点草坪种植；收集阳光；阻止僵尸！",
    "Level complete!": "关卡完成！",
    "The zombies ate your brains!": "僵尸吃掉了你的脑子！",
    "Survived": "坚持了",
    "waves!": "波！",
    "record": "最高纪录",
    "new record!": "新纪录！",

    # --- wave banners ---
    "Here They Come!": "僵尸来袭！",
    "A Huge Wave of Zombies!": "一大波僵尸正在靠近！",
    "is Approaching!": "即将来袭！",
    "FINAL WAVE!": "最后一波！",
    "Brace yourself!": "做好准备！",
    "Wave": "第",
    "Get ready! Next wave in": "准备！下一波还有",
    "s": "秒",
    "Next wave:": "下一波：",
    "Survival: Wave": "生存：第",
    "collected!": "已收集！",
    "FIRE!": "开火！",
    "BOOM!": "轰！",
    "*fizzle*": "*哑火*",
    "Fullscreen": "全屏",

    # --- shovel / toolbar tooltip words used in hover ---
    "HP:": "生命：",
    "Zombie": "普通僵尸",
    "Conehead Zombie": "路障僵尸",
    "Flag Zombie": "旗帜僵尸",
    "Buckethead Zombie": "铁桶僵尸",
    "Newspaper Zombie": "读报僵尸",
    "Pole Vaulting Zombie": "撑杆僵尸",
    "Zomboss": "僵王博士",
    "Plant": "植物",
    "Cooling down...": "冷却中…",
    "Lily Pad": "睡莲",
}

# plant type → localized name
_PLANT_ZH = {
    PLANT_PEASHOOTER: "豌豆射手",
    PLANT_SUNFLOWER: "向日葵",
    PLANT_WALLNUT: "坚果墙",
    PLANT_CHERRYBOMB: "樱桃炸弹",
    PLANT_FUMESHROOM: "大喷菇",
    PLANT_LILYPAD: "睡莲",
    PLANT_SNOWPEA: "寒冰射手",
}
_PLANT_EN = {
    PLANT_PEASHOOTER: "Peashooter",
    PLANT_SUNFLOWER: "Sunflower",
    PLANT_WALLNUT: "Wall-nut",
    PLANT_CHERRYBOMB: "Cherry Bomb",
    PLANT_FUMESHROOM: "Fume-shroom",
    PLANT_LILYPAD: "Lily Pad",
    PLANT_SNOWPEA: "Snow Pea",
}


def set_lang(lang):
    global _current
    _current = "zh" if lang == "zh" else "en"


def get_lang():
    return _current


def is_zh():
    return _current == "zh"


def tr(text):
    """Translate the English source text into the current language."""
    if _current == "en":
        return text
    return _ZH.get(text, text)


def plant_name(plant_type):
    table = _PLANT_ZH if _current == "zh" else _PLANT_EN
    return table.get(plant_type, plant_type)


def zombie_name(zombie_type):
    if _current == "zh":
        names = {
            "basic": "普通僵尸",
            "conehead": "路障僵尸",
            "flag": "旗帜僵尸",
            "buckethead": "铁桶僵尸",
            "newspaper": "读报僵尸",
            "pole": "撑杆僵尸",
            "boss": "僵王博士",
            "balloon": "气球僵尸",
            "bungee": "蹦极僵尸",
            "tactician": "战术僵尸",
            "digger": "矿工僵尸",
            "healer": "治疗僵尸",
            "commander": "指挥官僵尸",
        }
        return names.get(zombie_type, "僵尸")
    return {
        "basic": "Zombie",
        "conehead": "Conehead Zombie",
        "flag": "Flag Zombie",
        "buckethead": "Buckethead Zombie",
        "newspaper": "Newspaper Zombie",
        "pole": "Pole Vaulting Zombie",
        "boss": "Zomboss",
        "balloon": "Balloon Zombie",
        "bungee": "Bungee Zombie",
        "tactician": "Tactician Zombie",
        "digger": "Digger Zombie",
        "healer": "Healer Zombie",
        "commander": "Commander Zombie",
    }.get(zombie_type, "Zombie")


# ---- formatting helpers for number-embedded strings ----
def fmt_wave(n):
    return f"第 {n} 波" if _current == "zh" else f"Wave {n}"


def fmt_next_wave(secs):
    return f"下一波：{secs:.0f} 秒" if _current == "zh" else f"Next wave: {secs:.0f}s"


def fmt_survival_wave(n):
    return f"生存：第 {n} 波" if _current == "zh" else f"Survival: Wave {n}"


def fmt_get_ready(secs):
    return f"准备！下一波还有 {secs:.0f} 秒" if _current == "zh" else f"Get ready! Next wave in {secs:.0f}s"


def fmt_level_up(level):
    return f"升级！Lv{level}" if _current == "zh" else f"Level up! Lv{level}"


def fmt_level_name(raw):
    """'Level 1-3' → '关卡 1-3' (zh) or unchanged (en)."""
    if _current == "en":
        return raw
    if raw.startswith("Level "):
        return "关卡 " + raw[len("Level "):]
    return _ZH.get(raw, raw)


# ---------------------------------------------------------------
# Font handling — CJK glyphs need a real system font, pygame's
# default font can't draw Chinese. Cache per size.
# ---------------------------------------------------------------
import os
import pygame

_FONT_CANDIDATES = [
    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 "assets", "fonts", "NotoSansCJKsc-Regular.otf"),  # bundled
    "/System/Library/Fonts/PingFang.ttc",           # macOS
    "/System/Library/Fonts/STHeiti Light.ttc",       # macOS
    "/System/Library/Fonts/Hiragino Sans GB.ttc",    # macOS
    "C:/Windows/Fonts/msyh.ttc",                     # Windows
    "C:/Windows/Fonts/simhei.ttf",                   # Windows
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",# Linux
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
]
_font_path = None
_font_checked = False
_font_cache = {}


def _resolve_font():
    global _font_path, _font_checked
    if not _font_checked:
        _font_checked = True
        # 1) bundled CJK font file first (always present & reliable)
        for p in _FONT_CANDIDATES:
            if p and os.path.exists(p) and os.path.isfile(p):
                _font_path = p
                return _font_path
        # 2) then search installed font names
        try:
            pygame.font.init()
            names = pygame.font.get_fonts()
            for token in ("pingfang", "heiti", "hiragino", "songti", "stheiti",
                          "yahei", "simhei", "simsun", "msyh", "microhei",
                          "wenquanyi", "notosanscjk", "arialunicode"):
                for n in names:
                    if token in n:
                        _font_path = n  # SysFont name
                        return _font_path
        except Exception:
            pass
    return _font_path


def font(size):
    """Return a font that can render the current language's glyphs."""
    if _font_checked is False:
        _resolve_font()
    key = (_font_path, size)
    if key in _font_cache:
        return _font_cache[key]
    try:
        if _font_path:
            # _font_path is either a SysFont name or an absolute file path
            if _font_path.startswith(("/", "C:")):
                f = pygame.font.Font(_font_path, size)
            else:
                f = pygame.font.SysFont(_font_path, size)
        else:
            f = pygame.font.Font(None, size)
    except Exception:
        try:
            f = pygame.font.Font(None, size)
        except Exception:
            f = pygame.font.SysFont("arial", size)
    _font_cache[key] = f
    return f
