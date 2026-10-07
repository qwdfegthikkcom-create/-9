"""يصنع أيقونة الموقع (تظهر في تبويب المتصفح وعلى شاشة الهاتف) من شعار «واجهة»: حرف «و» ذهبي داخل قوس على عنابي.
التشغيل (مرة واحدة، أو إذا تغيّر الشعار أو الألوان):
  python3 tools/make_icons.py

يكتب في مجلد brand/:
  icon.svg      الأيقونة الأساسية (رسم متّجه، حادّة بأي حجم)
  icon-32.png   للمتصفحات التي لا تقبل SVG
  icon-180.png  لشاشة الهاتف الرئيسية (apple-touch-icon)
ثم شغّل python3 build.py، فهو يضمّنها في index.html. ارفع ملفات brand/ مع التغيير.

حرف «و» يُؤخذ من خط El Messiri نفسه بوزن 700 (مثل الشعار في الشريط العلوي)، والألوان من --bg و--gold
في :root داخل src/page.src.html، فلا تُكتب في مكان آخر.
يحتاج fontTools (pip install fonttools brotli) وPlaywright (أو المتغيرين PLAYWRIGHT وCHROMIUM).
"""
import json, os, pathlib, re, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / 'brand'
FONT = ROOT / 'fonts' / 'el-messiri' / 'files' / 'el-messiri-arabic-wght-normal.woff2'

try:
    from fontTools.ttLib import TTFont
    from fontTools.pens.svgPathPen import SVGPathPen
    from fontTools.pens.boundsPen import BoundsPen
    from fontTools.varLib.instancer import instantiateVariableFont
except ImportError:
    sys.exit('هذه الأداة تحتاج fontTools. ثبّتها بالأمر:\n  pip install fonttools brotli')


def color(name):
    src = (ROOT / 'src' / 'page.src.html').read_text(encoding='utf-8')
    m = re.search(r'--%s:\s*(#[0-9a-fA-F]{6})\s*;' % name, src)
    if not m:
        sys.exit('لم أجد --%s بلون مثل #2a0d14 في :root داخل src/page.src.html' % name)
    return m.group(1).lower()


def waw_path():
    """شكل حرف «و» من El Messiri بوزن 700، مع حدوده."""
    font = instantiateVariableFont(TTFont(FONT), {'wght': 700})
    glyphs = font.getGlyphSet()
    name = font.getBestCmap()[ord('و')]
    pen = SVGPathPen(glyphs)
    glyphs[name].draw(pen)
    bounds = BoundsPen(glyphs)
    glyphs[name].draw(bounds)
    return pen.getCommands(), bounds.bounds


def svg(bg, gold):
    d, (x0, y0, x1, y1) = waw_path()
    S = 64                      # مربع 64×64، يصغر ويكبر بلا تشويه
    aw, ah = 40, 50             # القوس: أعلاه نصف دائرة وقاعدته مستقيمة، بنسبة شعار الشريط العلوي تقريباً
    ax, ay = (S - aw) / 2, (S - ah) / 2 + 1
    w, h = x1 - x0, y1 - y0
    scale = 26 / max(w, h)
    gx = S / 2 - (x0 + w / 2) * scale
    gy = ay + ah * 0.62 + (y0 + h / 2) * scale  # محور y في الخط معكوس
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {S} {S}">'
            '<rect width="{S}" height="{S}" rx="14" fill="{bg}"/>'
            '<path d="M{ax:g} {ab:g}V{at:g}a{r:g} {r:g} 0 0 1 {aw} 0V{ab:g}z" fill="none" stroke="{gold}" stroke-width="3"/>'
            '<path transform="translate({gx:.2f} {gy:.2f}) scale({sc:.5f} {nsc:.5f})" fill="{gold}" d="{d}"/>'
            '</svg>\n').format(S=S, bg=bg, gold=gold, ax=ax, ab=ay + ah, at=ay + aw / 2, r=aw / 2, aw=aw,
                               gx=gx, gy=gy, sc=scale, nsc=-scale, d=d)


# يرسم الأيقونة بكروميوم ويحفظها PNG بالأحجام المطلوبة. الخلفية العنابية تملأ المربع كله،
# لأن الهاتف يدوّر زوايا أيقونة الشاشة الرئيسية بنفسه
RENDER = r'''
const { chromium } = require(process.env.PLAYWRIGHT || 'playwright');
const [svg, bg, out, sizes] = JSON.parse(process.argv[1]);
(async () => {
  const b = await chromium.launch({ executablePath: process.env.CHROMIUM || undefined });
  const uri = 'data:image/svg+xml,' + encodeURIComponent(svg);
  for (const s of sizes) {
    const p = await b.newPage({ viewport: { width: s, height: s } });
    await p.setContent(`<body style="margin:0;background:${bg}"><img src="${uri}" width="${s}" height="${s}" style="display:block">`);
    await p.screenshot({ path: `${out}/icon-${s}.png` });
    await p.close();
  }
  await b.close();
})().catch(e => { console.error(e.message); process.exit(1); });
'''


def main():
    bg, gold = color('bg'), color('gold')
    OUT.mkdir(exist_ok=True)
    text = svg(bg, gold)
    (OUT / 'icon.svg').write_text(text, encoding='utf-8')
    r = subprocess.run(['node', '-e', RENDER, json.dumps([text, bg, str(OUT), [32, 180]])],
                       cwd=ROOT, capture_output=True, text=True, env=os.environ)
    if r.returncode:
        sys.exit('تعذّر رسم الأيقونات PNG (هل Playwright مثبت؟):\n' + (r.stdout + r.stderr).strip())
    for f in ('icon.svg', 'icon-32.png', 'icon-180.png'):
        print('brand/%s' % f, (OUT / f).stat().st_size, 'bytes')
    print('شغّل الآن python3 build.py')


if __name__ == '__main__':
    main()
