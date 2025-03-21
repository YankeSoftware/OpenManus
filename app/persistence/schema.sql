-- Agent Persistence Schema

-- Agents table - Stores information about agents
CREATE TABLE IF NOT EXISTS agents (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    description TEXT,
    creation_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    code_path TEXT,
    system_prompt TEXT,
    version INTEGER DEFAULT 1,
    parent_id TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    metadata TEXT,
    FOREIGN KEY (parent_id) REFERENCES agents(id)
);

-- Agent capabilities - Stores agent capabilities
CREATE TABLE IF NOT EXISTS capabilities (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    implementation_path TEXT,
    creation_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    version INTEGER DEFAULT 1,
    metadata TEXT
);

-- Agent-capability mapping
CREATE TABLE IF NOT EXISTS agent_capabilities (
    agent_id TEXT NOT NULL,
    capability_id TEXT NOT NULL,
    added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (agent_id, capability_id),
    FOREIGN KEY (agent_id) REFERENCES agents(id),
    FOREIGN KEY (capability_id) REFERENCES capabilities(id)
);

-- Tools table - Stores information about available tools
CREATE TABLE IF NOT EXISTS tools (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    implementation_path TEXT,
    creation_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    metadata TEXT
);

-- Agent tool usage statistics
CREATE TABLE IF NOT EXISTS tool_usage_stats (
    agent_id TEXT NOT NULL,
    tool_id TEXT NOT NULL,
    usage_count INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0,
    average_execution_time REAL,
    last_used TIMESTAMP,
    PRIMARY KEY (agent_id, tool_id),
    FOREIGN KEY (agent_id) REFERENCES agents(id),
    FOREIGN KEY (tool_id) REFERENCES tools(id)
);

-- Execution sessions
CREATE TABLE IF NOT EXISTS execution_sessions (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    end_time TIMESTAMP,
    status TEXT,
    request TEXT,
    summary TEXT,
    metadata TEXT,
    FOREIGN KEY (agent_id) REFERENCES agents(id)
);

-- Execution steps - Detailed execution history
CREATE TABLE IF NOT EXISTS execution_steps (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    step_number INTEGER NOT NULL,
    tool_id TEXT,
    input TEXT,
    output TEXT,
    start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    end_time TIMESTAMP,
    status TEXT,
    error TEXT,
    FOREIGN KEY (session_id) REFERENCES execution_sessions(id),
    FOREIGN KEY (agent_id) REFERENCES agents(id),
    FOREIGN KEY (tool_id) REFERENCES tools(id)
);

-- Agent memory storage
CREATE TABLE IF NOT EXISTS agent_memory (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    creation_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_accessed TIMESTAMP,
    expiry_date TIMESTAMP,
    access_count INTEGER DEFAULT 0,
    FOREIGN KEY (agent_id) REFERENCES agents(id)
);

-- Agent relationships - For multi-agent coordination
CREATE TABLE IF NOT EXISTS agent_relationships (
    agent1_id TEXT NOT NULL,
    agent2_id TEXT NOT NULL,
    relationship_type TEXT NOT NULL,
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata TEXT,
    PRIMARY KEY (agent1_id, agent2_id, relationship_type),
    FOREIGN KEY (agent1_id) REFERENCES agents(id),
    FOREIGN KEY (agent2_id) REFERENCES agents(id)
);

-- Knowledge artifacts - Shared knowledge between agents
CREATE TABLE IF NOT EXISTS knowledge_artifacts (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    content TEXT,
    artifact_type TEXT,
    creator_agent_id TEXT,
    creation_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata TEXT,
    FOREIGN KEY (creator_agent_id) REFERENCES agents(id)
);

-- Task queue for multi-agent coordination
CREATE TABLE IF NOT EXISTS task_queue (
    id TEXT PRIMARY KEY,
    requesting_agent_id TEXT,
    assigned_agent_id TEXT,
    task_description TEXT NOT NULL,
    priority INTEGER DEFAULT 1,
    status TEXT DEFAULT 'pending',
    created_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    start_time TIMESTAMP,
    completion_time TIMESTAMP,
    result TEXT,
    metadata TEXT,
    FOREIGN KEY (requesting_agent_id) REFERENCES agents(id),
    FOREIGN KEY (assigned_agent_id) REFERENCES agents(id)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_agents_type ON agents(type);
CREATE INDEX IF NOT EXISTS idx_agents_is_active ON agents(is_active);
CREATE INDEX IF NOT EXISTS idx_capabilities_name ON capabilities(name);
CREATE INDEX IF NOT EXISTS idx_agent_memory_key ON agent_memory(agent_id, key);
CREATE INDEX IF NOT EXISTS idx_execution_sessions_agent ON execution_sessions(agent_id);
CREATE INDEX IF NOT EXISTS idx_execution_steps_session ON execution_steps(session_id);
CREATE INDEX IF NOT EXISTS idx_task_queue_status ON task_queue(status);
CREATE INDEX IF NOT EXISTS idx_task_queue_assigned ON task_queue(assigned_agent_id, status); 