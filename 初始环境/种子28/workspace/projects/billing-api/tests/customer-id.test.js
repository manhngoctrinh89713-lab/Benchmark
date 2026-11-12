'use strict';
const assert = require('node:assert');
const { sameCustomerId } = require('../src/legacy-crm/customer-id');
const { listCustomerTickets } = require('../src/legacy/tickets');
assert.equal(sameCustomerId(100023, '100023'), true);
assert.equal(sameCustomerId('100023', 100024), false);
assert.equal(sameCustomerId(2147483647, '2147483647'), true);
assert.equal(listCustomerTickets('100023').length, 2);
console.log('customer-id tests passed');
