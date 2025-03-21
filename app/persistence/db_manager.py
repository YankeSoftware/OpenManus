"""
Database manager for OpenManus persistence layer.

Handles SQLite database connections, migrations, and provides a context manager
for database operations.
"""

import os
import sqlite3
import threading
from pathlib import Path
from typing import Optional, Union

from app.config import Config
from app.logger import logger


class DatabaseManager:
    """
    Database manager for SQLite operations.
    
    Provides connection management, schema initialization, and transaction support.
    Uses thread-local storage to ensure thread safety.
    """
    
    _instance = None
    _local = threading.local()
    
    def __new__(cls):
        """Singleton pattern implementation."""
        if cls._instance is None:
            cls._instance = super(DatabaseManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize the database manager if not already initialized."""
        if self._initialized:
            return
            
        self.config = Config()
        self.db_path = self.config.get("agent_persistence.database_path", "data/agent_store.db")
        self._ensure_db_directory()
        self._initialize_schema()
        self._initialized = True
        
    def _ensure_db_directory(self):
        """Ensure the database directory exists."""
        db_dir = os.path.dirname(self.db_path)
        Path(db_dir).mkdir(parents=True, exist_ok=True)
        
    def _get_schema_path(self) -> str:
        """Get the path to the schema SQL file."""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(current_dir, "schema.sql")
        
    def _initialize_schema(self):
        """Initialize the database schema if needed."""
        try:
            with self.get_connection() as conn:
                with open(self._get_schema_path(), 'r') as f:
                    schema_sql = f.read()
                    conn.executescript(schema_sql)
                    logger.info(f"Initialized database schema at {self.db_path}")
        except Exception as e:
            logger.error(f"Error initializing database schema: {str(e)}")
            raise
            
    def get_connection(self) -> sqlite3.Connection:
        """
        Get a database connection from thread-local storage or create a new one.
        
        Returns:
            sqlite3.Connection: SQLite connection object
        """
        if not hasattr(self._local, 'connection') or self._local.connection is None:
            self._local.connection = sqlite3.connect(
                self.db_path, 
                detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES
            )
            self._local.connection.row_factory = sqlite3.Row
            
        return self._local.connection
        
    def close_connection(self):
        """Close the current thread's database connection if it exists."""
        if hasattr(self._local, 'connection') and self._local.connection is not None:
            self._local.connection.close()
            self._local.connection = None
            
    def execute(self, query: str, params=None) -> sqlite3.Cursor:
        """
        Execute a SQL query with optional parameters.
        
        Args:
            query: SQL query string
            params: Query parameters
            
        Returns:
            sqlite3.Cursor: Query cursor
        """
        conn = self.get_connection()
        return conn.execute(query, params or ())
        
    def executemany(self, query: str, params_list) -> sqlite3.Cursor:
        """
        Execute a SQL query multiple times with different parameter sets.
        
        Args:
            query: SQL query string
            params_list: List of parameter tuples
            
        Returns:
            sqlite3.Cursor: Query cursor
        """
        conn = self.get_connection()
        return conn.executemany(query, params_list)
        
    def fetchone(self, query: str, params=None) -> Optional[sqlite3.Row]:
        """
        Execute a query and fetch one result.
        
        Args:
            query: SQL query string
            params: Query parameters
            
        Returns:
            Optional[sqlite3.Row]: Single row result or None
        """
        cursor = self.execute(query, params)
        return cursor.fetchone()
        
    def fetchall(self, query: str, params=None) -> list:
        """
        Execute a query and fetch all results.
        
        Args:
            query: SQL query string
            params: Query parameters
            
        Returns:
            list: List of row results
        """
        cursor = self.execute(query, params)
        return cursor.fetchall()
        
    def transaction(self):
        """
        Get a transaction context manager.
        
        Returns:
            Transaction: Transaction context manager
        """
        return Transaction(self)
        
        
class Transaction:
    """
    Transaction context manager for database operations.
    
    Provides an atomic transaction that can be committed or rolled back.
    """
    
    def __init__(self, db_manager: DatabaseManager):
        """
        Initialize the transaction.
        
        Args:
            db_manager: Database manager instance
        """
        self.db_manager = db_manager
        self.connection = None
        
    def __enter__(self):
        """Begin the transaction by getting a connection."""
        self.connection = self.db_manager.get_connection()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        End the transaction by committing or rolling back.
        
        Args:
            exc_type: Exception type if an exception occurred
            exc_val: Exception value if an exception occurred
            exc_tb: Exception traceback if an exception occurred
        """
        if exc_type is None:
            # No exception, commit the transaction
            self.connection.commit()
        else:
            # Exception occurred, rollback
            self.connection.rollback()
            logger.error(f"Transaction rolled back due to error: {str(exc_val)}")
            
    def commit(self):
        """Manually commit the transaction."""
        self.connection.commit()
        
    def rollback(self):
        """Manually rollback the transaction."""
        self.connection.rollback() 