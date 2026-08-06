-- Normalize expert-knowledge and external-data references from message JSON.
-- Existing conversation history is intentionally cleared for this migration.

PRAGMA foreign_keys = OFF;

BEGIN;

DELETE FROM chat_conversation;
DROP TABLE IF EXISTS chat_message_expert_knowledge;
DROP TABLE IF EXISTS chat_message_external_data;
DROP TABLE IF EXISTS chat_conversation_message;

CREATE TABLE chat_conversation_message (
    id TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content_json TEXT NOT NULL DEFAULT '""',
    sort_order INTEGER NOT NULL DEFAULT 0,
    data_sources_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (conversation_id, id),
    FOREIGN KEY (conversation_id) REFERENCES chat_conversation(id) ON DELETE CASCADE
);

CREATE TABLE chat_message_expert_knowledge (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,
    message_id TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    title TEXT NOT NULL DEFAULT '',
    anchor_description TEXT NOT NULL DEFAULT '',
    system_prompt TEXT NOT NULL DEFAULT '',
    source_created_at TEXT NOT NULL DEFAULT '',
    source_updated_at TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (conversation_id, message_id, sort_order),
    FOREIGN KEY (conversation_id, message_id)
        REFERENCES chat_conversation_message(conversation_id, id)
        ON DELETE CASCADE
);

CREATE TABLE chat_message_external_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,
    message_id TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT '',
    response TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (conversation_id, message_id, sort_order),
    FOREIGN KEY (conversation_id, message_id)
        REFERENCES chat_conversation_message(conversation_id, id)
        ON DELETE CASCADE
);

CREATE UNIQUE INDEX idx_chat_message_conversation_order
ON chat_conversation_message(conversation_id, sort_order);

CREATE INDEX idx_chat_expert_knowledge_message
ON chat_message_expert_knowledge(conversation_id, message_id, sort_order);

CREATE INDEX idx_chat_external_data_message
ON chat_message_external_data(conversation_id, message_id, sort_order);

INSERT OR REPLACE INTO membership_schema_migrations (version, description)
VALUES ('V1.4', 'Normalize chatbot expert knowledge and external data references');

COMMIT;

PRAGMA foreign_keys = ON;
