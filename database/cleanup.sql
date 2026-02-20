-- ================================================
-- SCRIPT DE LIMPIEZA: Vaciar SOLO el contenido
-- Mantiene las tablas y estructura, solo borra los datos
-- ================================================

-- Vaciar mensajes primero (tiene FK a conversations)
TRUNCATE TABLE messages CASCADE;

-- Vaciar conversaciones
TRUNCATE TABLE conversations CASCADE;

-- Vaciar lead_states
TRUNCATE TABLE lead_states CASCADE;

-- NO vaciar campuses, careers, advisors ni objection_playbook
-- (son datos de configuración, no transaccionales)

-- Confirmar limpieza
SELECT 'Datos transaccionales eliminados (conversations, messages, lead_states). Tablas de configuración intactas.' AS resultado;
