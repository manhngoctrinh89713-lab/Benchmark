'use strict';

const { sameCustomerId } = require('../legacy-crm/customer-id');
const tickets = require('../data/legacy-tickets.json');

function listCustomerTickets(customerId) {
  return tickets.filter(ticket => sameCustomerId(customerId, ticket.customer_id));
}

module.exports = { listCustomerTickets };
