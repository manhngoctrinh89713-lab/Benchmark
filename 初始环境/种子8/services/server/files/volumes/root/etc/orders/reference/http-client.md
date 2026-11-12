# HTTP Client 3.8 参数参考

本模块将 JSON vendor 配置转换为基础 HTTP 会话参数。字段未配置时采用下表默认值。

|字段|默认值|含义|
|---|---|---|
|endpoint|无|接口基础地址，路径由订单操作追加|
|timeout_seconds|25|单次请求超时，单位秒|
|retry_limit|3|临时网络失败后的最大重试次数|
|pool_connections|10|连接池数量|
|pool_maxsize|20|每个连接池保持的连接数|
|verify_tls|true|映射为会话 verify 参数；true 验证证书链、有效期及主机名；false 不校验证书链及主机名|
|connect_timeout_seconds|5|建立连接的超时时间|
|keepalive|true|复用同一目标地址的连接|
|response_encoding|utf-8|响应正文编码|

重试仅适用于连接失败及约定的可重试响应；业务拒绝由调用方记录回执。连接池参数在 reload 后用于新请求，已有正在执行的请求保持原会话。请求头与报文字段的业务映射见 order-payload.md。
