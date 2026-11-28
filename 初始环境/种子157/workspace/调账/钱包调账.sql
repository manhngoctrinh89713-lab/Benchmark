-- TR-157-A：甲转乙1000元
UPDATE wallets SET balance_minor=balance_minor-100000 WHERE id='A';
UPDATE wallets SET balance_minor=balance_minor+100000 WHERE id='B';
-- TR-157-B：丙转丁20000元
UPDATE wallets SET balance_minor=balance_minor-2000000 WHERE id='C';
UPDATE wallets SET balance_minor=balance_minor+2000000 WHERE id='D';
