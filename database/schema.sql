-- ================================================
-- SCHEMA COMPLETO: Colegio San Ángel - Agente Luca
-- Base de datos para el agente de admisiones K-12
-- 3 planteles: Puebla, Poza Rica, Coatzacoalcos
-- ================================================

-- ================================================
-- LIMPIEZA: Eliminar tablas anteriores si existen
-- ================================================

-- Primero eliminar triggers y funciones (sin referenciar tablas)
DO $$
BEGIN
    DROP TRIGGER IF EXISTS trigger_update_conversation_timestamp ON messages;
EXCEPTION
    WHEN undefined_table THEN NULL;
END $$;

DO $$
BEGIN
    DROP TRIGGER IF EXISTS trigger_update_lead_state_timestamp ON lead_states;
EXCEPTION
    WHEN undefined_table THEN NULL;
END $$;

DO $$
BEGIN
    DROP TRIGGER IF EXISTS trigger_update_objection_playbook_timestamp ON objection_playbook;
EXCEPTION
    WHEN undefined_table THEN NULL;
END $$;

DROP FUNCTION IF EXISTS update_conversation_timestamp();
DROP FUNCTION IF EXISTS update_lead_state_timestamp();
DROP FUNCTION IF EXISTS update_objection_playbook_timestamp();

-- Luego eliminar tablas (CASCADE elimina dependencias)
DROP TABLE IF EXISTS messages CASCADE;
DROP TABLE IF EXISTS conversations CASCADE;
DROP TABLE IF EXISTS careers CASCADE;
DROP TABLE IF EXISTS campuses CASCADE;
DROP TABLE IF EXISTS lead_states CASCADE;
DROP TABLE IF EXISTS advisors CASCADE;
DROP TABLE IF EXISTS objection_playbook CASCADE;

-- ================================================
-- TABLA: conversations
-- Almacena cada conversación única por contact_id
-- ================================================
CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contact_id VARCHAR(255) NOT NULL UNIQUE,
    location_id VARCHAR(255),
    channel VARCHAR(50),
    status VARCHAR(50) DEFAULT 'active',
    is_human_active BOOLEAN DEFAULT FALSE,
    human_takeover_at TIMESTAMPTZ DEFAULT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_conversations_contact_id ON conversations(contact_id);
CREATE INDEX idx_conversations_location_id ON conversations(location_id);
CREATE INDEX idx_conversations_status ON conversations(status);
CREATE INDEX idx_conversations_human_active ON conversations(contact_id) WHERE is_human_active = TRUE;

-- ================================================
-- TABLA: messages
-- Almacena cada mensaje de la conversación
-- ================================================
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_messages_conversation_id ON messages(conversation_id);
CREATE INDEX idx_messages_created_at ON messages(created_at);
CREATE INDEX idx_messages_conversation_created ON messages(conversation_id, created_at);

-- ================================================
-- TABLA: campuses (planteles)
-- 3 planteles de Colegio San Ángel
-- ================================================
CREATE TABLE campuses (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    location_id VARCHAR(50),
    address TEXT,
    phone VARCHAR(100),
    map_url TEXT,
    website_url TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_campuses_name ON campuses(name);
CREATE INDEX idx_campuses_location_id ON campuses(location_id);

-- ================================================
-- TABLA: careers (niveles educativos)
-- Tabla se llama "careers" por compatibilidad con campus_service.py
-- Contiene niveles K-12: preescolar, primaria, secundaria, bachillerato
-- ================================================
CREATE TABLE careers (
    id SERIAL PRIMARY KEY,
    campus_id INTEGER REFERENCES campuses(id) ON DELETE CASCADE,
    name VARCHAR(200) NOT NULL,
    program_type VARCHAR(20) DEFAULT 'primaria',
    website_url TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_careers_campus_id ON careers(campus_id);

-- ================================================
-- TABLA: lead_states
-- Rastrea el estado de captación de datos del lead
-- 5 datos: plantel, nivel educativo, nombre padre/tutor, teléfono, email
-- ================================================
CREATE TABLE lead_states (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contact_id VARCHAR(255) UNIQUE NOT NULL,
    location_id VARCHAR(255),
    campus VARCHAR(255),
    programa VARCHAR(255),
    nombre_completo VARCHAR(255),
    telefono VARCHAR(50),
    email VARCHAR(255),
    current_step INTEGER DEFAULT 1,
    is_complete BOOLEAN DEFAULT FALSE,
    booking_sent_at TIMESTAMPTZ DEFAULT NULL,
    post_booking_count INTEGER DEFAULT 0,
    score INTEGER DEFAULT 0,
    channel VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_lead_states_contact_id ON lead_states(contact_id);
CREATE INDEX idx_lead_states_location_id ON lead_states(location_id);
CREATE INDEX idx_lead_states_is_complete ON lead_states(is_complete);
CREATE INDEX idx_lead_states_score ON lead_states(score);

-- ================================================
-- TABLA: advisors
-- Asesores por plantel con booking links para round-robin
-- ================================================
CREATE TABLE advisors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    campus VARCHAR(100) NOT NULL,
    location_id VARCHAR(50),
    booking_link VARCHAR(500) NOT NULL,
    ghl_user_id VARCHAR(50),
    is_active BOOLEAN DEFAULT TRUE,
    assigned_count INTEGER DEFAULT 0,
    last_assigned_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_advisors_campus ON advisors(campus);
CREATE INDEX idx_advisors_active ON advisors(campus, is_active);
CREATE INDEX idx_advisors_location_id ON advisors(location_id, is_active);
CREATE INDEX idx_advisors_ghl_user_id ON advisors(ghl_user_id);

-- ================================================
-- TABLA: objection_playbook
-- Playbook de objeciones para manejo estandarizado
-- Adaptado al contexto K-12 de Colegio San Ángel
-- ================================================
CREATE TABLE objection_playbook (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trigger_keywords TEXT[] NOT NULL,
    category VARCHAR(100) NOT NULL,
    response_template TEXT NOT NULL,
    redirect_to_booking BOOLEAN DEFAULT TRUE,
    is_active BOOLEAN DEFAULT TRUE,
    priority INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_objection_playbook_category ON objection_playbook(category);
CREATE INDEX idx_objection_playbook_active ON objection_playbook(is_active);
CREATE INDEX idx_objection_playbook_priority ON objection_playbook(priority DESC);

-- ================================================
-- FUNCIONES Y TRIGGERS
-- ================================================

-- Trigger: Actualizar updated_at en conversations al insertar mensaje
CREATE OR REPLACE FUNCTION update_conversation_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE conversations
    SET updated_at = NOW()
    WHERE id = NEW.conversation_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_conversation_timestamp
    AFTER INSERT ON messages
    FOR EACH ROW
    EXECUTE FUNCTION update_conversation_timestamp();

-- Trigger: Actualizar updated_at en lead_states
CREATE OR REPLACE FUNCTION update_lead_state_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_lead_state_timestamp
    BEFORE UPDATE ON lead_states
    FOR EACH ROW
    EXECUTE FUNCTION update_lead_state_timestamp();

-- Trigger: Actualizar updated_at en objection_playbook
CREATE OR REPLACE FUNCTION update_objection_playbook_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_objection_playbook_timestamp
    BEFORE UPDATE ON objection_playbook
    FOR EACH ROW
    EXECUTE FUNCTION update_objection_playbook_timestamp();

-- ================================================
-- COMENTARIOS
-- ================================================
COMMENT ON TABLE conversations IS 'Conversaciones únicas por contact_id de GHL';
COMMENT ON TABLE messages IS 'Mensajes individuales de cada conversación';
COMMENT ON TABLE campuses IS 'Planteles de Colegio San Ángel (Puebla, Poza Rica, Coatzacoalcos)';
COMMENT ON TABLE careers IS 'Niveles educativos por plantel (preescolar, primaria, secundaria, bachillerato)';
COMMENT ON TABLE lead_states IS 'Estado de captación de datos del lead (5 datos + booking + scoring)';
COMMENT ON TABLE advisors IS 'Asesores por plantel con booking links para rotación round-robin';
COMMENT ON TABLE objection_playbook IS 'Playbook de objeciones adaptado al contexto K-12';

COMMENT ON COLUMN conversations.contact_id IS 'ID único del contacto en GoHighLevel';
COMMENT ON COLUMN conversations.is_human_active IS 'Flag permanente: TRUE = humano tomó la conversación, bot se calla';
COMMENT ON COLUMN messages.role IS 'Rol del mensaje: user (padre/tutor) o assistant (Luca)';
COMMENT ON COLUMN lead_states.current_step IS 'Paso del flujo: 1=Plantel, 2=Nivel, 3=Nombre, 4=Teléfono, 5=Email';
COMMENT ON COLUMN lead_states.programa IS 'Nivel educativo de interés (preescolar, primaria, secundaria, bachillerato)';
COMMENT ON COLUMN advisors.assigned_count IS 'Contador para round-robin equitativo';
COMMENT ON COLUMN advisors.ghl_user_id IS 'ID del usuario en GHL para matchear con contact.assignedTo';

-- ================================================
-- DATOS SEED: Planteles
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
-- DATOS SEED: Niveles educativos por plantel
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
-- DATOS SEED: Objection Playbook (adaptado K-12)
-- ================================================

INSERT INTO objection_playbook (trigger_keywords, category, response_template, redirect_to_booking, priority) VALUES

-- 1. Colegiaturas / Costos
(ARRAY['precio', 'costo', 'cuanto cuesta', 'mensualidad', 'colegiatura', 'cuánto', 'cuanto', 'tarifa', 'inversión', 'inversion', 'pago'],
 'colegiaturas',
 'Tenemos planes de pago accesibles y becas que se adaptan a cada familia. En la cita, el asesor te dará la cotización exacta con las mejores opciones para ti.',
 TRUE, 10),

-- 2. Becas / Descuentos
(ARRAY['beca', 'descuento', 'apoyo económico', 'apoyo economico', 'financiamiento', 'promoción', 'promocion', 'hermanos'],
 'becas',
 '¡Sí tenemos becas y descuentos! Manejamos diferentes tipos de apoyo, incluyendo descuentos por hermanos. El asesor evaluará cuál es la mejor opción para tu familia en la cita.',
 TRUE, 9),

-- 3. Horarios / Actividades extraescolares
(ARRAY['horario', 'hora de entrada', 'hora de salida', 'actividades', 'extraescolar', 'deportes', 'taller', 'talleres', 'after school', 'tiempo completo'],
 'horarios',
 'Nuestros horarios están diseñados para adaptarse a las necesidades de las familias, y ofrecemos actividades extraescolares muy completas. El asesor te dará todos los detalles de horarios y actividades en tu cita.',
 TRUE, 8),

-- 4. Transporte escolar
(ARRAY['transporte', 'camión', 'ruta', 'rutas', 'autobús', 'autobus', 'cómo llego', 'como llego', 'pasan por mi hijo'],
 'transporte',
 'Contamos con servicio de transporte escolar con rutas que cubren diferentes zonas. En la cita podrás conocer las rutas disponibles y los costos del servicio.',
 TRUE, 7),

-- 5. Metodología / Modelo educativo
(ARRAY['método', 'metodo', 'metodología', 'metodologia', 'modelo educativo', 'plan de estudios', 'enseñanza', 'ensenanza', 'bilingüe', 'bilingue', 'inglés', 'ingles', 'nivel académico', 'nivel academico'],
 'modelo_educativo',
 'En Colegio San Ángel nos enfocamos en una educación integral con enfoque bilingüe y desarrollo de valores. El asesor te explicará nuestro modelo educativo a detalle en tu cita.',
 TRUE, 8),

-- 6. Instalaciones / Seguridad
(ARRAY['instalaciones', 'seguridad', 'cámaras', 'camaras', 'laboratorio', 'cancha', 'biblioteca', 'comedor', 'cafetería', 'cafeteria', 'áreas', 'areas'],
 'instalaciones',
 'Tenemos instalaciones modernas y seguras, diseñadas para el bienestar de los alumnos. En la cita podrás conocer el plantel personalmente y ver nuestras instalaciones.',
 TRUE, 6),

-- 7. Inscripción / Proceso
(ARRAY['inscripción', 'inscripcion', 'inscribirme', 'inscribir', 'registrar', 'cómo me inscribo', 'como me inscribo', 'requisitos', 'documentos', 'papeles', 'proceso', 'fecha límite', 'fecha limite', 'cuándo empiezan', 'cuando empiezan'],
 'inscripcion',
 '¡El proceso de inscripción es muy sencillo! Solo necesitas agendar tu cita y el asesor te guiará paso a paso con los documentos y el registro.',
 TRUE, 9),

-- 8. Uniformes / Materiales
(ARRAY['uniforme', 'unifomes', 'útiles', 'utiles', 'materiales', 'libros', 'lista de útiles', 'lista de utiles', 'mochila'],
 'uniformes',
 'Tenemos uniformes institucionales y una lista de materiales accesible. El asesor te dará toda la información sobre uniformes y materiales en tu cita.',
 TRUE, 5),

-- 9. Ubicación / Plantel
(ARRAY['dónde están', 'donde estan', 'ubicación', 'ubicacion', 'dirección', 'direccion', 'dónde queda', 'donde queda', 'estacionamiento', 'mapa']::TEXT[],
 'ubicacion',
 'Tenemos planteles en Puebla, Poza Rica y Coatzacoalcos, todos bien ubicados y accesibles. En la cita podrás conocer el plantel personalmente.',
 TRUE, 5)

ON CONFLICT DO NOTHING;

-- ================================================
-- DATOS SEED: Advisors (PLACEHOLDER - reemplazar con datos reales)
-- ================================================
-- PUEBLA
INSERT INTO advisors (name, campus, location_id, booking_link, ghl_user_id) VALUES
('Graciela Castañeda Ulloa', 'Puebla', 'SOz5nfbI23Xm9mXC51bI', 'https://link.superleads.mx/widget/booking/o33ctHxdbcr7Q7wmarJY', 'U7NS5gsTObDBBdvPSoHA'),
('Aranzazú Arteaga Medina', 'Puebla', 'SOz5nfbI23Xm9mXC51bI', 'https://link.superleads.mx/widget/booking/WPWBD7z4PvAjdqcp4N5d', 'DhkTOP362oCPu07QV5f7'),
('Michell Alexis Guerrero Fernández', 'Puebla', 'SOz5nfbI23Xm9mXC51bI', 'https://link.superleads.mx/widget/booking/w3hle8mTMay6OsFhlPDB', 'OAKT3f0NDEBF2eftSKPG');

-- POZA RICA (agregar asesores cuando estén disponibles)
-- INSERT INTO advisors (name, campus, location_id, booking_link, ghl_user_id) VALUES
-- ('Asesor Poza Rica', 'Poza Rica', 'epK2kqk7MkT8t0OBudqP', 'https://link.superleads.mx/widget/booking/XXX', 'XXX');

-- COATZACOALCOS (agregar asesores cuando estén disponibles)
-- INSERT INTO advisors (name, campus, location_id, booking_link, ghl_user_id) VALUES
-- ('Asesor Coatzacoalcos', 'Coatzacoalcos', 'UNorB3dhUdmtfbdjMAOc', 'https://link.superleads.mx/widget/booking/XXX', 'XXX');
