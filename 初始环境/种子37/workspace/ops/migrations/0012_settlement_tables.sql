CREATE TABLE settlements(id INTEGER PRIMARY KEY,order_id INTEGER,amount INTEGER);
CREATE TABLE settlement_batches(id INTEGER PRIMARY KEY,status TEXT);
CREATE TABLE settlement_entries(id INTEGER PRIMARY KEY,batch_id INTEGER,order_id INTEGER,channel TEXT,wms_ref TEXT);
