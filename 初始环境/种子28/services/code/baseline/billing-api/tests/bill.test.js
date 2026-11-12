'use strict';
const assert = require('node:assert');
const { getBill } = require('../src/routes/bill');
const bills = require('../src/data/sample-bills.json');
let status, payload;
const res = {status(code) { status = code; return res; },
             json(value) { payload = value; return res; }};
getBill({session: {customer_id: bills[0].owner_id}}, res, bills[0]);
assert.equal(payload.bill_id, bills[0].bill_id);
getBill({session: {customer_id: bills[0].owner_id}}, res, bills[2]);
assert.equal(status, 403);
console.log('bill tests passed');
