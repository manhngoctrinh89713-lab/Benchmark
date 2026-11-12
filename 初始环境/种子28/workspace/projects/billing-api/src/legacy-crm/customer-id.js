'use strict';

// 兼容旧CRM接口返回的数字编号与字符串编号。
function sameCustomerId(a, b) {
  return Number(a) === Number(b);
}

module.exports = { sameCustomerId };
