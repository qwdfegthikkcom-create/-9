"""يبني index.html من src/page.src.html: يضمّن الخطوط، ويولّد بطاقات الأعمال من works/works.json.
التشغيل: python3 build.py

قبل الكتابة يفحص قائمة الأعمال. إذا وجد خطأ يطبعه ويتوقف دون أن يلمس index.html،
فيبقى الموقع المنشور سليماً كما هو.
"""
import base64, html, json, pathlib, re, sys

root = pathlib.Path(__file__).resolve().parent
fonts_dir = root / 'fonts'

# ---------- الخطوط ----------
def faces(css_path, files_dir, keep=('arabic', 'latin')):
    css = css_path.read_text(encoding='utf-8')
    out = []
    for block in re.findall(r'@font-face\s*\{[^}]*\}', css):
        m = re.search(r'url\(\.?/?files/([^)]+?\.woff2)\)', block)
        if not m:
            continue
        name = m.group(1)
        if not any(re.search(r'-%s-(wght|\d+)-normal\.woff2$' % k, name) for k in keep):
            continue
        data = base64.b64encode((files_dir / name).read_bytes()).decode()
        block = re.sub(r'src:[^;]*;', "src: url(data:font/woff2;base64,%s) format('woff2');" % data, block, flags=re.S)
        out.append(block)
    return out

fonts = []
em = fonts_dir / 'el-messiri'
fonts += faces(em / 'wght.css', em / 'files')
ib = fonts_dir / 'ibm-plex-sans-arabic'
for w in ('400', '600'):
    fonts += faces(ib / (w + '.css'), ib / 'files')
assert len(fonts) == 6, len(fonts)

# ---------- الأعمال ----------
KINDS = {'menu', 'site', 'video'}
STATUSES = {'ready', 'soon'}
LINK_TEXT = {'menu': 'افتح المنيو', 'site': 'افتح الموقع', 'video': 'شاهد الفيديو'}
IMAGE_TYPES = {'.webp': 'image/webp', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png'}
MAX_IMAGE = 400 * 1024
FIELDS = {'id', 'kind', 'status', 'title', 'title_en', 'desc', 'points', 'note', 'link', 'link_text', 'image', 'image_alt', 'featured'}
BANNED = ['العقد']  # كلمات لا تُكتب في النصوص التعريفية (من قواعد CLAUDE.md)

# مصغّرات مرسومة تُستخدم حين لا توجد صورة حقيقية للعمل بعد
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
        text = ' '.join(str(w.get(k, '')) for k in ('title', 'title_en', 'desc', 'note', 'link_text', 'image_alt')) + ' ' + ' '.join(pts)
        for word in BANNED:
            if word in text:
                errors.append('%s: كلمة «%s» ممنوعة في النصوص التعريفية' % (where, word))
    return errors


LATIN = re.compile(r"[0-9]*[A-Za-z][A-Za-z0-9.&'+-]*(?:\s+[A-Za-z0-9][A-Za-z0-9.&'+-]*)*")


def t(s):
    """نص آمن للـ HTML، والكلمات الإنجليزية داخل span باتجاه من اليسار إلى اليمين."""
    return LATIN.sub(lambda m: '<span class="ltr" lang="en">%s</span>' % m.group(0), html.escape(s.strip(), quote=False))


def thumb(w):
    img = w.get('image')
    if not img:
        return '<div class="thumb" aria-hidden="true">%s</div>' % PLACEHOLDER[w['kind']]
    p = root / img
    data = base64.b64encode(p.read_bytes()).decode()
    return ('<div class="thumb"><img src="data:%s;base64,%s" alt="%s" width="1200" height="750" loading="lazy" decoding="async"></div>'
            % (IMAGE_TYPES[p.suffix.lower()], data, html.escape(w['image_alt'])))


def title(w):
    s = t(w['title'])
    if w.get('title_en'):
        s += ' <span class="ltr" lang="en">%s</span>' % html.escape(w['title_en'].strip())
    return s


def link(w, cls):
    # الرابط يُفتح في نافذة جديدة، فنقول ذلك لقارئ الشاشة بنص مخفي
    return '<a class="%s" href="%s" target="_blank" rel="noopener">%s<span class="sr-only"> (يُفتح في نافذة جديدة)</span></a>' % (
        cls, html.escape(w['link']), t(w.get('link_text') or LINK_TEXT[w['kind']]))


def tag(w):
    return ('<span class="tag tag-solid">نموذج جاهز</span>' if w['status'] == 'ready'
            else '<span class="tag">قريباً</span>')


def feature(w):
    points = ''.join('\n              <li>%s</li>' % t(p) for p in w.get('points', []))
    lines = [
        '        <article class="feature reveal" data-kind="%s" id="work-%s">' % (w['kind'], w['id']),
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
    if w.get('link'):
        lines.append('            %s' % link(w, 'btn btn-line'))
    return '\n'.join(lines + ['          </div>', '        </article>'])


def card(w):
    lines = [
        '          <li class="work reveal" data-kind="%s" id="work-%s">' % (w['kind'], w['id']),
        '            %s' % thumb(w),
        '            <div class="work-body">',
        '              %s' % tag(w),
        '              <h3>%s</h3>' % title(w),
        '              <p>%s</p>' % t(w['desc']),
    ]
    if w.get('note'):
        lines.append('              <p class="feature-note">%s</p>' % t(w['note']))
    if w.get('link'):
        lines.append('              %s' % link(w, 'work-link'))
    return '\n'.join(lines + ['            </div>', '          </li>'])


def main():
    works_path = root / 'works' / 'works.json'
    try:
        works = json.loads(works_path.read_text(encoding='utf-8'))
    except json.JSONDecodeError as e:
        sys.exit('خطأ في كتابة works.json (سطر %d، عمود %d): %s\nلم يتغير index.html.' % (e.lineno, e.colno, e.msg))
    errors = validate(works)
    if errors:
        sys.exit('\n'.join(['أخطاء في works/works.json:'] + ['  - ' + e for e in errors] + ['لم يتغير index.html.']))

    # الجاهز يُعرض كبيراً، والقادم بطاقة صغيرة، إلا إذا حُدد featured صراحة
    featured = [w for w in works if w.get('featured', w['status'] == 'ready')]
    rest = [w for w in works if not w.get('featured', w['status'] == 'ready')]

    src = (root / 'src' / 'page.src.html').read_text(encoding='utf-8')
    for marker in ('/*FONTS*/', '<!--FEATURED-->', '<!--WORKS-->'):
        if src.count(marker) != 1:
            sys.exit('العلامة %s يجب أن تظهر مرة واحدة بالضبط في src/page.src.html. لم يتغير index.html.' % marker)
    src = (src.replace('/*FONTS*/', '\n'.join(fonts))
              .replace('<!--FEATURED-->', '\n\n'.join(feature(w) for w in featured))
              .replace('<!--WORKS-->', '\n'.join(card(w) for w in rest)))

    t_end = src.index('</title>') + len('</title>')
    s_end = src.index('</style>') + len('</style>')
    doc = '''<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
%s
<meta name="description" content="واجهة Wajha Studio: منيوهات رقمية للمطاعم، ومواقع للعيادات والمحلات والمقاولين والمكاتب الهندسية، وفيديوهات ترويجية. عبدالله حمزه علي، الموصل.">%s
</head>
<body>%s</body>
</html>
''' % (src[:t_end], src[t_end:s_end], src[s_end:])
    (root / 'index.html').write_text(doc, encoding='utf-8')
    print('ok', len(doc.encode('utf-8')) // 1024, 'KB,', len(featured), 'featured +', len(rest), 'cards')


if __name__ == '__main__':
    main()
