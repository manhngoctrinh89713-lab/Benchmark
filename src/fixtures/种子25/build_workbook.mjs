import fs from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {Workbook, SpreadsheetFile} from '@oai/artifact-tool';
const dir = new URL('.', import.meta.url);
const wb=Workbook.create();
for(const name of ['产品价目表','待发报价','订单跟进']) wb.worksheets.add(name);
const products=[['产品编号','品名','销售单价（元）','计价单位'],['GF-101','保温杯',86,'只'],['GF-205','帆布袋',28,'个'],['GF-308','笔记本礼盒',65,'套'],['GF-412','折叠伞',48,'把'],['GF-506','金属签字笔',19,'支']];
wb.worksheets.getItem('产品价目表').getRange('A1:D6').values=products;
const pending=[['报价编号','客户','产品编号','数量','单价（元）','金额（元）','预计发送日期'],['Q1102-01','澄川科技','GF-101',200,null,null,'2026-11-03'],['Q1102-02','北辰咨询','GF-205',600,null,null,'2026-11-03'],['Q1102-03','禾木食品','GF-308',120,null,null,'2026-11-04'],['Q1102-04','云帆设计','GF-412',300,null,null,'2026-11-04']];
const ps=wb.worksheets.getItem('待发报价');ps.getRange('A1:G5').values=pending;
for(let r=2;r<=5;r++){ps.getRange(`E${r}`).formulas=[[`=VLOOKUP(C${r},'产品价目表'!$A$2:$C$6,3,FALSE)`]];ps.getRange(`F${r}`).formulas=[[`=D${r}*E${r}`]];}
const orders=[['订单号','客户','产品编号','数量','成交单价（元）','成交金额（元）','确认日期','交付进度'],['SO1028-01','启明软件','GF-101',500,null,null,'2026-10-28','待交付'],['SO1029-02','恒远咨询','GF-205',800,26,null,'2026-10-29','备货中'],['SO1030-03','松林教育','GF-308',240,null,null,'2026-10-30','待交付'],['SO1025-04','蓝港传媒','GF-412',160,46,null,'2026-10-25','已交付'],['SO1031-05','南星制造','GF-205',350,null,null,'2026-10-31','备货中'],['SO1026-06','瑞和物流','GF-506',1000,18,null,'2026-10-26','已交付']];
const os=wb.worksheets.getItem('订单跟进');os.getRange('A1:H7').values=orders;
for(let r=2;r<=7;r++){
 if([2,4,6].includes(r))os.getRange(`E${r}`).formulas=[[`=VLOOKUP(C${r},'产品价目表'!$A$2:$C$6,3,FALSE)`]];
 os.getRange(`F${r}`).formulas=[[`=D${r}*E${r}`]];
}
for(const s of [wb.worksheets.getItem('产品价目表'),ps,os]){
 s.getRange('A1:H1').format.fill='#243D55';
 s.getRange('A1:H1').format.font.color='#FFFFFF';
 s.getRange('A1:H1').format.font.bold=true;
 s.getRange('A:H').format.columnWidthPx=145;
 s.getRange('B:B').format.columnWidthPx=160;
}
ps.getRange('E2:F5').numberFormat='0.00';os.getRange('E2:F7').numberFormat='0.00';
wb.recalculate();
await (await SpreadsheetFile.exportXlsx(wb)).save(fileURLToPath(new URL('销售报价.xlsx',dir)));
console.log((await wb.inspect({kind:'region',sheetId:'订单跟进',range:'A1:H7',maxChars:2000,tableMaxRows:7,tableMaxCols:8})).ndjson);
try {const preview=await wb.render({sheetName:'订单跟进',range:'A1:H7',scale:1.5,format:'png'});await fs.writeFile(new URL('preview.png',dir),new Uint8Array(await preview.arrayBuffer()));}catch(e){console.log('Preview:',e.message);}
