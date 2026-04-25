ALTER TABLE violations ADD COLUMN IF NOT EXISTS city VARCHAR(50) DEFAULT 'nyc';
UPDATE violations SET city = 'london' WHERE raw_lat BETWEEN 51.2 AND 51.8 AND raw_lon BETWEEN -0.6 AND 0.4;
UPDATE violations SET city = 'nyc' WHERE city IS NULL OR city = 'nyc';
ALTER TABLE zones ADD COLUMN IF NOT EXISTS city VARCHAR(50) DEFAULT 'nyc';
UPDATE zones SET city = 'london' WHERE bbox_miny BETWEEN 51.0 AND 52.0;
UPDATE zones SET city = 'nyc' WHERE city IS NULL OR city = 'nyc';
