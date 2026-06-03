import sys
import os

# Add backend directory to sys.path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend"))

# Import everything from the consolidated db module
from db import (
    get_db,
    save_scan,
    get_recent_scans,
    get_scan_by_id,
    get_nhi_index,
    get_drift_summary,
    get_scan_history_chart,
    seed_demo_data,
    get_repo_metrics
)