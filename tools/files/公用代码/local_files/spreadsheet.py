"""Bounded XLSX operations and explicit, cache-independent formula evaluation.

No Excel macros, external links, Python eval or shell execution.
"""
import ast
import io
import math
import operator
import re
import zipfile
from decimal import Decimal, ROUND_HALF_UP

from openpyxl import load_workbook
from openpyxl.formula import Tokenizer
from openpyxl.utils.cell import range_boundaries, get_column_letter


def load(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        if len(z.infolist()) > 10000 or sum(i.file_size for i in z.infolist()) > 100 * 1024**2:
            raise ValueError('Workbook exceeds expanded size limits')
        if any('vbaProject' in i.filename for i in z.infolist()):
            raise ValueError('Macros are not supported')
    wb=load_workbook(io.BytesIO(raw), data_only=False, keep_links=True)
    if wb._external_links:
        raise ValueError('External workbook links are not supported')
    if sum(s.max_row*s.max_column for s in wb)>100000:
        raise ValueError('Workbook exceeds 100000 cells')
    return wb


def bounds(address):
    if not re.fullmatch(r'\$?[A-Za-z]{1,3}\$?[1-9][0-9]*(?::\$?[A-Za-z]{1,3}\$?[1-9][0-9]*)?', address):
        raise ValueError('Use a bounded A1 cell/range')
    a, b, c, d = range_boundaries(address)
    if c > 16384 or d > 1048576 or c < a or d < b or (c-a+1)*(d-b+1) > 2000:
        raise ValueError('Range exceeds 2000 cells or Excel bounds')
    return a, b, c, d


class Calculator:
    def __init__(self, workbook):
        self.wb = workbook
        self.cache = {}
        self.visiting = set()
        self.steps = 0

    def cell(self, sheet, address):
        address = address.replace('$', '').upper()
        bounds(address)
        key = (sheet, address)
        if key in self.cache:
            return self.cache[key]
        self.steps += 1
        if self.steps > 20000 or len(self.visiting) >= 64:
            raise ValueError('Calculation limit exceeded')
        if key in self.visiting:
            raise ValueError('Circular reference')
        self.visiting.add(key)
        try:
            cell = self.wb[sheet][address]
            if cell.data_type == 'e':
                raise ValueError('Excel error: '+str(cell.value))
            value = self.formula(cell.value, sheet) if cell.data_type == 'f' else cell.value
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError('Non-finite result')
            self.cache[key] = value
            return value
        finally:
            self.visiting.remove(key)

    def reference(self, sheet, ref):
        if '!' in ref:
            sheet, ref = ref.rsplit('!', 1)
            sheet = sheet[1:-1].replace("''", "'") if sheet.startswith("'") and sheet.endswith("'") else sheet
        if '[' in sheet or ']' in sheet or sheet not in self.wb.sheetnames:
            raise ValueError('External or unknown sheet reference')
        a,b,c,d = bounds(ref)
        if ':' not in ref:
            return self.cell(sheet, ref)
        return [[self.cell(sheet, f'{get_column_letter(col)}{row}') for col in range(a,c+1)] for row in range(b,d+1)]

    def formula(self, formula, sheet):
        if len(formula) > 4000:
            raise ValueError('Formula too long')
        parts = []
        for t in Tokenizer(formula).items:
            if t.type == 'WHITE-SPACE':
                continue
            if t.type == 'OPERAND':
                if t.subtype == 'RANGE': parts.append('REF('+repr(t.value)+')')
                elif t.subtype == 'TEXT': parts.append(repr(t.value[1:-1].replace('""','"')))
                elif t.subtype == 'NUMBER': parts.append(t.value)
                elif t.subtype == 'LOGICAL': parts.append(str(t.value.upper() == 'TRUE'))
                else: raise ValueError('Unsupported operand: '+t.value)
            elif t.type == 'FUNC':
                parts.append(t.value.upper() if t.subtype == 'OPEN' else ')')
            elif t.type == 'PAREN': parts.append(t.value)
            elif t.type == 'SEP' and t.subtype == 'ARG': parts.append(',')
            elif t.type in ('OPERATOR-INFIX','OPERATOR-PREFIX') and t.value in ('+','-','*','/'):
                parts.append(t.value)
            else: raise ValueError('Unsupported formula token: '+t.value)
        tree = ast.parse(''.join(parts), mode='eval')
        def flatten(xs):
            for x in xs:
                if isinstance(x,list): yield from flatten(x)
                else: yield x
        def calculate(node):
            if isinstance(node,ast.Constant) and type(node.value) in (str,int,float,bool): return node.value
            if isinstance(node,ast.BinOp) and type(node.op) in (ast.Add,ast.Sub,ast.Mult,ast.Div):
                a,b = calculate(node.left),calculate(node.right)
                if a is None: a=0
                if b is None: b=0
                if type(a) not in (int,float) or type(b) not in (int,float): raise ValueError('Non-numeric arithmetic')
                return {ast.Add:operator.add,ast.Sub:operator.sub,ast.Mult:operator.mul,ast.Div:operator.truediv}[type(node.op)](a,b)
            if isinstance(node,ast.UnaryOp) and type(node.op) in (ast.UAdd,ast.USub):
                x=calculate(node.operand)
                if type(x) not in (int,float): raise ValueError('Non-numeric unary operand')
                return x if isinstance(node.op,ast.UAdd) else -x
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and not node.keywords:
                args=[calculate(a) for a in node.args];name=node.func.id
                if name=='REF' and len(args)==1: return self.reference(sheet,args[0])
                if name=='VLOOKUP' and len(args)==4:
                    key,table,index,approx=args
                    if approx is not False or type(index) is not int or index<1 or not isinstance(table,list):
                        raise ValueError('VLOOKUP supports exact match only')
                    for row in table:
                        match = (row[0].casefold()==key.casefold()) if isinstance(row[0],str) and isinstance(key,str) else (type(row[0]) in (int,float) and type(key) in (int,float) and row[0]==key)
                        if match:
                            if index>len(row): raise ValueError('VLOOKUP column out of range')
                            return row[index-1]
                    raise ValueError('VLOOKUP key not found')
                if name=='ROUND' and len(args)==2 and type(args[1]) is int and -10<=args[1]<=10:
                    return float(Decimal(str(args[0])).quantize(Decimal(10)**-args[1],rounding=ROUND_HALF_UP))
                if name in ('SUM','MIN','MAX'):
                    nums=[x for x in flatten(args) if type(x) in (int,float)]
                    return sum(nums) if name=='SUM' else (min(nums) if name=='MIN' else max(nums))
                raise ValueError('Unsupported function: '+name)
            raise ValueError('Unsupported formula expression')
        return calculate(tree.body)


class SpreadsheetWorkbench:
    def get_workbook_info(self, path: str) -> dict:
        """查看XLSX工作表名称、可见性、行列范围和公式数量，不执行宏或外部链接。"""
        from .backend import digest
        with self.session():
            p=self.path(path,False);raw=self.read_bytes(p);wb=load(raw)
            return {'path':self.rel(p),'sha256':digest(raw),'sheets':[{'name':s.title,'state':s.sheet_state,'rows':s.max_row,'columns':s.max_column,'formula_count':sum(c.data_type=='f' for row in s for c in row)} for s in wb]}

    def read_spreadsheet(self, path: str, sheet: str, cell_range: str = 'A1:J20') -> dict:
        """读取XLSX指定区域的原值、公式和按当前依赖计算的结果。支持跨表引用、四则运算、SUM/MIN/MAX、ROUND和精确VLOOKUP；不支持的公式明确返回错误，不使用缓存冒充重算。单次最多2000格。"""
        from .backend import digest
        with self.session():
            p=self.path(path,False);raw=self.read_bytes(p);wb=load(raw);calc=Calculator(wb);a,b,c,d=bounds(cell_range)
            result=[]
            for row in wb[sheet].iter_rows(min_row=b,max_row=d,min_col=a,max_col=c):
                for cell in row:
                    item={'cell':cell.coordinate,'value':cell.value,'formula':cell.value if cell.data_type=='f' else None}
                    try: item['calculated_value']=calc.cell(sheet,cell.coordinate)
                    except (ValueError,KeyError,TypeError,ZeroDivisionError,SyntaxError,IndexError,RecursionError) as e: item['calculation_error']=str(e)
                    result.append(item)
            return {'path':self.rel(p),'sha256':digest(raw),'sheet':sheet,'cells':result}

    def write_spreadsheet(self, path: str, sheet: str, updates: list[dict], expected_sha256: str) -> dict:
        """按校验值批量修改XLSX单元格，保留其他内容和格式。updates每项为cell和value，支持数值、文本、布尔、null及以=开头的公式；最多2000格。公式由读取接口按支持范围计算，Excel打开后重新计算。"""
        from .backend import digest, MAX_FILE
        if not 1<=len(updates)<=2000: raise ValueError('updates requires 1..2000 cells')
        with self.session() as state:
            p=self.path(path,False);raw=self.read_bytes(p)
            if digest(raw)!=expected_sha256: raise ValueError('Workbook changed')
            wb=load(raw);ws=wb[sheet];seen=set()
            for update in updates:
                if set(update)!={'cell','value'}: raise ValueError('Each update needs cell and value')
                ref=update['cell'];bounds(ref)
                if ':' in ref: raise ValueError('Each update must address one cell')
                ref=ref.replace('$','').upper()
                if ref in seen: raise ValueError('Duplicate cell')
                seen.add(ref);v=update['value']
                if v is not None and type(v) not in (str,int,float,bool): raise ValueError('Invalid cell value')
                if isinstance(v,float) and not math.isfinite(v): raise ValueError('Non-finite value')
                if isinstance(v,str) and len(v)>32767: raise ValueError('Cell text too long')
                ws[ref]=v
            from openpyxl.workbook.properties import CalcProperties
            wb.calculation=CalcProperties(calcId=0,fullCalcOnLoad=True,forceFullCalc=True)
            out=io.BytesIO();wb.save(out);data=out.getvalue()
            if len(data)>MAX_FILE: raise ValueError('File exceeds 25 MiB')
            return self._write(state,p,data,True,'write_spreadsheet',expected_sha256)
