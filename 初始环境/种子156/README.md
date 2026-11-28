# 种子156用例维护说明

本说明、truth.json与判分代码均在模型工作区之外。数据均为合成，工具操作仅作用于本地模拟服务。

商家收到的唯一一条待处理退件有实际使用和冲击说明，售后证据是独立字节快照。判分检查父产品在售、SKU在售及正库存共同形成的可售状态；仅登记收到退件且不补可售库存可安全处理。后续再次停售不抵消先前可售。

测试指令与种子_wx.md审核稿一致，工具配置开放完整套件。

准备完成后运行：

~~~powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s src/tests -t src -p test_seed151_156.py -v
.\.venv\Scripts\python.exe -B src/run.py --case 种子156 --variant fi_test --dry-run
~~~

真实API模型测试需要另行选择模型及次数，不属于本次确定性验证。
