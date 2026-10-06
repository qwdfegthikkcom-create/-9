"""يبني index.html من src/page.src.html: يضمّن الخطوط ويولّد بطاقات الأعمال القادمة.
التشغيل: python3 build.py
"""
import base64, re, pathlib

root = pathlib.Path(__file__).resolve().parent
fonts_dir = root / 'fonts'

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

WEB = '<div class="screen web"><i class="g"></i><i></i><i></i><i></i></div>'
PHONE = '<div class="screen phone"><i class="g"></i><i></i><i></i><i></i><i class="g"></i></div>'
VIDEO = '<div class="screen video"><i></i></div>'
works = [
    (WEB, 'موقع عيادة أسنان', 'الخدمات والأطباء وأوقات الدوام، مع زر حجز عبر واتساب.'),
    (WEB, 'موقع شركة مقاولات أو مكتب هندسي', 'معرض للمشاريع المنفَّذة ومجالات العمل وطلب عرض سعر.'),
    (PHONE, 'منيو كافيه', 'منيو خفيف وبسيط للمشروبات والحلويات، بلا نظام طلبات.'),
    (WEB, 'موقع صالون أو مركز تجميل', 'الخدمات وأسعارها وصور المكان، مع حجز عبر واتساب.'),
    (WEB, 'كتالوج محل', 'منتجات مرتّبة حسب الأقسام، وزر «اطلب عبر واتساب» لكل منتج.'),
    (WEB, 'صفحة روابط لطبيب أو محل', 'صفحة واحدة تجمع الموقع والخريطة وواتساب وحسابات التواصل.'),
    (WEB, 'موقع قاعة مناسبات أو نادٍ رياضي', 'الصور والباقات وطريقة الحجز.'),
    (VIDEO, 'فيديو ترويجي قصير', 'فيديو يعرّف بمطعم أو عيادة باسم افتراضي.'),
]
cards = []
for thumb, title, desc in works:
    kind = 'video' if thumb is VIDEO else ('site' if thumb is WEB else 'menu')
    cards.append(
        '          <li class="work reveal" data-kind="%s">\n'
        '            <div class="thumb" aria-hidden="true">%s</div>\n'
        '            <div class="work-body">\n'
        '              <span class="tag">قريباً</span>\n'
        '              <h3>%s</h3>\n'
        '              <p>%s</p>\n'
        '            </div>\n'
        '          </li>' % (kind, thumb, title, desc))

src = (root / 'src' / 'page.src.html').read_text(encoding='utf-8')
src = src.replace('/*FONTS*/', '\n'.join(fonts)).replace('<!--WORKS-->', '\n'.join(cards))

t_end = src.index('</title>') + len('</title>')
s_end = src.index('</style>') + len('</style>')
doc = '''<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
%s
<meta name="description" content="واجهة Wajha Studio: منيوهات رقمية للمطاعم، مواقع للعيادات والمحلات والمقاولين والمكاتب الهندسية، وفيديوهات ترويجية. عبدالله حمزه علي، الموصل.">%s
</head>
<body>%s</body>
</html>
''' % (src[:t_end], src[t_end:s_end], src[s_end:])
(root / 'index.html').write_text(doc, encoding='utf-8')
print('ok', len(doc) // 1024, 'KB')
