import urllib.request, urllib.parse, re, html, json, time
from urllib.error import HTTPError, URLError

UA={'User-Agent':'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'}

def fetch(url, timeout=30):
    req=urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8','ignore')

def strip(s):
    return re.sub(r'\s+', ' ', html.unescape(re.sub('<.*?>',' ',s))).strip()

def ddg(q):
    url='https://duckduckgo.com/html/?q='+urllib.parse.quote(q)
    txt=fetch(url)
    out=[]
    for m in re.finditer(r'<a rel="nofollow" class="result__a" href="([^"]+)"[^>]*>(.*?)</a>', txt, re.S):
        href=html.unescape(m.group(1))
        if 'uddg=' in href:
            href=urllib.parse.unquote(urllib.parse.parse_qs(urllib.parse.urlparse(href).query).get('uddg',[href])[0])
        out.append((strip(m.group(2)), href))
    return out, txt

def bing(q):
    url='https://www.bing.com/search?q='+urllib.parse.quote(q)
    txt=fetch(url)
    out=[]
    for m in re.finditer(r'<li class="b_algo".*?<h2.*?<a href="([^"]+)"[^>]*>(.*?)</a>(.*?)</li>', txt, re.S):
        out.append((strip(m.group(2)), html.unescape(m.group(1)), strip(m.group(3))[:500]))
    return out, txt

# scrape ikman search page cards
u='https://ikman.lk/en/ads/sri-lanka/property?sort=date&order=desc&buy_now=0&urgent=0&query='+urllib.parse.quote('4 bedroom house rent colombo')
txt=fetch(u)
print('IKMAN_SEARCH_LEN', len(txt))
# collect ad URLs around /en/ad/
urls=[]
for m in re.finditer(r'https?://ikman.lk/en/ad/[^"\\< ]+|/en/ad/[^"\\< ]+', txt):
    href=html.unescape(m.group(0))
    if href.startswith('/'): href='https://ikman.lk'+href
    href=href.split('?')[0]
    if href not in urls: urls.append(href)
print('IKMAN_URLS', len(urls))
for href in urls[:50]:
    # context around href
    idx=txt.find(href.replace('https://ikman.lk',''))
    if idx<0: idx=txt.find(href)
    ctx=strip(txt[max(0,idx-1000):idx+2000])
    print('\nIKMAN', href)
    print(ctx[:1200])

queries=[]
platforms=['ikman.lk','lankapropertyweb.com/rentals/property_details','house.lk/details','patpat.lk','rush2homes.lk','anrealtors.lk','colomborealtors.lk','ceylonproperty.lk','propertyocean.lk']
locs=['Colombo 5','Colombo 4','Colombo 6','Nugegoda','Rajagiriya','Nawala','Narahenpita','Thimbirigasyaya','Kirulapone','Dehiwala','Bambalapitiya','Wellawatte']
for p in platforms:
  for loc in locs[:]:
    queries.append(f'site:{p} "house for rent" "{loc}" "4" "250,000"')
    queries.append(f'site:{p} "4 bedroom" "for rent" "{loc}" "250,000"')
# sample bing
seen=set()
for q in queries[:80]:
    try:
        res,_=bing(q)
    except Exception as e:
        continue
    for title,href,snip in res:
        if any(dom.split('/')[0] in href for dom in ['ikman.lk','lankapropertyweb.com','house.lk','patpat.lk','rush2homes.lk','anrealtors.lk','colomborealtors.lk','ceylonproperty.lk','propertyocean.lk']):
            key=href.split('?')[0]
            if key not in seen:
                seen.add(key)
                print('\nBING_RESULT', q, '\n', title, '\n', href, '\n', snip[:400])
    time.sleep(0.2)
print('SEEN', len(seen))
