import urllib.request, re, html, json, urllib.parse, sys, time
UA={'User-Agent':'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'}
def fetch(url):
 req=urllib.request.Request(url,headers=UA)
 return urllib.request.urlopen(req,timeout=30).read().decode('utf-8','ignore')
def clean(s): return re.sub(r'\s+',' ',html.unescape(re.sub('<.*?>',' ',s))).strip()
search='https://ikman.lk/en/ads/sri-lanka/property?sort=date&order=desc&buy_now=0&urgent=0&query='+urllib.parse.quote('4 bedroom house rent colombo')
txt=fetch(search)
# parse ItemList json schema
m=re.search(r'<script[^>]*type="application/ld\+json"[^>]*>(\{"@context":"http://schema.org","@type":"ItemList".*?</script>)', txt, re.S)
items=[]
if m:
 raw=m.group(1).split('</script>')[0]
 try:
  data=json.loads(raw)
  items=data.get('itemListElement',[])
 except Exception as e: print('json err',e, raw[:200])
urls=[]
for it in items:
 u=it.get('url'); name=it.get('name')
 if u and u not in [x[1] for x in urls]: urls.append((name,u))
print('urls',len(urls))
for name,u in urls:
 print('\n###',name,'\nURL',u)
 try:
  t=fetch(u)
  print('len',len(t))
  # text snippets around price, bedrooms
  plain=clean(t)
  # print title meta desc
  for pat in [r'<title[^>]*>(.*?)</title>', r'<meta[^>]+name="description"[^>]+content="([^"]*)"', r'<script type="application/ld\+json">(.*?)</script>']:
   mm=re.search(pat,t,re.S|re.I)
   if mm: print('PAT', clean(mm.group(1))[:1000])
  for kw in ['Rs','Bedrooms','Bedroom','Bathrooms','Type','Address','Colombo','posted']:
   idx=plain.lower().find(kw.lower())
   if idx>=0: print('CTX',kw, plain[max(0,idx-300):idx+700])
  # regex useful pairs
  for rm in re.finditer(r'(Rs\.?\s*[0-9,]+|LKR\s*[0-9,]+|[0-9,]+\s*per month)', plain, re.I): print('PRICE?',rm.group(0))
 except Exception as e: print('ERR',repr(e))
 time.sleep(.3)
