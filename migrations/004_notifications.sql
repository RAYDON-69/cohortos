-- CoachMate Notification System Schema
-- Version: 1.0

-- Notification templates table
CREATE TABLE IF NOT EXISTS notification_templates (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    name TEXT NOT NULL,
    template_type TEXT NOT NULL,
    channel TEXT NOT NULL,
    subject_template TEXT NOT NULL,
    body_template TEXT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    variables TEXT DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(tenant_id, name)
);

-- Notification channels table
CREATE TABLE IF NOT EXISTS notification_channels (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    channel_type TEXT NOT NULL,
    config TEXT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    priority INTEGER DEFAULT 5,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    created_at TEXT NOT NULL,
    UNIQUE(tenant_id, channel_type)
);

-- Notification preferences table
CREATE TABLE IF NOT EXISTS notification_preferences (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    channel_type TEXT NOT NULL,
    event_type TEXT NOT NULL,
    enabled BOOLEAN DEFAULT TRUE,
    scheduled_time TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(user_id, tenant_id, channel_type, event_type)
);

-- Notification queue table
CREATE TABLE IF NOT EXISTS notification_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    notification_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    channel_type TEXT NOT NULL,
    subject TEXT NOT NULL,
    content TEXT NOT NULL,
    priority INTEGER DEFAULT 5,
    status TEXT NOT NULL DEFAULT 'pending',
    scheduled_at TEXT,
    sent_at TEXT,
    retry_count INTEGER DEFAULT 0,
    error_message TEXT,
    template_id TEXT,
    metadata TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    UNIQUE(notification_id, channel_type)
);

-- Notifications history table
CREATE TABLE IF NOT EXISTS notifications (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    channel_type TEXT NOT NULL,
    subject TEXT NOT NULL,
    content TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'sent',
    sent_at TEXT,
    delivered_at TEXT,
    read_at TEXT,
    retry_count INTEGER DEFAULT 0,
    error_message TEXT,
    metadata TEXT DEFAULT '{}',
    created_at TEXT NOT NULL
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_queue_tenant ON notification_queue(tenant_id);
CREATE INDEX IF NOT EXISTS idx_queue_status ON notification_queue(status);
CREATE INDEX IF NOT EXISTS idx_queue_priority ON notification_queue(priority DESC, created_at ASC);
CREATE INDEX IF NOT EXISTS idx_notifications_tenant ON notifications(tenant_id);
CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id);
CREATE INDEX IF NOT EXISTS idx_notifications_created ON notifications(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_preferences_user ON notification_preferences(user_id);
CREATE INDEX IF NOT EXISTS idx_preferences_event ON notification_preferences(event_type);
CREATE INDEX IF NOT EXISTS idx_channels_tenant ON notification_channels(tenant_id);
CREATE INDEX IF NOT EXISTS idx_templates_tenant ON notification_templates(tenant_id);

-- Create triggers for cleanup
CREATE TRIGGER IF NOT EXISTS cleanup_old_notifications
AFTER INSERT ON notifications
BEGIN
    -- Keep only last 1000 notifications per user
    DELETE FROM notifications
    WHERE id IN (
        SELECT id FROM (
            SELECT id FROM notifications
            ORDER BY created_at DESC
            LIMIT -1000 OFFSET 1000
        )
    );
END;

-- Create view for notification metrics
CREATE VIEW IF NOT EXISTS notification_metrics AS
SELECT
    tenant_id,
    DATE(created_at) as notification_date,
    COUNT(*) as total_sent,
    SUM(CASE WHEN status = 'sent' THEN 1 ELSE 0 END) as delivered,
    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
    SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
    channel_type,
    COUNT(DISTINCT user_id) as unique_users
FROM notifications
GROUP BY tenant_id, DATE(created_at), channel_type;

-- Create view for notification delivery rates
CREATE VIEW IF NOT EXISTS notification_delivery_rates AS
SELECT
    tenant_id,
    channel_type,
    DATE(created_at) as date,
    COUNT(*) as total,
    SUM(CASE WHEN status = 'sent' THEN 1 ELSE 0 END) as successful,
    ROUND(SUM(CASE WHEN status = 'sent' THEN 1 ELSE 0 END) * 100.0 / COUNT(CASE WHEN status IN ('sent', 'failed') THEN 1 ELSE 0 END), 2) as success_rate
FROM notifications
WHERE status IN ('sent', 'failed')
GROUP BY tenant_id, channel_type, DATE(created_at);