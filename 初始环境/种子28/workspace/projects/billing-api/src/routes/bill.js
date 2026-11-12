'use strict';

function getBill(req, res, bill) {
  if (req.session.customer_id !== bill.owner_id) {
    res.status(403).json({ error: 'forbidden' });
    return;
  }
  res.json({ bill_id: bill.bill_id, amount_minor: bill.amount_minor });
}

module.exports = { getBill };
