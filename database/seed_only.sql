-- ================================================
-- SEED ONLY: Poblar datos sin recrear tablas
-- Ejecutar después de schema.sql si las tablas ya existen
-- pero están vacías (o para re-poblar datos de configuración)
-- ================================================

-- Limpiar datos de configuración existentes
TRUNCATE TABLE careers CASCADE;
TRUNCATE TABLE campuses CASCADE;
TRUNCATE TABLE objection_playbook CASCADE;
-- NOTA: No truncamos advisors para no perder asesores ya configurados

-- ================================================
-- Planteles
-- NOTA: location_id son placeholders, reemplazar con IDs reales de GHL
-- ================================================

INSERT INTO campuses (name, location_id, address, phone, map_url, website_url) VALUES
('Puebla', 'SOz5nfbI23Xm9mXC51bI',
 'Av. Orión Sur 1549, Col. Reserva Territorial Atlixcáyotl, Puebla, Pue. C.P. 72590',
 '222-169-1699 / 222-469-3998',
 'https://maps.google.com/?q=Colegio+San+Angel+Puebla',
 'https://sanangel.edu.mx/'),
('Poza Rica', 'epK2kqk7MkT8t0OBudqP',
 'Carr. Poza Rica - Cazones Fracción A2, Parcela 26B, Col. La Rueda, Poza Rica, Ver. C.P. 93306',
 '782-111-5970',
 'https://maps.google.com/?q=Colegio+San+Angel+Poza+Rica',
 'https://sanangel.edu.mx/'),
('Coatzacoalcos', 'UNorB3dhUdmtfbdjMAOc',
 'Col. Predio Rústico Santa Rosa, Av. Universidad Veracruzana 2920, Fovissste, Coatzacoalcos, Ver. C.P. 96536',
 '921-210-6827',
 'https://maps.google.com/?q=Colegio+San+Angel+Coatzacoalcos',
 'https://sanangel.edu.mx/');

-- ================================================
-- Niveles educativos por plantel
-- ================================================

-- PUEBLA: Preescolar, Primaria, Secundaria, Bachillerato
INSERT INTO careers (campus_id, name, program_type, website_url) VALUES
((SELECT id FROM campuses WHERE name = 'Puebla'), 'Preescolar', 'preescolar', 'https://sanangel.edu.mx/nivel/preescolar/'),
((SELECT id FROM campuses WHERE name = 'Puebla'), 'Primaria', 'primaria', 'https://sanangel.edu.mx/nivel/primaria/'),
((SELECT id FROM campuses WHERE name = 'Puebla'), 'Secundaria', 'secundaria', 'https://sanangel.edu.mx/nivel/secundaria/'),
((SELECT id FROM campuses WHERE name = 'Puebla'), 'Bachillerato', 'bachillerato', 'https://sanangel.edu.mx/nivel/bachillerato/');

-- POZA RICA: Primaria, Secundaria, Bachillerato (sin Preescolar)
INSERT INTO careers (campus_id, name, program_type, website_url) VALUES
((SELECT id FROM campuses WHERE name = 'Poza Rica'), 'Primaria', 'primaria', 'https://sanangel.edu.mx/nivel/primaria/'),
((SELECT id FROM campuses WHERE name = 'Poza Rica'), 'Secundaria', 'secundaria', 'https://sanangel.edu.mx/nivel/secundaria/'),
((SELECT id FROM campuses WHERE name = 'Poza Rica'), 'Bachillerato', 'bachillerato', 'https://sanangel.edu.mx/nivel/bachillerato/');

-- COATZACOALCOS: Preescolar, Primaria, Secundaria, Bachillerato
INSERT INTO careers (campus_id, name, program_type, website_url) VALUES
((SELECT id FROM campuses WHERE name = 'Coatzacoalcos'), 'Preescolar', 'preescolar', 'https://sanangel.edu.mx/nivel/preescolar/'),
((SELECT id FROM campuses WHERE name = 'Coatzacoalcos'), 'Primaria', 'primaria', 'https://sanangel.edu.mx/nivel/primaria/'),
((SELECT id FROM campuses WHERE name = 'Coatzacoalcos'), 'Secundaria', 'secundaria', 'https://sanangel.edu.mx/nivel/secundaria/'),
((SELECT id FROM campuses WHERE name = 'Coatzacoalcos'), 'Bachillerato', 'bachillerato', 'https://sanangel.edu.mx/nivel/bachillerato/');

-- ================================================
-- Objection Playbook (adaptado K-12)
-- ================================================

INSERT INTO objection_playbook (trigger_keywords, category, response_template, redirect_to_booking, priority) VALUES

(ARRAY['precio', 'costo', 'cuanto cuesta', 'mensualidad', 'colegiatura', 'cuánto', 'cuanto', 'tarifa', 'inversión', 'inversion', 'pago'],
 'colegiaturas',
 'Tenemos planes de pago accesibles y becas que se adaptan a cada familia. En la cita, el asesor te dará la cotización exacta con las mejores opciones para ti.',
 TRUE, 10),

(ARRAY['beca', 'descuento', 'apoyo económico', 'apoyo economico', 'financiamiento', 'promoción', 'promocion', 'hermanos'],
 'becas',
 '¡Sí tenemos becas y descuentos! Manejamos diferentes tipos de apoyo, incluyendo descuentos por hermanos. El asesor evaluará cuál es la mejor opción para tu familia en la cita.',
 TRUE, 9),

(ARRAY['horario', 'hora de entrada', 'hora de salida', 'actividades', 'extraescolar', 'deportes', 'taller', 'talleres', 'after school', 'tiempo completo'],
 'horarios',
 'Nuestros horarios están diseñados para adaptarse a las necesidades de las familias, y ofrecemos actividades extraescolares muy completas. El asesor te dará todos los detalles de horarios y actividades en tu cita.',
 TRUE, 8),

(ARRAY['transporte', 'camión', 'ruta', 'rutas', 'autobús', 'autobus', 'cómo llego', 'como llego', 'pasan por mi hijo'],
 'transporte',
 'Contamos con servicio de transporte escolar con rutas que cubren diferentes zonas. En la cita podrás conocer las rutas disponibles y los costos del servicio.',
 TRUE, 7),

(ARRAY['método', 'metodo', 'metodología', 'metodologia', 'modelo educativo', 'plan de estudios', 'enseñanza', 'ensenanza', 'bilingüe', 'bilingue', 'inglés', 'ingles', 'nivel académico', 'nivel academico'],
 'modelo_educativo',
 'En Colegio San Ángel nos enfocamos en una educación integral con enfoque bilingüe y desarrollo de valores. El asesor te explicará nuestro modelo educativo a detalle en tu cita.',
 TRUE, 8),

(ARRAY['instalaciones', 'seguridad', 'cámaras', 'camaras', 'laboratorio', 'cancha', 'biblioteca', 'comedor', 'cafetería', 'cafeteria', 'áreas', 'areas'],
 'instalaciones',
 'Tenemos instalaciones modernas y seguras, diseñadas para el bienestar de los alumnos. En la cita podrás conocer el plantel personalmente y ver nuestras instalaciones.',
 TRUE, 6),

(ARRAY['inscripción', 'inscripcion', 'inscribirme', 'inscribir', 'registrar', 'cómo me inscribo', 'como me inscribo', 'requisitos', 'documentos', 'papeles', 'proceso', 'fecha límite', 'fecha limite', 'cuándo empiezan', 'cuando empiezan'],
 'inscripcion',
 '¡El proceso de inscripción es muy sencillo! Solo necesitas agendar tu cita y el asesor te guiará paso a paso con los documentos y el registro.',
 TRUE, 9),

(ARRAY['uniforme', 'unifomes', 'útiles', 'utiles', 'materiales', 'libros', 'lista de útiles', 'lista de utiles', 'mochila'],
 'uniformes',
 'Tenemos uniformes institucionales y una lista de materiales accesible. El asesor te dará toda la información sobre uniformes y materiales en tu cita.',
 TRUE, 5),

(ARRAY['dónde están', 'donde estan', 'ubicación', 'ubicacion', 'dirección', 'direccion', 'dónde queda', 'donde queda', 'estacionamiento', 'mapa']::TEXT[],
 'ubicacion',
 'Tenemos planteles en Puebla, Poza Rica y Coatzacoalcos, todos bien ubicados y accesibles. En la cita podrás conocer el plantel personalmente.',
 TRUE, 5)

ON CONFLICT DO NOTHING;
