-- CoachMate Portion 0: Row-Level Security Policies
-- Ensures tenant isolation for all core tables

-- Enable RLS on all tables
ALTER TABLE centres ENABLE ROW LEVEL SECURITY;
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE roles ENABLE ROW LEVEL SECURITY;
ALTER TABLE role_permissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_configs ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;

-- Policy: Users can only access their own tenant's data
CREATE POLICY tenant_isolation_centres ON centres
    FOR ALL USING (true); -- Centres are global system objects

-- Policy: Users can only see their own tenant's users
CREATE POLICY tenant_isolation_users ON users
    FOR ALL USING (tenant_id = current_setting('app.current_tenant', true)::UUID);

-- Policy: Users can only access their own tenant's roles
CREATE POLICY tenant_isolation_roles ON roles
    FOR ALL USING (tenant_id = current_setting('app.current_tenant', true)::UUID);

-- Policy: Users can only access their own tenant's role permissions
CREATE POLICY tenant_isolation_role_permissions ON role_permissions
    FOR ALL USING (tenant_id = current_setting('app.current_tenant', true)::UUID);

-- Policy: Users can only access their own tenant's configs
CREATE POLICY tenant_isolation_tenant_configs ON tenant_configs
    FOR ALL USING (tenant_id = current_setting('app.current_tenant', true)::UUID);

-- Policy: Users can only see audit logs for their tenant
CREATE POLICY tenant_isolation_audit_logs ON audit_logs
    FOR ALL USING (tenant_id = current_setting('app.current_tenant', true)::UUID);

-- Policy: System users (super-admin) can access all data
-- This will be implemented in the application layer for security
CREATE POLICY system_admin_override ON centres
    FOR ALL USING (has_role('super_admin'));

CREATE POLICY system_admin_override ON users
    FOR ALL USING (has_role('super_admin'));

CREATE POLICY system_admin_override ON roles
    FOR ALL USING (has_role('super_admin'));

CREATE POLICY system_admin_override ON role_permissions
    FOR ALL USING (has_role('super_admin'));

CREATE POLICY system_admin_override ON tenant_configs
    FOR ALL USING (has_role('super_admin'));

CREATE POLICY system_admin_override ON audit_logs
    FOR ALL USING (has_role('super_admin'));

-- Function to set current tenant (called from application)
CREATE OR REPLACE FUNCTION set_current_tenant(tenant_id UUID)
RETURNS void AS $$
BEGIN
    SET LOCAL app.current_tenant = tenant_id::text;
END;
$$ LANGUAGE plpgsql;

-- Function to get current tenant
CREATE OR REPLACE FUNCTION get_current_tenant()
RETURNS UUID AS $$
BEGIN
    RETURN current_setting('app.current_tenant', true)::UUID;
END;
$$ LANGUAGE plpgsql;