-- Account-scoped chatbot conversation history.

PRAGMA foreign_keys = ON;

BEGIN;

CREATE TABLE IF NOT EXISTS chat_conversation (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '新對話',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT,

    FOREIGN KEY (user_id) REFERENCES membership_user(id)
);

CREATE TABLE IF NOT EXISTS chat_conversation_message (
    id TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content_json TEXT NOT NULL DEFAULT '""',
    sort_order INTEGER NOT NULL DEFAULT 0,
    data_sources_json TEXT NOT NULL DEFAULT '[]',
    expert_knowledge_json TEXT NOT NULL DEFAULT '[]',
    external_data_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (conversation_id, id),

    FOREIGN KEY (conversation_id) REFERENCES chat_conversation(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_chat_conversation_user_updated
ON chat_conversation(user_id, updated_at DESC)
WHERE deleted_at IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_chat_message_conversation_order
ON chat_conversation_message(conversation_id, sort_order);

INSERT OR REPLACE INTO membership_schema_migrations (version, description)
VALUES ('V1.3', 'Add account-scoped chatbot conversation history');

COMMIT;
