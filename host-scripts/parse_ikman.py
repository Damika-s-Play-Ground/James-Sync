import urllib.request, urllib.parse, re, json, html, time
UA={'User-Agent':'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'}
def fetch(url): return urllib.request.urlopen(urllib.request.Request(url,headers=UA),timeout=30).read().decode('utf-8','ignore')
def extract_initial(t):
    marker='window.initialData = '
    i=t.find(marker)
    if i<0: return None
    j=i+len(marker)
    # skip spaces
    while j<len(t) and t[j].isspace(): j+=1
    start=j; depth=0; in_s=False; esc=False
    for k in range(start,len(t)):
        c=t[k]
        if in_s:
            if esc: esc=False
            elif c=='\\': esc=True
            elif c=='"': in_s=False
        else:
            if c=='"': in_s=True
            elif c=='{': depth+=1
            elif c=='}':
                depth-=1
                if depth==0:
                    return json.loads(t[start:k+1])
    return None

def rec(x,path=''):
    if isinstance(x,dict):
        yield path,x
        for k,v in x.items(): yield from rec(v,path+'/'+str(k))
    elif isinstance(x,list):
        for i,v in enumerate(x): yield from rec(v,path+f'[{i}]')

def get_urls():
    search='https://ikman.lk/en/ads/sri-lanka/property?sort=date&order=desc&buy_now=0&urgent=0&query='+urllib.parse.quote('4 bedroom house rent colombo')
    t=fetch(search)
    m=re.search(r'<script[^>]*type="application/ld\+json"[^>]*>(\{"@context":"http://schema.org","@type":"ItemList".*?</script>)', t, re.S)
    raw=m.group(1).split('</script>')[0]
    data=json.loads(raw)
    return [(it['name'],it['url']) for it in data['itemListElement']]

for name,u in get_urls():
    t=fetch(u); data=extract_initial(t)
    print('\n###',name); print(u)
    if not data:
        print('NO initial'); continue
    candidates=[]
    for p,d in rec(data):
        keys=set(d.keys())
        if ('title' in keys or 'name' in keys) and any(k in keys for k in ['price','description','location','ad','details','properties','money']):
            s=json.dumps(d,ensure_ascii=False)[:4000]
            if name[:15].lower() in s.lower() or 'price' in s.lower(): candidates.append((p,d))
    # Print likely ad dictionary paths with title/name and prices
    printed=0
    for p,d in candidates[:20]:
        js=json.dumps(d,ensure_ascii=False)
        if u.split('/ad/')[-1].split('-for-rent')[0][:20] in js or name.split('|')[0][:20] in js or 'amount' in js or 'price' in js:
            print('PATH',p)
            # flatten selected keys shallow
            for k in ['id','slug','title','name','description','price','location','properties','details','ad','type','status','timestamp','adDate']:
                if k in d: print(k, json.dumps(d[k],ensure_ascii=False)[:1500])
            printed+=1
            if printed>=5: break
    time.sleep(.2)
