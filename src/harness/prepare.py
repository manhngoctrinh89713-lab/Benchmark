"""Regenerate group instructions from the tool schemas.

The output is reference documentation only: since 2026-11-11 runs no longer read
``prompt/tools/*.md`` (the tool catalog already reaches the model through the
request's ``tools`` array).  See ``.archive/tool-docs-20261111/README.md``.
"""
import json

from .catalog import ROOT, SUITES, TOOLS_ROOT
from .interface import public_description

GUIDES = {
    "mail": "管理邮件账户、会话、草稿、附件、文件夹、分类、通讯录、委托、收件规则、自动回复和定时邮件。先查询账户权限及对象 ID；附件与文件工具共用工作区。读取不改变状态或推进时间。批量操作逐项返回结果，发送接受与已有投递证据分别记录。",
    "chat": "管理微信式联系人关系、私聊、群聊、公告、消息、媒体、草稿和收藏。身份、个人备注与群昵称分别保存；先查对象 ID 和当前群角色。读取不自动标已读、不推进时间。附件与文件工具共用工作区；新成员不自动取得入群前历史，退群保留自己的既有本地记录。",
    "files": "管理工作区文件、目录、文本与二进制、文档提取、ZIP、回收站和XLSX单元格读写。工作簿读取可返回公式及按支持范围计算的结果，计算错误明确报告。路径相对于工作区；写入默认不覆盖，回收与直接删除分别操作，恢复默认不覆盖。",
    "database": "通过数据库 ID 管理 SQLite 数据库、结构、参数化查询和事务，支持 CSV、导出、备份恢复及完整性检查。备份文件使用工作区相对路径；覆盖现有数据库前核对 SHA-256。",
    "code": "按项目 ID 查询和修改代码、符号及引用，支持文件生命周期、多文件编辑、预览和静态语法诊断。文件路径相对于项目；先查询项目及当前文件。静态诊断不代表项目测试结果。",
    "git": "先查询仓库、状态和当前提交，再管理分支、标签、暂存、提交、文件恢复、stash、合并、变基、挑选或撤销提交。文件路径相对于仓库；冲突后可继续、跳过或中止对应操作。",
    "github": "管理仓库、Issue、PR、评论、评审、标签、里程碑、发布和工作流。文件与 Git 共享。PR 评审针对当前提交；工作流触发、取消请求和执行器最终结果分别记录。",
    "pc": "管理目标 Windows 电脑的应用、进程、启动项、个人文件、缓存、回收站、备份、设置、环境变量和计划任务。系统路径指向目标电脑；读取不推进任务，任务结果由环境调度记录。",
    "server": "管理目标 Linux 服务器的服务、进程、权限、配置、日志、文件、备份、环境变量和计划任务，查询网络观测。系统路径指向目标服务器；配置保存、重载生效与服务状态分别判断。",
    "merchant": "管理规格库存、销售政策、配送优惠、订单、分包发货、数字交付、退换货、退款、订阅方案和开票。与买家共用交易状态，已成交条款保留快照。发起退款与退款到账分别记录。账期由环境统一推进。",
    "buyer": "管理资料、地址、支付方式、商品、购物车、报价、订单、包裹、数字交付、售后、订阅和开票。先查询当前规格和政策；报价不预留库存，订单保存成交快照。支付、退款到账和履约状态分别判断。文件参数使用工作区相对路径。",
}


def main():
    destination = ROOT / "prompt/tools"
    destination.mkdir(parents=True, exist_ok=True)
    for group, (directory, _, _) in SUITES.items():
        lines = [f"## {group} 工具组", "", GUIDES[group], "", "可用工具（参数见函数定义）：", ""]
        for path in sorted((TOOLS_ROOT / directory / "工具调用API").glob("*/schema.json")):
            schema = json.loads(path.read_text(encoding="utf-8"))
            lines.append(f"- `{group}__{schema['name']}`：{public_description(schema['description'])}")
        (destination / (group + ".md")).write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
