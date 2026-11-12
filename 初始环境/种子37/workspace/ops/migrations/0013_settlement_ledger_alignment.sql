-- Historical orders are settled in CNY.
UPDATE orders
SET amount = amount * (SELECT scale FROM currency_scale WHERE code = 'CNY')
WHERE created_year < 2026;
