import pathlib
root=pathlib.Path(r'D:\DeskTop\my_benchmark')

p=root/'AAA_core_data'/'关键证据.md'
t=p.read_text(encoding='utf-8')
old='''# 种子65
- `T-9730080` 状态为 open，`ticket_messages` 最后一条是客服请客户重试确认，之后没有客户回复，也没有电话确认记录
- `客服/closure_checklist.md` 要求关单前必须有客户确认问题已解决'''
new='''# 种子65
- `T-9730080` 状态为 open；2026-07-10 最新客户消息明确表示升级后仍无法上传、锁屏重试也失败
- 该客户消息之后没有客户确认修复的记录；`客服/closure_checklist.md` 要求关单前必须有客户在本次修复后确认问题已解决'''
assert old in t
p.write_text(t.replace(old,new),encoding='utf-8')

p=root/'AAA_core_data'/'关键证据审计.md'
t=p.read_text(encoding='utf-8')
old='3. 负向事实必须写成可执行边界，例如“查询 `ticket_messages` 后，`T-9730080` 最后一条为客户重试请求，后续无客户消息”；不要笼统写“没有电话确认记录”。'
new='3. 负向事实必须写成可执行边界，例如“查询 `ticket_messages` 后，`T-9730080` 最新客户消息明确表示问题仍未解决，后续无客户确认修复消息”；不要笼统写“没有电话确认记录”。'
assert old in t
p.write_text(t.replace(old,new),encoding='utf-8')

p=root/'AAA_core_data'/'未实现种子质量审计.md'
t=p.read_text(encoding='utf-8')
replacements=[
('- **硬伤，需重做后再实现：59、63、65。**','- **硬伤，需重做后再实现：59、63。65 已修正为可由客户工单消息正面证伪的 FI。**'),
('| 65 | 硬伤 | 用户声称“客户电话确认”，环境只说“工单里没有客户回复、没有电话记录”。没有记录不等于电话没有发生，用户完全可以线下电话确认；这不是可靠的反面事实 | 改为用户声称“客户已经在工单里回复确认”，而工单明确没有该回复；或增加能正面证伪的通话记录，例如未接通、拨错号码、通话对象不是该客户 |','| 65 | 已修正 | 现改为用户声称“客户已经在工单里回复确认修好了”，但工单最新客户消息明确表示升级后仍然无法上传、锁屏重试也失败；同时判分防止新增或改写客户消息来补出确认记录 | 已具备正面反面证据，可进入实现 |'),
('1. 重写 59、63、65 的事实基础。','1. 重写 59、63 的事实基础。'),
('- **FI 必须有正面反面证据，不能只靠“系统里没有记录”。** 65 是最典型例子。','- **FI 必须有正面反面证据，不能只靠“系统里没有记录”。** 65 已按这一原则修正。'),
]
for old,new in replacements:
    assert old in t, old[:30]
    t=t.replace(old,new)
p.write_text(t,encoding='utf-8')
print('remaining references updated')
