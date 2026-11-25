"""Placeholder risograph-style art for ViewDeals (two spot colors, grain, misregistration).

Writes assets/art/cat-*.svg, event-*.svg, share-*.svg, lead-texture.svg and marks/*.svg.
Every file carries a PLACEHOLDER comment and a small corner mark until the commissioned set arrives.
"""
import sys
from pathlib import Path

ART = Path(sys.argv[1])
(ART / "marks").mkdir(parents=True, exist_ok=True)
PAPER, INK, RED = "#F4EFE6", "#161412", "#D7261E"

GRAIN = """<filter id="g" x="0" y="0" width="100%" height="100%"><feTurbulence type="fractalNoise" baseFrequency="1.4" numOctaves="1" seed="SEED" result="n"/><feColorMatrix in="n" type="matrix" values="0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 -2.4 2.25" result="m"/><feComposite in="SourceGraphic" in2="m" operator="in"/></filter>"""

# Drawings in a 480x320 box: (red fills, ink line work)
D = {
"tech": (
  '<rect x="128" y="150" width="58" height="96" rx="22"/><rect x="294" y="150" width="58" height="96" rx="22"/>',
  '<path d="M140 176 C138 82 342 82 340 176"/><path d="M152 172 C152 104 328 104 328 172"/>'
  '<rect x="124" y="146" width="58" height="96" rx="22"/><rect x="298" y="146" width="58" height="96" rx="22"/>'
  '<path d="M384 168 q14 26 0 52 M402 156 q24 38 0 76 M96 168 q-14 26 0 52 M78 156 q-24 38 0 76"/>'),
"home": (
  '<path d="M170 128 h120 v104 q0 30 -30 30 h-60 q-30 0 -30 -30z"/>',
  '<path d="M166 124 h124 v108 q0 32 -32 32 h-60 q-32 0 -32 -32z"/><path d="M290 150 q46 0 46 34 t-46 34"/>'
  '<path d="M130 276 h220"/><path d="M200 104 q-12 -18 0 -36 t0 -36 M232 104 q-12 -18 0 -36 t0 -36 M264 104 q-12 -18 0 -36 t0 -36"/>'),
"smart-home": (
  '<path d="M150 170 L240 98 L330 170 V262 H150z"/>',
  '<path d="M126 178 L240 86 L354 178"/><path d="M150 160 V262 H330 V160"/><rect x="214" y="200" width="52" height="62"/>'
  '<path d="M196 150 q44 -36 88 0 M210 166 q30 -22 60 0"/><circle cx="240" cy="180" r="5"/>'),
"beauty": (
  '<path d="M206 110 q4 -46 34 -60 q30 14 30 60z"/><rect x="290" y="150" width="70" height="112" rx="4"/>',
  '<path d="M202 112 q4 -50 38 -64 q34 14 34 64z"/><rect x="196" y="112" width="84" height="40"/><rect x="186" y="152" width="104" height="112"/>'
  '<rect x="286" y="146" width="70" height="116" rx="4"/><path d="M296 128 v18 M316 120 v26 M336 128 v18 M120 266 h260"/>'),
"toys": (
  '<rect x="176" y="96" width="128" height="64"/>',
  '<rect x="120" y="164" width="128" height="64"/><rect x="248" y="164" width="128" height="64"/><rect x="172" y="92" width="128" height="68"/>'
  '<path d="M140 164 v-12 h24 v12 M196 164 v-12 h24 v12 M268 164 v-12 h24 v12 M324 164 v-12 h24 v12 M196 92 v-12 h24 v12 M252 92 v-12 h24 v12 M104 232 h288"/>'),
"outdoors": (
  '<circle cx="340" cy="92" r="40"/><path d="M150 262 L232 130 L314 262z"/>',
  '<path d="M60 262 L160 150 L214 206 M292 172 L330 140 L420 262"/><path d="M146 262 L232 124 L318 262"/><path d="M232 124 L232 262 M210 262 L232 214 L254 262"/>'
  '<path d="M40 266 h400"/><circle cx="344" cy="88" r="40"/>'),
"fashion": (
  '<path d="M170 124 l38 -22 q32 22 64 0 l38 22 l-18 46 l-22 -10 v118 h-60 v-118 l-22 10z"/>',
  '<path d="M240 62 q0 -22 16 -22 q16 0 16 16 M240 62 L130 112 h220 L240 62"/>'
  '<path d="M166 120 l40 -22 q34 22 68 0 l40 22 l-18 48 l-22 -10 v120 h-128 v-120 l-22 10z"/>'),
"events": (
  '<path d="M200 96 h150 v128 h-150 l-44 -64z"/>',
  '<path d="M196 92 h154 v136 h-154 l-48 -68z"/><circle cx="200" cy="160" r="10"/><path d="M190 160 q-70 -10 -98 -70"/>'
  '<path d="M236 136 h84 M236 160 h64 M236 184 h76"/>'),
"black-friday": (
  '<path d="M150 130 h180 l14 132 h-208z"/>',
  '<path d="M146 126 h188 l16 140 h-220z"/><path d="M196 126 v-24 q0 -34 44 -34 q44 0 44 34 v24"/><path d="M188 190 l104 0 M200 220 l80 0"/>'),
"cyber-monday": (
  '<rect x="150" y="90" width="180" height="120"/>',
  '<rect x="144" y="84" width="192" height="132" rx="4"/><path d="M110 236 h260 l-16 26 h-228z"/><path d="M236 130 l0 48 l14 -14 l12 24 l10 -5 l-12 -23 l20 -2z"/>'),
"prime-day": (
  '<path d="M140 140 h200 v120 h-200z"/>',
  '<path d="M136 136 h208 v128 h-208z M136 136 l34 -40 h140 l34 40 M240 96 v40"/><path d="M214 136 v36 h52 v-36"/><path d="M164 236 h60"/>'),
"back-to-school": (
  '<path d="M120 200 L300 80 L330 120 L150 240z"/>',
  '<path d="M116 196 L300 74 L332 120 L148 242z M116 196 L98 262 L148 242 M300 74 L316 64 L344 108 L332 120"/>'
  '<rect x="180" y="250" width="220" height="30"/><path d="M200 250 v12 M220 250 v8 M240 250 v12 M260 250 v8 M280 250 v12 M300 250 v8 M320 250 v12 M340 250 v8 M360 250 v12"/>'),
"holiday-gifts": (
  '<rect x="160" y="150" width="160" height="112"/>',
  '<rect x="156" y="146" width="168" height="118"/><rect x="146" y="118" width="188" height="30"/><path d="M240 118 v146"/>'
  '<path d="M240 118 q-60 -60 -70 -14 q-4 22 70 14 q60 -60 70 -14 q4 22 -70 14"/>'),
"spring-sales": (
  '<circle cx="240" cy="132" r="34"/>',
  '<circle cx="240" cy="132" r="18"/><path d="M240 96 q-26 -34 0 -50 q26 16 0 50 M276 132 q34 -26 50 0 q-16 26 -50 0 M240 168 q26 34 0 50 q-26 -16 0 -50 M204 132 q-34 26 -50 0 q16 -26 50 0"/>'
  '<path d="M240 218 v52 M240 250 q30 -26 52 -10 q-22 26 -52 10"/><path d="M150 270 h180"/>'),
}

NAMES = {"tech": "Tech", "home": "Home", "smart-home": "Smart Home", "beauty": "Beauty", "toys": "Toys",
         "outdoors": "Outdoors", "fashion": "Fashion", "events": "Sale Events", "black-friday": "Black Friday",
         "cyber-monday": "Cyber Monday", "prime-day": "Prime Day", "back-to-school": "Back to School",
         "holiday-gifts": "Holiday Gifts", "spring-sales": "Spring Sales"}


def drawing(key, seed):
    red, ink = D[key]
    return (f'<g filter="url(#g)"><g fill="{RED}" transform="translate(5 4)">{red}</g>'
            f'<g fill="none" stroke="{INK}" stroke-width="7" stroke-linecap="round" stroke-linejoin="round">{ink}</g></g>')


def tile(key, seed):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="480" height="320" viewBox="0 0 480 320">
<!-- PLACEHOLDER ART: replace with the commissioned risograph illustration -->
<defs>{GRAIN.replace("SEED", str(seed))}</defs>
<rect width="480" height="320" fill="{PAPER}"/>
{drawing(key, seed)}
<text x="468" y="310" text-anchor="end" font-family="Arial,sans-serif" font-size="11" fill="{INK}" opacity=".45">placeholder</text>
</svg>
'''


def share(key, seed, title):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630">
<!-- PLACEHOLDER SHARE IMAGE: replace with the commissioned design -->
<defs>{GRAIN.replace("SEED", str(seed))}</defs>
<rect width="1200" height="630" fill="{PAPER}"/>
<rect x="40" y="40" width="1120" height="550" fill="none" stroke="{INK}" stroke-width="3"/>
<text x="88" y="150" font-family="Georgia,serif" font-size="44" font-weight="700" fill="{INK}">ViewDeals</text>
<path d="M88 172 h420" stroke="{INK}" stroke-width="3"/>
<text x="88" y="300" font-family="Georgia,serif" font-size="76" font-weight="700" fill="{INK}">{title}</text>
<text x="88" y="370" font-family="Georgia,serif" font-size="34" font-style="italic" fill="{RED}">Hand-picked deals, checked daily</text>
<g transform="translate(640 120) scale(1.15)">{drawing(key, seed)}</g>
<text x="1140" y="575" text-anchor="end" font-family="Arial,sans-serif" font-size="16" fill="{INK}" opacity=".45">placeholder</text>
</svg>
'''


seed = 1
for key in D:
    prefix = "event" if key in ("black-friday", "cyber-monday", "prime-day", "back-to-school", "holiday-gifts", "spring-sales") else "cat"
    (ART / f"{prefix}-{key}.svg").write_text(tile(key, seed), encoding="utf-8", newline="\n")
    share_name = f"share-{key}.svg" if prefix == "event" else f"share-cat-{key}.svg"
    (ART / share_name).write_text(share(key, seed, NAMES[key]), encoding="utf-8", newline="\n")
    seed += 1
(ART / "share-home.svg").write_text(share("events", 99, "Today’s best deals"), encoding="utf-8", newline="\n")

# Lead-story texture: halftone dots in tag red, very light.
(ART / "lead-texture.svg").write_text(
    f'<svg xmlns="http://www.w3.org/2000/svg" width="400" height="200" viewBox="0 0 400 200"><!-- PLACEHOLDER lead texture -->'
    f'<defs><pattern id="h" width="12" height="12" patternUnits="userSpaceOnUse" patternTransform="rotate(18)">'
    f'<g fill="{RED}"><circle cx="3" cy="3" r="1.6"/><circle cx="9" cy="9" r="1.1"/></g></pattern></defs>'
    f'<rect width="400" height="200" fill="url(#h)" opacity=".2"/></svg>\n', encoding="utf-8", newline="\n")

# Annotation marks: single strokes in currentColor, inlined by the build so they can draw themselves.
MARKS = {
 "circle": ("0 0 240 120", '<path pathLength="1" d="M200 22 C150 4 52 8 20 46 C-6 80 60 112 130 108 C200 104 236 78 228 50 C220 24 170 14 120 16"/>'),
 "underline": ("0 0 240 24", '<path pathLength="1" d="M4 14 C40 6 70 18 110 12 S190 6 236 12"/>'),
 "arrow": ("0 0 160 120", '<path pathLength="1" d="M8 112 C20 60 60 24 140 18 M112 4 L142 18 L118 42"/>'),
 "starburst": ("0 0 120 120", '<path pathLength="1" d="M60 6 L70 40 L104 22 L84 54 L116 66 L80 74 L94 108 L64 86 L46 116 L44 80 L8 88 L34 62 L6 40 L42 42 L36 8 L56 38z"/>'),
 "bracket": ("0 0 40 200", '<path pathLength="1" d="M34 4 C14 6 14 20 16 60 C18 92 8 98 4 100 C8 102 18 108 16 140 C14 180 14 194 34 196"/>'),
 "checkmark": ("0 0 100 80", '<path pathLength="1" d="M6 44 L36 72 L94 6"/>'),
 "editors-pick": ("0 0 220 64", '<text class="mark__script" x="6" y="40" font-size="34">editor’s pick</text><path pathLength="1" d="M8 52 C60 46 140 56 200 48"/>'),
 "last-chance": ("0 0 220 64", '<text class="mark__script" x="6" y="40" font-size="34">last chance</text><path pathLength="1" d="M8 52 C60 58 140 44 200 52"/>'),
}
for name, (vb, body) in MARKS.items():
    (ART / "marks" / f"{name}.svg").write_text(
        f'<svg class="mark mark--{name}" xmlns="http://www.w3.org/2000/svg" viewBox="{vb}" fill="none" stroke="currentColor" '
        f'stroke-width="4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">'
        f'<!-- PLACEHOLDER mark -->{body}</svg>\n', encoding="utf-8", newline="\n")
print("art written")
