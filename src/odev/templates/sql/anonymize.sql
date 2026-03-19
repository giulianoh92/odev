-- Script de Anonimizacion de Base de Datos
-- Reemplaza datos personales en res_partner con datos falsos.
-- Preserva partners del sistema (id <= 3) y el usuario admin.

BEGIN;

-- Anonimizar nombres de partners (omitir partners del sistema)
UPDATE res_partner
SET name = 'Partner ' || id,
    email = 'partner_' || id || '@example.com',
    phone = '+1-555-' || LPAD(id::text, 4, '0'),
    mobile = NULL,
    street = id || ' Example Street',
    street2 = NULL,
    city = 'Example City',
    zip = '00000',
    website = NULL,
    comment = NULL,
    vat = NULL
WHERE id > 3;

-- Resetear todas las passwords de usuarios a 'admin' (excepto public/portal)
UPDATE res_users
SET password = 'admin'
WHERE id > 2
  AND active = true;

-- Limpiar direcciones de email de alias de correo
UPDATE mail_alias
SET alias_contact = 'everyone'
WHERE id > 0;

COMMIT;
