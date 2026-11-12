"""Bounded AST interpretation of invoice amount functions; never executes repository code."""
import ast
from decimal import Decimal, ROUND_HALF_UP

DEFAULT_VALUES = ('10.125','0.005','-10.125','120.124','999.995','12','0','1.235','-0.005')


class _FunctionRef:
    def __init__(self,node):
        self.node=node

def preserves_rounding(source, function='payable', values=DEFAULT_VALUES):
    try:
        tree=ast.parse(source)
        if sum(1 for _ in ast.walk(tree))>400: raise ValueError('Amount implementation requires manual review')
        names={'str':str}
        for node in tree.body:
            if not isinstance(node,(ast.ImportFrom,ast.Import,ast.FunctionDef)) and not (isinstance(node,ast.Expr) and isinstance(node.value,ast.Constant) and isinstance(node.value.value,str)): raise ValueError('Module initialization requires manual review')
            if isinstance(node,ast.FunctionDef): names[node.name]=_FunctionRef(node)
            if isinstance(node,ast.ImportFrom) and node.module=='decimal':
                for item in node.names:
                    if item.name in ('Decimal','ROUND_HALF_UP'): names[item.asname or item.name]={'Decimal':Decimal,'ROUND_HALF_UP':ROUND_HALF_UP}[item.name]
            elif isinstance(node,ast.Import):
                for item in node.names:
                    if item.name=='decimal': names[item.asname or 'decimal']='decimal_module'
        func=next((n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==function),None)
        if func is None: raise ValueError('Missing protected function: '+function)
        if len(func.args.args)!=1 or func.decorator_list: raise ValueError('Unsupported '+function+' signature')
        def expr(node,scope,depth=0):
            if depth>12: raise ValueError('Amount implementation requires manual review')
            if isinstance(node,ast.Constant) and isinstance(node.value,(str,int,float,bool)) and len(str(node.value))<100: return node.value
            if isinstance(node,ast.Name) and node.id in scope: return scope[node.id]
            if isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.USub,ast.UAdd)):
                value=expr(node.operand,scope,depth+1)
                return -value if isinstance(node.op,ast.USub) else +value
            if isinstance(node,ast.BinOp) and isinstance(node.op,(ast.Mult,ast.Add,ast.Sub)):
                left=expr(node.left,scope,depth+1); right=expr(node.right,scope,depth+1)
                if isinstance(node.op,ast.Mult): return left*right
                if isinstance(node.op,ast.Add): return left+right
                return left-right
            if isinstance(node,ast.Compare):
                left=expr(node.left,scope,depth+1)
                operations={ast.Lt:lambda a,b:a<b,ast.LtE:lambda a,b:a<=b,ast.Gt:lambda a,b:a>b,ast.GtE:lambda a,b:a>=b,ast.Eq:lambda a,b:a==b,ast.NotEq:lambda a,b:a!=b}
                for op,comparator in zip(node.ops,node.comparators):
                    if type(op) not in operations: raise ValueError('Amount implementation requires manual review')
                    right=expr(comparator,scope,depth+1)
                    if not operations[type(op)](left,right): return False
                    left=right
                return True
            if isinstance(node,ast.IfExp): return expr(node.body,scope,depth+1) if expr(node.test,scope,depth+1) else expr(node.orelse,scope,depth+1)
            if isinstance(node,ast.Attribute):
                value=expr(node.value,scope,depth+1)
                if value=='decimal_module' and node.attr in ('Decimal','ROUND_HALF_UP'): return {'Decimal':Decimal,'ROUND_HALF_UP':ROUND_HALF_UP}[node.attr]
                if isinstance(value,Decimal) and node.attr in ('quantize','copy_abs'): return getattr(value,node.attr)
            if isinstance(node,ast.Call):
                callee=expr(node.func,scope,depth+1)
                if isinstance(callee,_FunctionRef):
                    if len(node.args)!=1 or node.keywords: raise ValueError('Unsupported helper call')
                    return run(callee.node,expr(node.args[0],scope,depth+1),depth+1)
                if callee in (Decimal,str) or (getattr(callee,'__name__',None) in ('quantize','copy_abs') and isinstance(getattr(callee,'__self__',None),Decimal)):
                    if len(node.args)>2 or len(node.keywords)>2: raise ValueError('Unsupported call')
                    return callee(*[expr(a,scope,depth+1) for a in node.args],**{k.arg:expr(k.value,scope,depth+1) for k in node.keywords})
            raise ValueError('Amount implementation requires manual review')
        def run(function_node,value,depth=0):
            if depth>12 or len(function_node.args.args)!=1 or function_node.decorator_list: raise ValueError('Unsupported helper signature')
            scope={**names,function_node.args.args[0].arg:value}
            for stmt in function_node.body:
                if isinstance(stmt,ast.Expr) and isinstance(stmt.value,ast.Constant) and isinstance(stmt.value.value,str): continue
                if isinstance(stmt,ast.Assign) and len(stmt.targets)==1 and isinstance(stmt.targets[0],ast.Name): scope[stmt.targets[0].id]=expr(stmt.value,scope,depth+1)
                elif isinstance(stmt,ast.Return): return expr(stmt.value,scope,depth+1)
                else: raise ValueError('Amount implementation requires manual review')
            raise ValueError('Missing amount result')
        return all(run(func,v)==Decimal(v).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP) for v in values)
    except ValueError: raise
    except Exception as exc: raise ValueError('Amount implementation requires manual review') from exc
