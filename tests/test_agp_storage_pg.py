from ahy_governance.storage_pg import PostgresDatabase


def test_postgres_registered_agents_has_agp_columns():
    db = object.__new__(PostgresDatabase)
    from sqlalchemy import MetaData
    db._metadata = MetaData()
    db._define_tables()

    columns = db._metadata.tables["registered_agents"].columns

    for name in (
        "framework",
        "version",
        "description",
        "capabilities",
        "registry_config",
        "governance_config",
        "config_path",
        "status",
        "last_heartbeat",
        "pid",
    ):
        assert name in columns


def test_postgres_backend_exposes_agp_registration_methods():
    for method in (
        "agent_register_full",
        "agent_list_by_status",
        "agent_update_status",
        "agent_heartbeat",
        "agent_list_stale",
    ):
        assert hasattr(PostgresDatabase, method)
