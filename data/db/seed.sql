INSERT INTO customers VALUES
 (1,'C-001','Customer Alpha','Tehran'),
 (2,'C-002','Customer Beta','Shiraz'),
 (3,'C-003','Customer Gamma','Tabriz');
INSERT INTO products VALUES
 (1,'KB-100','Nava Mechanical Keyboard','keyboard'),
 (2,'HS-200','Nava Office Headset','headset'),
 (3,'SP-300','Nava Desktop Speaker','speaker');
INSERT INTO orders VALUES
 (1,'N-1001',1,'2026-01-05','completed','IRR'),
 (2,'N-1002',2,'2026-01-10','completed','IRR'),
 (3,'N-1003',1,'2026-01-15','completed','IRR'),
 (4,'N-1004',3,'2026-01-25','completed','IRR'),
 (5,'N-1005',1,'2026-01-28','cancelled','IRR'),
 (6,'N-1010',1,'2026-02-03','completed','IRR'),
 (7,'N-1011',2,'2026-02-10','completed','IRR'),
 (8,'N-1012',1,'2026-02-18','completed','IRR'),
 (9,'N-1013',3,'2026-02-25','completed','IRR'),
 (10,'N-1014',2,'2026-03-01','completed','IRR');
INSERT INTO order_items VALUES
 (1,1,1,2,2000000,0), (2,1,2,2,3000000,0),
 (3,2,3,5,5000000,0), (4,3,2,10,3000000,0),
 (5,4,3,8,5000000,5000000), (6,5,3,10,5000000,0),
 (7,6,1,10,2000000,0), (8,6,2,5,3000000,0),
 (9,7,3,10,5000000,0), (10,8,2,10,3000000,0),
 (11,9,1,5,2000000,0), (12,10,1,1,2000000,0);
