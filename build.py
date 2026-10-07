"""يبني index.html من src/page.src.html: يضمّن الخطوط (بعد تصغيرها إلى الحروف المستعملة فقط) والأيقونة،
ويولّد بطاقات الأعمال من works/works.json.
التشغيل: python3 build.py   (يحتاج: pip install fonttools brotli)

قبل الكتابة يفحص قائمة الأعمال وروابط واتساب. إذا وجد خطأ يطبعه ويتوقف دون أن يلمس index.html،
فيبقى الموقع المنشور سليماً كما هو.
"""
import base64, html, io, json, pathlib, re, struct, sys, urllib.parse

# تصغير الخطوط يحتاج fontTools وbrotli. بدونهما يتوقف البناء ولا يلمس index.html
try:
    import brotli  # noqa: F401  (يستخدمه fontTools لكتابة woff2)
    from fontTools import subset as font_subset
except ImportError:
    sys.exit('البناء يحتاج مكتبتي fontTools وbrotli لتصغير الخطوط المضمّنة. ثبّتهما بالأمر:\n'
             '  pip install fonttools brotli\n'
             'ثم أعد python3 build.py. لم يتغير index.html.')

root = pathlib.Path(__file__).resolve().parent
fonts_dir = root / 'fonts'

# ---------- الخطوط ----------
# الخطوط الأصلية في fonts/ تبقى كاملة. البناء يأخذ منها الحروف المستعملة في الصفحة فقط (مع الأساسيات أدناه)
# ويضمّنها، فيصغر الموقع كثيراً. إذا كتبت نصاً جديداً في src أو works.json تدخل حروفه تلقائياً في البناء التالي.
def faces(css_path, files_dir, keep=('arabic', 'latin')):
    """قواعد @font-face من ملف css، كل واحدة مع مسار ملف الخط الذي تشير إليه."""
    css = css_path.read_text(encoding='utf-8')
    out = []
    for block in re.findall(r'@font-face\s*\{[^}]*\}', css):
        m = re.search(r'url\(\.?/?files/([^)]+?\.woff2)\)', block)
        if not m:
            continue
        name = m.group(1)
        if not any(re.search(r'-%s-(wght|\d+)-normal\.woff2$' % k, name) for k in keep):
            continue
        out.append((block, files_dir / name))
    return out


fonts = []
em = fonts_dir / 'el-messiri'
fonts += faces(em / 'wght.css', em / 'files')
ib = fonts_dir / 'ibm-plex-sans-arabic'
for w in ('400', '600'):
    fonts += faces(ib / (w + '.css'), ib / 'files')
assert len(fonts) == 6, len(fonts)

# حروف تبقى في الخطوط دائماً، حتى لو لم تظهر في نص الصفحة: الإنجليزية الأساسية والأرقام،
# وعلامات الترقيم العربية والأرقام العربية (خطوات «طريقة العمل» تُرقَّم بها من CSS)، والتشكيل، وعلامات الاتجاه
ALWAYS = (list(range(0x20, 0x7F)) + [0xA0, 0xAB, 0xB7, 0xBB]
          + [0x060C, 0x061B, 0x061F, 0x0640, 0x06D4] + list(range(0x064B, 0x0653))
          + list(range(0x0660, 0x066E)) + list(range(0x06F0, 0x06FA))
          + list(range(0x200C, 0x2028)))


def used_chars(page):
    """كل الحروف التي قد تظهر في الصفحة: النص، وقيم content في CSS، ونصوص السكربت، مع فك &...; و\\XXXX و\\uXXXX."""
    chars = set(html.unescape(page))
    escapes = re.findall(r'\\u([0-9a-fA-F]{4})|\\u\{([0-9a-fA-F]{1,6})\}|\\([0-9a-fA-F]{1,6})', page)  # JS ثم CSS
    chars |= {chr(int(h, 16)) for e in escapes for h in e if h and int(h, 16) <= 0x10FFFF}
    return {ord(c) for c in chars if c.isprintable() or c in '\u200c\u200d\u200e\u200f'} | set(ALWAYS)


def subset(path, unicodes):
    """ملف الخط بالحروف المطلوبة فقط، woff2. يحتفظ بكل ميزات تشكيل الحروف العربية (layout_features='*').
    النتيجة ثابتة: نفس الحروف تعطي نفس الملف بايتاً ببايت، فلا يتغير index.html بلا سبب."""
    opts = font_subset.Options()
    opts.layout_features = ['*']
    opts.flavor = 'woff2'
    font = font_subset.load_font(str(path), opts)
    font.recalcTimestamp = False  # لا يكتب وقت البناء داخل الخط
    sub = font_subset.Subsetter(opts)
    sub.populate(unicodes=sorted(unicodes))
    sub.subset(font)
    out = io.BytesIO()
    font_subset.save_font(font, out, opts)
    return out.getvalue()


def font_css(unicodes):
    """قواعد @font-face الست، وكل خط مصغّر ومضمّن داخلها. يرجع النص وحجم الخطوط قبل التصغير وبعده."""
    blocks, before, after = [], 0, 0
    for block, path in fonts:
        data = subset(path, unicodes)
        before += path.stat().st_size
        after += len(data)
        src = "src: url(data:font/woff2;base64,%s) format('woff2');" % base64.b64encode(data).decode()
        blocks.append(re.sub(r'src:[^;]*;', lambda _: src, block, flags=re.S))
    return '\n'.join(blocks), before, after


# ---------- رأس الصفحة: الأيقونة ولون شريط المتصفح ونص المشاركة ----------
# الاسم والوصف كما يظهران في نتائج البحث وعند مشاركة رابط الموقع على واتساب وفيسبوك
SITE_NAME = 'واجهة ✦ Wajha Studio'
DESCRIPTION = ('واجهة Wajha Studio: منيوهات رقمية للمطاعم، ومواقع للعيادات والمحلات والمقاولين والمكاتب الهندسية، '
               'وفيديوهات ترويجية. عبدالله حمزه علي، الموصل.')
# رابط الموقع المنشور، ينتهي بـ / مثل https://example.github.io/site/ . اتركه فارغاً حتى يتأكد الرابط.
# حين يُكتب يضيف البناء صورة المشاركة og.jpg (تصنعها tools/og.cjs) والرابط الأساسي للصفحة.
SITE_URL = ''
# أيقونة الموقع من مجلد brand/ (تصنعها tools/make_icons.py)
ICONS_DIR = root / 'brand'


def head_meta(src):
    """وسوم <head> بعد العنوان. لون شريط المتصفح يُقرأ من --bg في :root، فيبقى مطابقاً للخلفية."""
    m = re.search(r'--bg:\s*(#[0-9a-fA-F]{3,8})\s*;', src)
    if not m:
        sys.exit('لم أجد --bg في :root داخل src/page.src.html (لون شريط المتصفح). لم يتغير index.html.')
    for f in ('icon.svg', 'icon-32.png', 'icon-180.png'):
        if not (ICONS_DIR / f).is_file():
            sys.exit('الأيقونة brand/%s غير موجودة. شغّل python3 tools/make_icons.py. لم يتغير index.html.' % f)
    svg = 'data:image/svg+xml,' + urllib.parse.quote((ICONS_DIR / 'icon.svg').read_text(encoding='utf-8').strip(), safe=' /:=,.-')
    png = lambda f: 'data:image/png;base64,' + base64.b64encode((ICONS_DIR / f).read_bytes()).decode()
    a = lambda s: html.escape(s, quote=True)
    lines = [
        '<meta name="description" content="%s">' % a(DESCRIPTION),
        '<meta name="theme-color" content="%s">' % m.group(1),
        '<meta name="color-scheme" content="dark">',
        '<link rel="icon" type="image/svg+xml" href="%s">' % a(svg),
        '<link rel="icon" type="image/png" sizes="32x32" href="%s">' % png('icon-32.png'),
        '<link rel="apple-touch-icon" href="%s">' % png('icon-180.png'),
        '<meta property="og:type" content="website">',
        '<meta property="og:locale" content="ar_IQ">',
        '<meta property="og:title" content="%s">' % a(SITE_NAME),
        '<meta property="og:description" content="%s">' % a(DESCRIPTION),
    ]
    if SITE_URL:
        if not re.fullmatch(r'https://[^\s"<>?#]+/', SITE_URL):
            sys.exit('SITE_URL يجب أن يبدأ بـ https:// وينتهي بـ / وبلا مسافات. لم يتغير index.html.')
        if not (root / 'og.jpg').is_file():
            sys.exit('og.jpg غير موجودة بجانب index.html. شغّل node tools/og.cjs. لم يتغير index.html.')
        lines += [
            '<link rel="canonical" href="%s">' % a(SITE_URL),
            '<meta property="og:url" content="%s">' % a(SITE_URL),
            '<meta property="og:image" content="%s">' % a(SITE_URL + 'og.jpg?v=1'),
            '<meta property="og:image:width" content="1200">',
            '<meta property="og:image:height" content="630">',
        ]
    # بطاقة كبيرة بالصورة حين توجد صورة مشاركة، وإلا بطاقة نصية
    lines.append('<meta name="twitter:card" content="%s">' % ('summary_large_image' if SITE_URL else 'summary'))
    return '\n'.join(lines)

# ---------- واتساب ----------
# رقم واتساب العمل بلا + ولا مسافات. تُبنى منه روابط الأعمال («أريد منيو مثل هذا» و«اسألني عن مثله»).
# الرقم مكتوب أيضاً في src/page.src.html (ثلاثة روابط، والرقم الظاهر، وvar value): إذا غيّرته فغيّره هناك معاً،
# والبناء يتوقف إذا وجد رابط wa.me برقم آخر.
WA_NUMBER = '9647747800611'


def wa(text):
    return 'https://wa.me/%s?text=%s' % (WA_NUMBER, urllib.parse.quote(text, safe=''))


# ---------- الأعمال ----------
KINDS = {'menu', 'site', 'video'}
STATUSES = {'ready', 'soon'}
LINK_TEXT = {'menu': 'افتح المنيو', 'site': 'افتح الموقع', 'video': 'شاهد الفيديو'}
IMAGE_TYPES = {'.webp': 'image/webp', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png'}
MAX_IMAGE = 400 * 1024
# لقطات الشاشة الحقيقية تحت العمل الجاهز (الحقل screens): حتى 4 لقطات، كل واحدة webp أو jpg وأقل من 60KB
SCREEN_TYPES = {'.webp': 'image/webp', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg'}
MAX_SCREENS = 4
MAX_SCREEN = 60 * 1024
# مجموع صور الأعمال المضمّنة في الصفحة (صورة كل عمل جاهز ولقطاته). إذا تجاوزه يتوقف البناء، حتى لا يثقل الموقع على الهاتف
IMAGES_BUDGET = 300 * 1024
FIELDS = {'id', 'kind', 'status', 'title', 'title_en', 'desc', 'points', 'note', 'link', 'link_text', 'image', 'image_alt',
          'featured', 'demo', 'screens'}
BANNED = ['العقد']  # كلمات لا تُكتب في النصوص التعريفية (من قواعد CLAUDE.md)

# زر واتساب تحت كل عمل جاهز: نص الزر، وما يُكتب في الرسالة بعد اسم العمل
WANT = {
    'menu': ('أريد منيو مثل هذا', 'وأريد منيو مثله لمحلّي.'),
    'site': ('أريد موقعاً مثل هذا', 'وأريد موقعاً مثله لنشاطي.'),
    'video': ('أريد فيديو مثل هذا', 'وأريد فيديو مثله لنشاطي.'),
}

# أيقونات أسطر «قريباً»، وهي نفسها أيقونات بطاقات الخدمات: هاتف للمنيو، ومتصفح للموقع، وزر تشغيل للفيديو
ICONS = {
    'menu': '<svg viewBox="0 0 24 24"><rect x="7" y="3" width="10" height="18" rx="2"/><path d="M10 8h4M10 11.5h4M10 15h2.5"/></svg>',
    'site': '<svg viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 9h18M7 13h5M7 16h3"/></svg>',
    'video': '<svg viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M10 9.5v5l4.5-2.5z"/></svg>',
}

# مصغّرات مرسومة تُستخدم حين لا توجد صورة حقيقية لعمل جاهز
PLACEHOLDER = {
    'site': '<div class="screen web"><i class="g"></i><i></i><i></i><i></i></div>',
    'menu': '<div class="screen phone"><i class="g"></i><i></i><i></i><i></i><i class="g"></i></div>',
    'video': '<div class="screen video"><i></i></div>',
}


def validate(works):
    errors = []
    if not isinstance(works, list) or not works:
        return ['works.json يجب أن يكون قائمة فيها عمل واحد على الأقل']
    seen = set()
    used = {}  # ملف الصورة ← id العمل الذي يستخدمه
    for n, w in enumerate(works, 1):
        where = 'العمل رقم %d' % n
        if not isinstance(w, dict):
            errors.append('%s: يجب أن يكون كائناً {...}' % where)
            continue
        where = '%s (%s)' % (where, w.get('id', 'بلا id'))
        for k in sorted(set(w) - FIELDS):
            errors.append('%s: حقل غير معروف «%s»' % (where, k))
        for k in ('id', 'kind', 'status', 'title', 'desc'):
            if not isinstance(w.get(k), str) or not w[k].strip():
                errors.append('%s: الحقل «%s» مطلوب ويجب أن يكون نصاً' % (where, k))
        wid = w.get('id', '')
        if isinstance(wid, str) and wid:
            if not re.fullmatch(r'[a-z0-9]+(-[a-z0-9]+)*', wid):
                errors.append('%s: id يُكتب بحروف إنجليزية صغيرة وأرقام وشَرطات فقط، مثل cafe-menu' % where)
            if wid in seen:
                errors.append('%s: id مكرر' % where)
            seen.add(wid)
        if w.get('kind') not in KINDS:
            errors.append('%s: kind يجب أن يكون menu أو site أو video' % where)
        if w.get('status') not in STATUSES:
            errors.append('%s: status يجب أن يكون ready أو soon' % where)
        pts = w.get('points', [])
        if not isinstance(pts, list) or not all(isinstance(p, str) and p.strip() for p in pts):
            errors.append('%s: points يجب أن تكون قائمة نصوص' % where)
            pts = []
        for k in ('title_en', 'link_text', 'image_alt'):
            if k in w and not isinstance(w[k], str):
                errors.append('%s: %s يجب أن يكون نصاً' % (where, k))
        if 'note' in w and not (isinstance(w['note'], str) and w['note'].strip()):
            errors.append('%s: note يجب أن يكون نصاً غير فارغ (احذف الحقل إذا لا تريده)' % where)
        link = w.get('link')
        if link is not None and not (isinstance(link, str) and re.fullmatch(r'https://[^\s"<>]+', link)):
            errors.append('%s: link يجب أن يبدأ بـ https:// وبلا مسافات' % where)
        img = w.get('image')
        if img is not None:
            p = root / img if isinstance(img, str) else None
            if p is None or not p.is_file():
                errors.append('%s: الصورة غير موجودة: %s' % (where, img))
            elif p.suffix.lower() not in IMAGE_TYPES:
                errors.append('%s: نوع الصورة غير مدعوم (webp أو jpg أو png)' % where)
            elif p.stat().st_size > MAX_IMAGE:
                errors.append('%s: الصورة أكبر من %d KB، صغّرها' % (where, MAX_IMAGE // 1024))
            if not (isinstance(w.get('image_alt'), str) and w['image_alt'].strip()):
                errors.append('%s: image_alt مطلوب مع الصورة (وصف قصير لما فيها)' % where)
        if 'featured' in w and not isinstance(w['featured'], bool):
            errors.append('%s: featured يجب أن يكون true أو false' % where)
        if 'demo' in w and not isinstance(w['demo'], bool):
            errors.append('%s: demo يجب أن يكون true أو false' % where)
        # لقطات الشاشة الحقيقية: قائمة من 1 إلى 4، كل لقطة {"image": ..., "alt": ...}
        screens = w.get('screens', [])
        if 'screens' in w and not (isinstance(screens, list) and 1 <= len(screens) <= MAX_SCREENS):
            errors.append('%s: screens قائمة من لقطة واحدة إلى %d لقطات (احذف الحقل إذا لا تريده)' % (where, MAX_SCREENS))
            screens = screens if isinstance(screens, list) else []
        alts = []
        files = [w.get('image')]
        for i, sc in enumerate(screens, 1):
            at = '%s: اللقطة رقم %d في screens' % (where, i)
            if not isinstance(sc, dict) or set(sc) != {'image', 'alt'}:
                errors.append('%s: تُكتب هكذا {"image": "works/images/...", "alt": "وصف اللقطة"}' % at)
                continue
            files.append(sc['image'])
            if isinstance(sc['alt'], str) and sc['alt'].strip():
                alts.append(sc['alt'])
            else:
                errors.append('%s: alt مطلوب (وصف قصير لما في اللقطة)' % at)
            p = root / sc['image'] if isinstance(sc['image'], str) and sc['image'] else None
            if p is None or not p.is_file():
                errors.append('%s: الصورة غير موجودة: %s' % (at, sc['image']))
            elif p.suffix.lower() not in SCREEN_TYPES:
                errors.append('%s: نوع الصورة غير مدعوم (webp أو jpg)' % at)
            elif p.stat().st_size > MAX_SCREEN:
                errors.append('%s: الصورة أكبر من %d KB، صغّرها' % (at, MAX_SCREEN // 1024))
            elif not image_size(p):
                errors.append('%s: تعذّرت قراءة أبعاد الصورة، احفظها من جديد webp أو jpg' % at)
        # كل ملف صورة لعمل واحد فقط، حتى لا تغيّر صورةُ عملٍ صورةَ عمل آخر
        for f in files:
            if isinstance(f, str) and f:
                if f in used:
                    errors.append('%s: الصورة %s مستخدمة مرتين (أيضاً في %s)' % (where, f, used[f]))
                used[f] = w.get('id', where)
        text = ' '.join(str(w.get(k, '')) for k in ('title', 'title_en', 'desc', 'note', 'link_text', 'image_alt')) + ' ' + ' '.join(pts + alts)
        for word in BANNED:
            if word in text:
                errors.append('%s: كلمة «%s» ممنوعة في النصوص التعريفية' % (where, word))
    return errors


def image_size(p):
    """عرض الصورة وارتفاعها من رأس الملف (webp أو jpg) بلا مكتبات إضافية، أو None إذا تعذّر."""
    b = p.read_bytes()
    if b[:4] == b'RIFF' and b[8:12] == b'WEBP':
        chunk = b[12:16]
        if chunk == b'VP8 ' and len(b) >= 30:
            w, h = struct.unpack('<HH', b[26:30])
            return w & 0x3fff, h & 0x3fff
        if chunk == b'VP8L' and len(b) >= 25:
            bits = int.from_bytes(b[21:25], 'little')
            return (bits & 0x3fff) + 1, ((bits >> 14) & 0x3fff) + 1
        if chunk == b'VP8X' and len(b) >= 30:
            return int.from_bytes(b[24:27], 'little') + 1, int.from_bytes(b[27:30], 'little') + 1
        return None
    if b[:2] == b'\xff\xd8':
        i = 2
        while i + 9 < len(b):
            if b[i] != 0xFF:
                i += 1
                continue
            m = b[i + 1]
            if m in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                h, w = struct.unpack('>HH', b[i + 5:i + 9])
                return w, h
            if m in (0xD8, 0x01, 0xFF) or 0xD0 <= m <= 0xD7:
                i += 2 if m != 0xFF else 1
                continue
            i += 2 + struct.unpack('>H', b[i + 2:i + 4])[0]
    return None


LATIN = re.compile(r"[0-9]*[A-Za-z][A-Za-z0-9.&'+-]*(?:\s+[A-Za-z0-9][A-Za-z0-9.&'+-]*)*")


def t(s):
    """نص آمن للـ HTML، والكلمات الإنجليزية داخل span باتجاه من اليسار إلى اليمين."""
    return LATIN.sub(lambda m: '<span class="ltr" lang="en">%s</span>' % m.group(0), html.escape(s.strip(), quote=False))


def data_uri(p, types):
    return 'data:%s;base64,%s' % (types[p.suffix.lower()], base64.b64encode(p.read_bytes()).decode())


def thumb(w):
    img = w.get('image')
    if not img:
        return '<div class="thumb" aria-hidden="true">%s</div>' % PLACEHOLDER[w['kind']]
    # وسم «نموذج عرض» فوق كل صورة حقيقية، إلا إذا كان demo: false (لعميل حقيقي فقط)
    badge = '<span class="thumb-badge">نموذج عرض</span>' if w.get('demo', True) else ''
    # الصورة مضمّنة في الصفحة نفسها، فلا فائدة من loading="lazy"
    return '<div class="thumb">%s<img src="%s" alt="%s" width="1200" height="750" decoding="async"></div>' % (
        badge, data_uri(root / img, IMAGE_TYPES), html.escape(w['image_alt']))


def tour(w, indent):
    """لقطات الشاشة الحقيقية (الحقل screens): شريط يُسحب أفقياً بلا جافاسكربت، ويُمرَّر بالأسهم بعد التركيز عليه."""
    screens = w.get('screens') or []
    if not screens:
        return []
    one = len(screens) == 1
    items = []
    for sc in screens:
        p = root / sc['image']
        width, height = image_size(p)
        items.append('%s    <li><img src="%s" alt="%s" width="%d" height="%d" decoding="async"></li>'
                     % (indent, data_uri(p, SCREEN_TYPES), html.escape(sc['alt']), width, height))
    # «من النموذج» لنموذج العرض، و«من العمل» لعميل حقيقي (demo: false)
    demo = w.get('demo', True)
    label = '%s حقيقية من %s' % ('لقطة' if one else 'لقطات', 'النموذج' if demo else 'العمل')
    name = '%s من %s%s' % ('لقطة' if one else 'لقطات', 'نموذج ' if demo else '', plain_title(w))
    return [
        '%s<p class="tour-label">%s</p>' % (indent, label),
        '%s<div class="tour" tabindex="0" role="region" aria-label="%s">' % (indent, html.escape(name)),
        '%s  <ul>' % indent,
    ] + items + ['%s  </ul>' % indent, '%s</div>' % indent]


def demo_attr(w):
    return '' if w.get('demo', True) else ' data-demo="false"'


def title(w):
    s = t(w['title'])
    if w.get('title_en'):
        s += ' <span class="ltr" lang="en">%s</span>' % html.escape(w['title_en'].strip())
    return s


def plain_title(w):
    """اسم العمل كما يُكتب في رسالة واتساب، مثل «منيو فور يو 4U»."""
    return ' '.join(x.strip() for x in (w['title'], w.get('title_en', '')) if x.strip())


NEW_WINDOW = '<span class="sr-only"> (يُفتح في نافذة جديدة)</span>'


def wa_link(w, cls, text, message):
    # اسم العمل مخفي لقارئ الشاشة، حتى لا تتشابه الروابط حين تُقرأ وحدها
    return '<a class="%s" href="%s" target="_blank" rel="noopener">%s<span class="sr-only">: %s (يُفتح في نافذة جديدة)</span></a>' % (
        cls, html.escape(wa(message)), text, title(w))


def link(w, cls):
    # الرابط يُفتح في نافذة جديدة، فنقول ذلك لقارئ الشاشة بنص مخفي
    return '<a class="%s" href="%s" target="_blank" rel="noopener">%s%s</a>' % (
        cls, html.escape(w['link']), t(w.get('link_text') or LINK_TEXT[w['kind']]), NEW_WINDOW)


def tag(w):
    return ('<span class="tag tag-solid">نموذج جاهز</span>' if w['status'] == 'ready'
            else '<span class="tag">قريباً</span>')


def feature(w):
    points = ''.join('\n              <li>%s</li>' % t(p) for p in w.get('points', []))
    lines = [
        '        <article class="feature reveal" data-kind="%s" id="work-%s"%s>' % (w['kind'], w['id'], demo_attr(w)),
        '          %s' % thumb(w),
        '          <div class="feature-body">',
        '            %s' % tag(w),
        '            <h3>%s</h3>' % title(w),
        '            <p>%s</p>' % t(w['desc']),
    ]
    if points:
        lines.append('            <ul>%s\n            </ul>' % points)
    if w.get('note'):
        lines.append('            <p class="feature-note">%s</p>' % t(w['note']))
    # زر فتح العمل (إن وُجد رابط)، ثم زر واتساب برسالة جاهزة تذكر اسم العمل
    text, want = WANT[w['kind']]
    buttons = [link(w, 'btn btn-line')] if w.get('link') else []
    buttons.append(wa_link(w, 'btn', text, 'مرحباً، رأيت نموذج «%s» في موقع واجهة، %s' % (plain_title(w), want)))
    lines.append('            <div class="feature-actions">%s\n            </div>' % ''.join('\n              ' + b for b in buttons))
    lines.append('          </div>')
    # اللقطات في شريط بعرض البطاقة كله تحت الصورة والنص، فلا تتمدد صورة العمل على الحاسوب
    shots = tour(w, '            ')
    if shots:
        lines += ['          <div class="feature-tour">'] + shots + ['          </div>']
    return '\n'.join(lines + ['        </article>'])


def card(w):
    lines = [
        '          <li class="work reveal" data-kind="%s" id="work-%s"%s>' % (w['kind'], w['id'], demo_attr(w)),
        '            %s' % thumb(w),
        '            <div class="work-body">',
        '              %s' % tag(w),
        '              <h3>%s</h3>' % title(w),
        '              <p>%s</p>' % t(w['desc']),
    ]
    if w.get('note'):
        lines.append('              <p class="feature-note">%s</p>' % t(w['note']))
    lines += tour(w, '              ')
    if w.get('link'):
        lines.append('              %s' % link(w, 'work-link'))
    return '\n'.join(lines + ['            </div>', '          </li>'])


def row(w):
    """عمل قادم: سطر مختصر بأيقونة، والعنوان ووسم «قريباً»، والوصف، ورابط سؤال عبر واتساب. بلا صورة."""
    ask = wa_link(w, 'soon-ask', 'اسألني عن مثله',
                  'مرحباً، رأيت «%s» ضمن الأعمال القادمة في موقع واجهة، وأريد الاستفسار عن عمل مثله لنشاطي.' % plain_title(w))
    return '\n'.join([
        '            <li class="soon-item" data-kind="%s" id="work-%s">' % (w['kind'], w['id']),
        '              <span class="soon-icon" aria-hidden="true">%s</span>' % ICONS[w['kind']],
        '              <h4>%s</h4>' % title(w),
        '              %s' % tag(w),
        '              <p>%s</p>' % t(w['desc']),
        '              %s' % ask,
        '            </li>',
    ])


def main():
    works_path = root / 'works' / 'works.json'
    try:
        works = json.loads(works_path.read_text(encoding='utf-8'))
    except json.JSONDecodeError as e:
        sys.exit('خطأ في كتابة works.json (سطر %d، عمود %d): %s\nلم يتغير index.html.' % (e.lineno, e.colno, e.msg))
    errors = validate(works)
    if errors:
        sys.exit('\n'.join(['أخطاء في works/works.json:'] + ['  - ' + e for e in errors] + ['لم يتغير index.html.']))

    # الجاهز يُعرض كبيراً (أو بطاقة صغيرة مع featured: false)، والقادم سطراً في قائمة «قريباً»
    ready = [w for w in works if w['status'] == 'ready']
    featured = [w for w in ready if w.get('featured', True)]
    cards = [w for w in ready if not w.get('featured', True)]
    soon = [w for w in works if w['status'] == 'soon']

    # حجم الصور المضمّنة: صورة كل عمل جاهز ولقطاته (القادم لا تظهر له صور)
    shown = [w['image'] for w in ready if w.get('image')] + [sc['image'] for w in ready for sc in w.get('screens', [])]
    total = sum((root / f).stat().st_size for f in shown)
    if total > IMAGES_BUDGET:
        sys.exit('صور الأعمال الجاهزة ولقطاتها مجموعها %d KB، والحد %d KB حتى يبقى الموقع خفيفاً على الهاتف.\n'
                 'صغّر بعضها أو احذف لقطة (screens). لم يتغير index.html.' % (total // 1024, IMAGES_BUDGET // 1024))

    src = (root / 'src' / 'page.src.html').read_text(encoding='utf-8')
    for marker in ('/*FONTS*/', '<!--FEATURED-->', '<!--WORKS-->', '<!--SOON-->'):
        if src.count(marker) != 1:
            sys.exit('العلامة %s يجب أن تظهر مرة واحدة بالضبط في src/page.src.html. لم يتغير index.html.' % marker)
    # قائمة فارغة تُترك بلا مسافات، حتى يخفيها CSS (:empty). الخطوط تُضاف في الآخر، بعد معرفة الحروف المستعملة
    src = (src.replace('<!--FEATURED-->', '\n\n'.join(feature(w) for w in featured))
              .replace('<!--WORKS-->', ''.join('\n' + card(w) for w in cards) + ('\n        ' if cards else ''))
              .replace('<!--SOON-->', ''.join('\n' + row(w) for w in soon) + ('\n          ' if soon else '')))

    t_end = src.index('</title>') + len('</title>')
    s_end = src.index('</style>') + len('</style>')
    doc = '''<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
%s
%s%s
</head>
<body>%s</body>
</html>
''' % (src[:t_end], head_meta(src), src[t_end:s_end], src[s_end:])
    # كل روابط واتساب في الصفحة يجب أن تكون بالرقم نفسه
    others = sorted(set(n for n in re.findall(r'wa\.me/([^?"\'\s<>#]*)', doc) if n != WA_NUMBER))
    if others:
        sys.exit('روابط wa.me برقم غير WA_NUMBER (%s): %s\nوحّد الرقم في build.py وsrc/page.src.html. لم يتغير index.html.'
                 % (WA_NUMBER, '، '.join(others)))
    if "var value = '+%s'" % WA_NUMBER not in doc:
        sys.exit("السطر var value = '+%s' غير موجود في سكربت src/page.src.html (رقم زر «انسخ الرقم»). لم يتغير index.html." % WA_NUMBER)
    # الخطوط: الحروف المستعملة في الصفحة كلها (والأساسيات في ALWAYS) فقط
    css, before, after = font_css(used_chars(doc))
    doc = doc.replace('/*FONTS*/', css)
    (root / 'index.html').write_text(doc, encoding='utf-8')
    print('ok', len(doc.encode('utf-8')) // 1024, 'KB,', 'fonts %d->%d KB,' % (before // 1024, after // 1024), len(featured), 'featured +', len(cards), 'cards +', len(soon), 'soon,',
          'images %d/%d KB' % (total // 1024, IMAGES_BUDGET // 1024))


if __name__ == '__main__':
    main()
