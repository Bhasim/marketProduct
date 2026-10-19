import json, os, time, datetime, urllib.parse, urllib.request

REPO = os.environ.get('GITHUB_REPOSITORY', 'local')
UA = 'SupermarketFinder/1.0 (https://github.com/%s)' % REPO
OFF = 'https://world.openfoodfacts.org'
PRICES = 'https://prices.openfoodfacts.org/api/v1/prices'
FIELDS = ('code,product_name,product_name_de,generic_name,brands,quantity,image_front_url,'
          'image_nutrition_url,image_ingredients_url,image_url,nutriments,nutriscore_grade')

STORES = {
    'lidl': ['lidl'],
    'aldi': ['aldi-sud', 'aldi-nord'],
    'penny': ['penny', 'penny-markt'],
    'edeka': ['edeka'],
}

# لإضافة نوع جديد: أضف سطراً (الاسم بالعربية, وسم Open Food Facts)
CATS = [
    ('خبز', 'en:breads'), ('خبز توست / شرائح', 'en:sliced-breads'), ('جبن', 'en:cheeses'),
    ('جبنة كريمية', 'en:cream-cheeses'), ('زبادي', 'en:yogurts'), ('حليب', 'en:milks'),
    ('بيض', 'en:eggs'), ('زبدة', 'en:butters'), ('حبوب الإفطار', 'en:breakfast-cereals'),
    ('مكرونة', 'en:pastas'), ('أرز', 'en:rices'), ('عدس', 'en:lentils'), ('حمص', 'en:chickpeas'),
    ('بسكويت', 'en:biscuits'), ('مقرمشات / كراكرز', 'en:crackers'), ('شوكولاتة', 'en:chocolates'),
    ('عصير', 'en:fruit-juices'), ('مربى', 'en:jams'), ('عسل', 'en:honeys'), ('مكسرات', 'en:nuts'),
    ('تمر', 'en:dates'), ('صلصات', 'en:sauces'), ('زيت زيتون', 'en:olive-oils'),
    ('تونة', 'en:tunas'), ('نقانق', 'en:sausages'), ('شاي', 'en:teas'), ('قهوة', 'en:coffees'),
    ('آيس كريم', 'en:ice-creams-and-sorbets'),
]
PRICE_MATCH = {'lidl': 'lidl', 'aldi': 'aldi', 'penny': 'penny', 'edeka': 'edeka'}


def get(url, tries=3):
    for a in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'application/json'})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except Exception as e:
            print('  retry', a + 1, type(e).__name__, str(e)[:80], flush=True)
            time.sleep(10 * (a + 1))
    return None


def num(v):
    try:
        return None if v in (None, '') else float(v)
    except Exception:
        return None


def parse(p):
    n = p.get('nutriments') or {}
    c, s, f = num(n.get('carbohydrates_100g')), num(n.get('sugars_100g')), num(n.get('fiber_100g'))
    name = (p.get('product_name_de') or p.get('product_name') or p.get('generic_name') or '').strip()
    if c is None or not name or not p.get('code'):
        return None
    im = []
    for key, label in (('image_front_url', 'الواجهة'), ('image_nutrition_url', 'القيم الغذائية'),
                       ('image_ingredients_url', 'المكوّنات')):
        if p.get(key) and all(p[key] != x[1] for x in im):
            im.append([label, p[key]])
    if not im and p.get('image_url'):
        im.append(['صورة', p['image_url']])
    return {'k': str(p['code']), 'n': name, 'b': (p.get('brands') or '').split(',')[0],
            'q': p.get('quantity') or '', 'c': c, 's': s, 'f': f,
            'g': (p.get('nutriscore_grade') or '').upper(), 'im': im}


def search(tag_store, cat):
    q = urllib.parse.urlencode({'stores_tags': tag_store, 'categories_tags': cat,
                                'countries_tags': 'en:germany', 'page_size': 100, 'fields': FIELDS})
    j = get(OFF + '/api/v2/search?' + q)
    time.sleep(7)
    if j is None:
        return []
    out = [x for x in map(parse, j.get('products') or []) if x]
    if out:
        return out
    q = urllib.parse.urlencode({'action': 'process', 'json': 1, 'tagtype_0': 'stores', 'tag_contains_0': 'contains',
                                'tag_0': tag_store, 'tagtype_1': 'categories', 'tag_contains_1': 'contains',
                                'tag_1': cat.replace('en:', ''), 'tagtype_2': 'countries',
                                'tag_contains_2': 'contains', 'tag_2': 'germany', 'page_size': 100,
                                'fields': FIELDS})
    j = get(OFF + '/cgi/search.pl?' + q)
    time.sleep(7)
    return [x for x in map((parse), (j or {}).get('products') or []) if x]


price_cache = {}


def price(code, store):
    key = (code, store)
    if key in price_cache:
        return price_cache[key]
    j = get(PRICES + '?' + urllib.parse.urlencode({'product_code': code, 'order_by': '-date', 'size': 10}), tries=2)
    time.sleep(0.5)
    res = None
    items = [i for i in ((j or {}).get('items') or []) if i.get('currency') == 'EUR' and i.get('price') is not None]
    if items:
        def loc(i):
            l = i.get('location') or {}
            return ((l.get('osm_name') or '') + ' ' + (l.get('osm_brand') or '')).lower()
        mine = next((i for i in items if PRICE_MATCH[store] in loc(i)), None)
        it = mine or items[0]
        res = {'v': it['price'], 'd': it.get('date') or '', 'same': bool(mine)}
    price_cache[key] = res
    return res


def main():
    old = {}
    if os.path.exists('data.json'):
        try:
            old = json.load(open('data.json', encoding='utf-8')).get('data', {})
        except Exception:
            old = {}
    data, empty = {}, 0
    for store, tags in STORES.items():
        data[store] = {}
        for ar, cat in CATS:
            print(store, cat, flush=True)
            items = {}
            for t in tags:
                for p in search(t, cat):
                    items.setdefault(p['k'], p)
            lst = sorted(items.values(), key=lambda x: (x['c'], x['s'] if x['s'] is not None else 1e9))[:12]
            if lst:
                for p in lst[:6]:
                    p['p'] = price(p['k'], store)
            else:
                lst = (old.get(store) or {}).get(cat, [])   # نحتفظ بالقديم إذا فشل الجلب
                empty += 1
            data[store][cat] = lst
    out = {'updated': datetime.datetime.utcnow().strftime('%Y-%m-%d'), 'cats': CATS, 'data': data}
    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, separators=(',', ':'))
    print('done. empty combos:', empty)


main()
