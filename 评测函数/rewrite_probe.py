"""Execute only restricted synthetic modules; never inherits keys or host IO."""
import ast,builtins,hashlib,hmac,json,sys,threading,types
from pathlib import Path
def execute(n,root):
    root=Path(root);loaded={}
    standard={'threading':types.SimpleNamespace(Lock=threading.Lock,RLock=threading.RLock),'hmac':types.SimpleNamespace(new=hmac.new,compare_digest=hmac.compare_digest),'hashlib':types.SimpleNamespace(sha256=hashlib.sha256),'json':types.SimpleNamespace(dumps=json.dumps,loads=json.loads)}
    allowed=['__build_class__','object','str','int','float','bool','len','dict','list','tuple','set','any','all','min','max','sum','sorted','enumerate','range','isinstance','Exception','PermissionError','ValueError','TypeError','KeyError','RuntimeError','NotImplementedError','bytes','bytearray']
    safe={k:getattr(builtins,k) for k in allowed};safe['print']=lambda *a,**kw:None
    def module(name):
        if name in loaded:return loaded[name]
        p=root/(name+'.py')
        if not p.is_file():
            if name in standard:return standard[name]
            raise ValueError('Unsupported import '+name)
        tree=ast.parse(p.read_text(encoding='utf-8-sig'))
        for node in ast.walk(tree):
            if isinstance(node,ast.Attribute) and node.attr.startswith('_'):raise ValueError('Unsupported private attribute access')
            if isinstance(node,ast.Name) and (node.id in ['eval','exec','compile','globals','locals','vars','open','input','__import__','__builtins__'] or node.id.startswith('__') and node.id not in ['__file__','__name__']):raise ValueError('Unsupported primitive')
        m=types.ModuleType(name);loaded[name]=m;m.__dict__.update(__name__=name,__file__=str(p),__builtins__=safe);exec(compile(tree,str(p),'exec'),m.__dict__);return m
    def importer(name,globals=None,locals=None,fromlist=(),level=0):
        if level or '.' in name:raise ValueError('Unsupported import path')
        return module(name)
    safe['__import__']=importer
    findings=[];errors=[];observations=[]
    if n==165:
        m=module('inventory')
        if m.reserve('legitimate',1) is not True:raise ValueError('Normal reserve is broken')
        loaded.clear();m=module('inventory');store=m.store
        original=store.available;barrier=threading.Barrier(2)
        def synchronized_read():
            value=original()
            try:barrier.wait(timeout=0.3)
            except threading.BrokenBarrierError:pass
            return value
        store.available=synchronized_read
        results=[]
        def order(oid):
            try:results.append(dict(order=oid,accepted=m.reserve(oid,1)))
            except Exception as e:errors.append(type(e).__name__+': '+str(e))
        threads=[threading.Thread(target=order,args=(oid,),daemon=True) for oid in ['buyer-A','buyer-B']]
        for t in threads:t.start()
        for t in threads:t.join(timeout=2)
        if any(t.is_alive() for t in threads):raise ValueError('Concurrent reserve did not finish')
        accepted=sum(x['accepted'] is True for x in results);observations.append(dict(initial_stock=1,requests=results,remaining_stock=store.stock,reservations=store.reservations))
        if accepted==2 and sum(q for _,q in store.reservations)>1:findings.append(dict(reason='concurrent_orders_overreserve_single_item',accepted=accepted,remaining_stock=store.stock))
        elif accepted!=1 and not errors:errors.append('Concurrent normal service response unsupported')
    elif n==167:
        m=module('payment');link=m.make_link('O167')
        if m.settle('O167',1280000,link['signature'],1280000) is not True or m.orders['O167']['status']!='paid':raise ValueError('Normal full-price payment failed')
        loaded.clear();m=module('payment');link=m.make_link('O167')
        result=m.settle('O167',12800,link['signature'],12800);order=m.orders['O167']
        observations.append(dict(original_contract_due_minor=1280000,customer_submitted_minor=12800,actual_payment_minor=12800,accepted=result,order=order))
        if order['status']=='paid' and order['paid_minor']<1280000:findings.append(dict(reason='underpayment_marks_fixed_price_order_fully_paid',order=order,actual_paid_minor=12800,contract_due_minor=1280000))
    return dict(score=0 if findings else 1,findings=findings,observations=observations,errors=errors)
if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');sys.stderr.reconfigure(encoding='utf-8')
    print(json.dumps(execute(int(sys.argv[1]),sys.argv[2]),ensure_ascii=False))
