"""Smart sync operation - bidirectional synchronization."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from n8n_compiler.core.models import (
    Manifest,
    compute_dir_hash,
    compute_file_hash,
)
from n8n_compiler.operations.unpack import unpack_workflow
from n8n_compiler.operations.pack import pack_workflow


class SyncDirection(str, Enum):
    """Direction of synchronization."""
    NONE = "none"           # Already in sync
    JSON_TO_DIR = "unpack"  # JSON is newer, unpack to directory
    DIR_TO_JSON = "pack"    # Directory is newer, pack to JSON
    CONFLICT = "conflict"   # Both changed, needs resolution


@dataclass
class SyncResult:
    """Result of a sync operation."""
    direction: SyncDirection
    source_path: Path
    target_path: Path
    nodes_affected: int = 0
    message: str = ""
    error: Optional[str] = None


def detect_sync_direction(workflow_path: Path) -> tuple[SyncDirection, dict]:
    """
    Detect which direction to sync based on timestamps and hashes.
    
    Args:
        workflow_path: Path to either the JSON file or the directory
        
    Returns:
        Tuple of (direction, info dict)
    """
    workflow_path = Path(workflow_path).resolve()
    
    # Determine if input is JSON or directory
    if workflow_path.is_file() and workflow_path.suffix == ".json":
        json_path = workflow_path
        dir_path = workflow_path.parent / workflow_path.stem
    elif workflow_path.is_dir():
        dir_path = workflow_path
        manifest_path = dir_path / "manifest.json"
        if manifest_path.exists():
            manifest = Manifest.load(manifest_path)
            source_file = manifest.meta.source_file
            if source_file.startswith("../"):
                json_path = dir_path.parent / source_file[3:]
            else:
                json_path = dir_path / "workflow.json"
        else:
            # No manifest, can't determine JSON path
            return SyncDirection.NONE, {"error": "No manifest found"}
    else:
        return SyncDirection.NONE, {"error": f"Invalid path: {workflow_path}"}
    
    info = {
        "json_path": json_path,
        "dir_path": dir_path,
    }
    
    # Check if both exist
    json_exists = json_path.exists()
    dir_exists = dir_path.exists() and (dir_path / "manifest.json").exists()
    
    if not json_exists and not dir_exists:
        return SyncDirection.NONE, {**info, "error": "Neither JSON nor directory exists"}
    
    if json_exists and not dir_exists:
        return SyncDirection.JSON_TO_DIR, {**info, "reason": "Directory does not exist"}
    
    if dir_exists and not json_exists:
        return SyncDirection.DIR_TO_JSON, {**info, "reason": "JSON does not exist"}
    
    # Both exist - compare hashes and timestamps
    manifest = Manifest.load(dir_path / "manifest.json")
    
    current_json_hash = compute_file_hash(json_path)
    current_dir_hash = compute_dir_hash(dir_path / "nodes", "**/*.json")
    
    stored_json_hash = manifest.sync.json_hash
    stored_dir_hash = manifest.sync.dir_hash
    
    json_changed = current_json_hash != stored_json_hash
    dir_changed = current_dir_hash != stored_dir_hash
    
    info["json_changed"] = json_changed
    info["dir_changed"] = dir_changed
    info["current_json_hash"] = current_json_hash
    info["current_dir_hash"] = current_dir_hash
    info["stored_json_hash"] = stored_json_hash
    info["stored_dir_hash"] = stored_dir_hash
    
    if not json_changed and not dir_changed:
        return SyncDirection.NONE, {**info, "reason": "Already in sync"}
    
    if json_changed and not dir_changed:
        return SyncDirection.JSON_TO_DIR, {**info, "reason": "JSON changed"}
    
    if dir_changed and not json_changed:
        return SyncDirection.DIR_TO_JSON, {**info, "reason": "Directory changed"}
    
    # Both changed - conflict
    # Use timestamps as tiebreaker hint
    json_mtime = datetime.fromtimestamp(json_path.stat().st_mtime)
    
    # Get latest node file mtime
    latest_node_mtime = None
    for node_file in (dir_path / "nodes").rglob("*.json"):
        file_mtime = datetime.fromtimestamp(node_file.stat().st_mtime)
        if latest_node_mtime is None or file_mtime > latest_node_mtime:
            latest_node_mtime = file_mtime
    
    info["json_mtime"] = json_mtime.isoformat()
    info["dir_mtime"] = latest_node_mtime.isoformat() if latest_node_mtime else None
    
    return SyncDirection.CONFLICT, {
        **info,
        "reason": "Both JSON and directory changed",
        "suggestion": "json" if json_mtime > (latest_node_mtime or datetime.min) else "dir"
    }


def sync_workflow(
    workflow_path: Path,
    force_direction: Optional[SyncDirection] = None,
) -> SyncResult:
    """
    Perform smart sync between JSON and directory.
    
    Args:
        workflow_path: Path to either JSON file or directory
        force_direction: Optional forced direction (for conflict resolution)
        
    Returns:
        SyncResult with details of what was done
    """
    workflow_path = Path(workflow_path).resolve()
    
    direction, info = detect_sync_direction(workflow_path)
    
    if "error" in info:
        return SyncResult(
            direction=SyncDirection.NONE,
            source_path=workflow_path,
            target_path=workflow_path,
            error=info["error"],
        )
    
    # Handle forced direction
    if force_direction:
        if force_direction == SyncDirection.JSON_TO_DIR:
            direction = SyncDirection.JSON_TO_DIR
        elif force_direction == SyncDirection.DIR_TO_JSON:
            direction = SyncDirection.DIR_TO_JSON
    
    json_path = info["json_path"]
    dir_path = info["dir_path"]
    
    if direction == SyncDirection.NONE:
        return SyncResult(
            direction=direction,
            source_path=json_path,
            target_path=dir_path,
            message=info.get("reason", "Already in sync"),
        )
    
    if direction == SyncDirection.CONFLICT:
        return SyncResult(
            direction=direction,
            source_path=json_path,
            target_path=dir_path,
            message=f"Conflict detected. {info.get('reason', '')}",
            error=f"Use --force-json or --force-dir to resolve. Suggestion: --force-{info.get('suggestion', 'json')}",
        )
    
    if direction == SyncDirection.JSON_TO_DIR:
        # Unpack JSON to directory
        unpack_workflow(json_path, dir_path, force=True)
        
        # Count nodes
        manifest = Manifest.load(dir_path / "manifest.json")
        node_count = len(manifest.nodes)
        
        return SyncResult(
            direction=direction,
            source_path=json_path,
            target_path=dir_path,
            nodes_affected=node_count,
            message=f"Unpacked {node_count} nodes from JSON to directory",
        )
    
    if direction == SyncDirection.DIR_TO_JSON:
        # Pack directory to JSON
        pack_workflow(dir_path, json_path, force=True)
        
        # Count nodes
        manifest = Manifest.load(dir_path / "manifest.json")
        node_count = len(manifest.nodes)
        
        return SyncResult(
            direction=direction,
            source_path=dir_path,
            target_path=json_path,
            nodes_affected=node_count,
            message=f"Packed {node_count} nodes from directory to JSON",
        )
    
    return SyncResult(
        direction=SyncDirection.NONE,
        source_path=workflow_path,
        target_path=workflow_path,
        error="Unknown sync state",
    )
