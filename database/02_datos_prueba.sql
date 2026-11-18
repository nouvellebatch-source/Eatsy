-- Solo para una base de pruebas vacía, después de 01_esquema.sql.
INSERT INTO restaurants (name, slug, description, active) VALUES ('Restaurante de prueba', 'restaurante-prueba', 'Datos académicos ficticios', 1);
SET @restaurant_id = LAST_INSERT_ID();
INSERT INTO restaurant_branches (restaurant_id,name,address,city,active) VALUES (@restaurant_id,'Sede de prueba','Dirección ficticia','Cartagena',1);
SET @branch_id = LAST_INSERT_ID();
INSERT INTO restaurant_tables (restaurant_id,branch_id,table_number,capacity) VALUES (@restaurant_id,@branch_id,1,4),(@restaurant_id,@branch_id,2,4);
INSERT INTO menu_products (restaurant_id,name,description,category,price,currency,available) VALUES (@restaurant_id,'Producto de prueba','Artículo ficticio','Menú',18000,'COP',1);
-- Las cuentas se crean con la CLI para almacenar contraseñas protegidas.
