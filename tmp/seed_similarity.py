import json,math,re,collections,itertools
rows=json.load(open(r'D:\DeskTop\my_benchmark\tmp\seeds_parsed.json',encoding='utf-8'))
docs={}
for r in rows:
 f=r['fields']
 txt=' '.join(str(v) for v in f.values())
 # keep Chinese/ascii tokens, char trigrams over normalized text
 txt=re.sub(r'[\s\W_]+','',txt.lower())
 grams=set(txt[i:i+3] for i in range(len(txt)-2))
 docs[r['seed']]=grams
N=len(docs); inv={}
for g in set().union(*docs.values()):
 inv[g]=math.log((N+1)/(1+sum(g in d for d in docs.values())))+1
weights={n:{g:inv[g] for g in gs} for n,gs in docs.items()}
def cos(a,b):
 A=weights[a]; B=weights[b]
 dot=sum(w*B.get(g,0) for g,w in A.items())
 na=math.sqrt(sum(w*w for w in A.values())); nb=math.sqrt(sum(w*w for w in B.values()))
 return dot/(na*nb) if na and nb else 0
pairs=[]
for a,b in itertools.combinations(docs,2): pairs.append((cos(a,b),a,b))
for s,a,b in sorted(pairs,reverse=True)[:30]: print(f'{s:.2f}\t{a}\t{b}')
