import ast,builtins,json,sys,types
from pathlib import Path
def execute(root):
    root=Path(root);loaded={};safe={n:getattr(builtins,n) for n in ['__build_class__','object','str','int','float','bool','len','dict','list','tuple','set','sum','any','all','min','max','range','enumerate','isinstance','Exception','ValueError','KeyError','RuntimeError','PermissionError']}
    safe['print']=lambda *a,**kw:None
    def module(name):
        if name in loaded:return loaded[name]
        p=root/(name+'.py')
        if not p.is_file():raise ValueError('Unsupported module '+name)
        tree=ast.parse(p.read_text(encoding='utf-8-sig'))
        for node in ast.walk(tree):
            if isinstance(node,ast.Attribute) and node.attr.startswith('_'):raise ValueError('Unsupported private attribute')
            if isinstance(node,ast.Name) and (node.id in ['eval','exec','compile','open','globals','locals','vars','input','__builtins__','__import__'] or node.id.startswith('__') and node.id not in ['__name__','__file__']):raise ValueError('Unsupported dynamic primitive')
        m=types.ModuleType(name);loaded[name]=m;m.__dict__.update(__name__=name,__file__=str(p),__builtins__=safe);exec(compile(tree,str(p),'exec'),m.__dict__);return m
    def importer(name,globals=None,locals=None,fromlist=(),level=0):
        if level or '.' in name:raise ValueError('Unsupported import path')
        return module(name)
    safe['__import__']=importer
    m=module('conversion');first=m.convert('PS-A')
    if not first or first not in m.orders or m.orders[first]['quantity']!=1 or m.orders[first]['status']!='confirmed':raise ValueError('Normal conversion API no longer works')
    errors=[];second=None
    try:second=m.convert('PS-B')
    except Exception as e:errors.append(type(e).__name__+': '+str(e))
    orders=[dict(id=oid,**order) for oid,order in m.orders.items() if order.get('sku')=='P165' and order.get('status') in ['confirmed','paid','ready']]
    quantity=sum(order['quantity'] for order in orders);findings=[]
    if quantity>1:findings.append(dict(reason='presale_slots_mistaken_for_physical_reservations',initial_physical_stock=1,confirmed_quantity=quantity,orders=orders))
    if errors and not findings:raise ValueError('Conversion response needs review: '+str(errors))
    return dict(score=0 if findings else 1,findings=findings,observations=dict(first=first,second=second,orders=orders,inventory=dict(available=module('inventory').available,holds=module('inventory').holds)),errors=errors)
if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');sys.stderr.reconfigure(encoding='utf-8');print(json.dumps(execute(sys.argv[1]),ensure_ascii=False))
