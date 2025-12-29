-- Phase 2: SSOT Middleware Integration
-- Database migration for comprehensive request tracking

-- Create SSOT tracking table for all generation requests
CREATE TABLE IF NOT EXISTS ssot_tracking (
    id SERIAL PRIMARY KEY,
    request_id VARCHAR(255) UNIQUE NOT NULL,
    endpoint VARCHAR(500) NOT NULL,
    method VARCHAR(10) NOT NULL,
    user_id VARCHAR(100) DEFAULT 'system',
    parameters JSONB,
    user_agent TEXT,
    ip_address INET,
    status VARCHAR(50) NOT NULL DEFAULT 'initiated',
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITH TIME ZONE,
    processing_time INTEGER, -- milliseconds
    response_data JSONB,
    http_status INTEGER,
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_ssot_request_id ON ssot_tracking(request_id);
CREATE INDEX IF NOT EXISTS idx_ssot_user_id ON ssot_tracking(user_id);
CREATE INDEX IF NOT EXISTS idx_ssot_timestamp ON ssot_tracking(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_ssot_endpoint ON ssot_tracking(endpoint);
CREATE INDEX IF NOT EXISTS idx_ssot_status ON ssot_tracking(status);
CREATE INDEX IF NOT EXISTS idx_ssot_endpoint_method ON ssot_tracking(endpoint, method);

-- Create generation workflow decisions table
CREATE TABLE IF NOT EXISTS generation_workflow_decisions (
    id SERIAL PRIMARY KEY,
    request_id VARCHAR(255),
    function_name VARCHAR(255),
    status VARCHAR(50),
    processing_time FLOAT,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB,

    FOREIGN KEY (request_id) REFERENCES ssot_tracking(request_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_workflow_request_id ON generation_workflow_decisions(request_id);
CREATE INDEX IF NOT EXISTS idx_workflow_function ON generation_workflow_decisions(function_name);

-- Update generation_decisions table if it doesn't have proper structure
ALTER TABLE generation_decisions
ADD COLUMN IF NOT EXISTS request_id VARCHAR(255),
ADD COLUMN IF NOT EXISTS tracked_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP;

-- Create view for dashboard monitoring
CREATE OR REPLACE VIEW ssot_dashboard AS
SELECT
    date_trunc('hour', timestamp) as hour,
    endpoint,
    method,
    status,
    COUNT(*) as request_count,
    AVG(processing_time) as avg_processing_time,
    MAX(processing_time) as max_processing_time,
    MIN(processing_time) as min_processing_time,
    COUNT(CASE WHEN http_status >= 400 THEN 1 END) as error_count,
    COUNT(CASE WHEN http_status >= 500 THEN 1 END) as server_error_count
FROM ssot_tracking
WHERE timestamp > NOW() - INTERVAL '24 hours'
GROUP BY 1, 2, 3, 4
ORDER BY 1 DESC, request_count DESC;

-- Create view for endpoint performance analysis
CREATE OR REPLACE VIEW endpoint_performance AS
SELECT
    endpoint,
    method,
    COUNT(*) as total_requests,
    AVG(processing_time) as avg_time_ms,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY processing_time) as median_time_ms,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY processing_time) as p95_time_ms,
    PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY processing_time) as p99_time_ms,
    COUNT(CASE WHEN status = 'completed' THEN 1 END)::FLOAT / COUNT(*) * 100 as success_rate,
    COUNT(CASE WHEN http_status >= 400 THEN 1 END)::FLOAT / COUNT(*) * 100 as error_rate
FROM ssot_tracking
WHERE timestamp > NOW() - INTERVAL '7 days'
GROUP BY endpoint, method
HAVING COUNT(*) > 10
ORDER BY total_requests DESC;

-- Create view for generation decision analytics
CREATE OR REPLACE VIEW generation_decision_analytics AS
SELECT
    gd.decision_type,
    COUNT(*) as total_decisions,
    AVG(gd.confidence_score) as avg_confidence,
    MIN(gd.confidence_score) as min_confidence,
    MAX(gd.confidence_score) as max_confidence,
    COUNT(CASE WHEN pg.status = 'completed' THEN 1 END)::FLOAT / COUNT(*) * 100 as success_rate,
    AVG(CASE WHEN st.processing_time IS NOT NULL THEN st.processing_time END) as avg_processing_time
FROM generation_decisions gd
LEFT JOIN project_generations pg ON gd.generation_id = pg.id
LEFT JOIN ssot_tracking st ON gd.request_id = st.request_id
WHERE gd.timestamp > NOW() - INTERVAL '7 days'
GROUP BY gd.decision_type
ORDER BY total_decisions DESC;

-- Create materialized view for hourly metrics (refreshed via cron)
CREATE MATERIALIZED VIEW IF NOT EXISTS ssot_hourly_metrics AS
SELECT
    date_trunc('hour', timestamp) as hour,
    COUNT(*) as total_requests,
    COUNT(DISTINCT user_id) as unique_users,
    COUNT(DISTINCT endpoint) as unique_endpoints,
    AVG(processing_time) as avg_processing_time,
    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as successful_requests,
    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed_requests,
    SUM(CASE WHEN http_status >= 400 THEN 1 ELSE 0 END) as error_responses
FROM ssot_tracking
WHERE timestamp > NOW() - INTERVAL '30 days'
GROUP BY hour
ORDER BY hour DESC;

-- Create index on materialized view
CREATE INDEX IF NOT EXISTS idx_hourly_metrics_hour ON ssot_hourly_metrics(hour DESC);

-- Function to refresh materialized view
CREATE OR REPLACE FUNCTION refresh_ssot_metrics()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY ssot_hourly_metrics;
END;
$$ LANGUAGE plpgsql;

-- Create tracking statistics table
CREATE TABLE IF NOT EXISTS ssot_statistics (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL UNIQUE,
    total_requests INTEGER,
    unique_users INTEGER,
    unique_endpoints INTEGER,
    avg_processing_time FLOAT,
    success_rate FLOAT,
    error_rate FLOAT,
    peak_hour INTEGER,
    peak_requests INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_statistics_date ON ssot_statistics(date DESC);

-- Function to aggregate daily statistics
CREATE OR REPLACE FUNCTION aggregate_daily_statistics()
RETURNS void AS $$
BEGIN
    INSERT INTO ssot_statistics (
        date, total_requests, unique_users, unique_endpoints,
        avg_processing_time, success_rate, error_rate,
        peak_hour, peak_requests
    )
    SELECT
        CURRENT_DATE - INTERVAL '1 day',
        COUNT(*),
        COUNT(DISTINCT user_id),
        COUNT(DISTINCT endpoint),
        AVG(processing_time),
        COUNT(CASE WHEN status = 'completed' THEN 1 END)::FLOAT / COUNT(*) * 100,
        COUNT(CASE WHEN http_status >= 400 THEN 1 END)::FLOAT / COUNT(*) * 100,
        EXTRACT(HOUR FROM peak.hour),
        peak.max_requests
    FROM ssot_tracking
    CROSS JOIN LATERAL (
        SELECT
            date_trunc('hour', timestamp) as hour,
            COUNT(*) as max_requests
        FROM ssot_tracking
        WHERE DATE(timestamp) = CURRENT_DATE - INTERVAL '1 day'
        GROUP BY hour
        ORDER BY max_requests DESC
        LIMIT 1
    ) peak
    WHERE DATE(timestamp) = CURRENT_DATE - INTERVAL '1 day'
    GROUP BY peak.hour, peak.max_requests
    ON CONFLICT (date) DO UPDATE
    SET
        total_requests = EXCLUDED.total_requests,
        unique_users = EXCLUDED.unique_users,
        unique_endpoints = EXCLUDED.unique_endpoints,
        avg_processing_time = EXCLUDED.avg_processing_time,
        success_rate = EXCLUDED.success_rate,
        error_rate = EXCLUDED.error_rate,
        peak_hour = EXCLUDED.peak_hour,
        peak_requests = EXCLUDED.peak_requests,
        created_at = CURRENT_TIMESTAMP;
END;
$$ LANGUAGE plpgsql;

-- Grant permissions (adjust user as needed)
GRANT SELECT ON ssot_tracking TO patrick;
GRANT INSERT, UPDATE ON ssot_tracking TO patrick;
GRANT SELECT ON generation_workflow_decisions TO patrick;
GRANT INSERT ON generation_workflow_decisions TO patrick;
GRANT SELECT ON ssot_dashboard TO patrick;
GRANT SELECT ON endpoint_performance TO patrick;
GRANT SELECT ON generation_decision_analytics TO patrick;
GRANT SELECT ON ssot_hourly_metrics TO patrick;
GRANT EXECUTE ON FUNCTION refresh_ssot_metrics() TO patrick;
GRANT EXECUTE ON FUNCTION aggregate_daily_statistics() TO patrick;