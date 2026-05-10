"""Pack operation - converts directory structure back to workflow JSON."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from n8n_compiler.core.models import (
    Manifest,
    Node,
    Workflow,
    compute_file_hash,
    compute_hash,
)


def pack_workflow(
    source_dir: Path,
    output_json: Optional[Path] = None,
    force: bool = False,
) -> Path:
    """
    Pack a directory structure back into a workflow JSON file.
    
    Args:
        source_dir: Path to the unpacked workflow directory
        output_json: Optional output JSON path (defaults to workflow.json in dir)
        force: If True, overwrite existing JSON
        
    Returns:
        Path to the created JSON file
    """
    source_dir = Path(source_dir).resolve()
    
    if not source_dir.exists():
        raise FileNotFoundError(f"Source directory not found: {source_dir}")
    
    manifest_path = source_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")
    
    # Load manifest
    manifest = Manifest.load(manifest_path)
    
    # Determine output path
    if output_json is None:
        # Use the source_file from manifest if it exists, else workflow.json
        source_file = manifest.meta.source_file
        if source_file.startswith("../"):
            output_json = source_dir.parent / source_file[3:]
        else:
            output_json = source_dir / "workflow.json"
    else:
        output_json = Path(output_json).resolve()
    
    # Load all nodes from clipboard-compatible format
    nodes: list[Node] = []
    node_id_to_name: dict[str, str] = {}
    all_connections: dict[str, dict[str, list[list[dict]]]] = {}
    all_pin_data: dict[str, list[dict]] = {}
    
    for node_id, entry in manifest.nodes.items():
        node_path = source_dir / entry.file
        
        if not node_path.exists():
            raise FileNotFoundError(f"Node file not found: {node_path}")
        
        with open(node_path, "r", encoding="utf-8") as f:
            file_data = json.load(f)
        
        # Handle both clipboard format and legacy raw format
        if "nodes" in file_data and isinstance(file_data["nodes"], list):
            # Clipboard format - extract node from nodes array
            node_data = file_data["nodes"][0]
            
            # Merge connections from this node file
            if "connections" in file_data:
                all_connections.update(file_data["connections"])
            
            # Merge pinData from this node file
            if "pinData" in file_data:
                all_pin_data.update(file_data["pinData"])
        else:
            # Legacy raw format - use as-is
            node_data = file_data
        
        node = Node.model_validate(node_data)
        nodes.append(node)
        node_id_to_name[node_id] = node.name
    
    # Sort nodes by execution order
    nodes.sort(key=lambda n: manifest.nodes[n.id].execution_order)
    
    # Use connections from node files (already name-based)
    connections = all_connections
    
    # Merge pinData: use node files first, then fall back to manifest settings
    pin_data = all_pin_data if all_pin_data else manifest.workflow_settings.pinData
    
    # Create workflow
    workflow = Workflow(
        nodes=nodes,
        connections=connections,
        name=manifest.workflow_settings.name,
        settings=manifest.workflow_settings.settings,
        staticData=manifest.workflow_settings.staticData,
        pinData=pin_data,
    )
    
    # Save workflow
    workflow.save(output_json)
    
    # Update manifest with new hashes
    now = datetime.now().astimezone().isoformat()
    manifest.sync.json_hash = compute_file_hash(output_json)
    manifest.sync.json_mtime = now
    manifest.meta.last_synced = now
    
    # Update node hashes
    for node_id, entry in manifest.nodes.items():
        node_path = source_dir / entry.file
        if node_path.exists():
            with open(node_path, "r", encoding="utf-8") as f:
                node_data = json.load(f)
            entry.hash = compute_hash(json.dumps(node_data, sort_keys=True))
    
    # Update directory hash
    manifest.sync.dir_hash = compute_hash(
        json.dumps(
            {node_id: entry.hash for node_id, entry in manifest.nodes.items()},
            sort_keys=True
        )
    )
    manifest.sync.dir_mtime = now
    
    manifest.save(manifest_path)
    
    return output_json


def pack_auto(
    source_dir: Path,
    output_json: Optional[Path] = None,
) -> Path:
    """
    Pack workflow from node files alone (no manifest required).
    
    Uses filename order prefixes (001_, 002_) to determine execution order.
    Merges connections and pinData from individual node files.
    
    Args:
        source_dir: Path to the unpacked workflow directory
        output_json: Optional output JSON path
        
    Returns:
        Path to the created JSON file
    """
    source_dir = Path(source_dir).resolve()
    nodes_dir = source_dir / "nodes"
    
    if not nodes_dir.exists():
        raise FileNotFoundError(f"Nodes directory not found: {nodes_dir}")
    
    # Determine output path
    if output_json is None:
        output_json = source_dir.parent / f"{source_dir.name}.json"
    else:
        output_json = Path(output_json).resolve()
    
    # Discover all node files
    node_files = sorted(nodes_dir.glob("**/*.json"))
    
    # Filter out README.md files
    node_files = [f for f in node_files if f.name != "README.md"]
    
    if not node_files:
        raise FileNotFoundError(f"No node files found in {nodes_dir}")
    
    nodes: list[Node] = []
    all_connections: dict[str, dict[str, list[list[dict]]]] = {}
    all_pin_data: dict[str, list[dict]] = {}
    
    for node_file in node_files:
        with open(node_file, "r", encoding="utf-8") as f:
            file_data = json.load(f)
        
        # Handle clipboard format
        if "nodes" in file_data and isinstance(file_data["nodes"], list):
            node_data = file_data["nodes"][0]
            all_connections.update(file_data.get("connections", {}))
            all_pin_data.update(file_data.get("pinData", {}))
        else:
            node_data = file_data
        
        node = Node.model_validate(node_data)
        # Store source filename for sorting
        node._source_order = _extract_order_prefix(node_file.name)
        nodes.append(node)
    
    # Sort by filename order prefix
    nodes.sort(key=lambda n: getattr(n, '_source_order', 999))
    
    # Try to load workflow name from manifest if exists
    workflow_name = source_dir.name
    workflow_settings = {}
    static_data = None
    
    manifest_path = source_dir / "manifest.json"
    if manifest_path.exists():
        try:
            manifest = Manifest.load(manifest_path)
            workflow_name = manifest.workflow_settings.name or workflow_name
            workflow_settings = manifest.workflow_settings.settings
            static_data = manifest.workflow_settings.staticData
        except Exception:
            pass  # Use defaults
    
    # Create workflow
    workflow = Workflow(
        nodes=nodes,
        connections=all_connections,
        name=workflow_name,
        settings=workflow_settings,
        staticData=static_data,
        pinData=all_pin_data,
    )
    
    workflow.save(output_json)
    
    return output_json


def _extract_order_prefix(filename: str) -> int:
    """Extract numeric order prefix from filename like '001_node.json'."""
    import re
    match = re.match(r'^(\d+)_', filename)
    if match:
        return int(match.group(1))
    return 999  # No prefix = end of list


def validate_directory(source_dir: Path) -> list[str]:
    """
    Validate a directory structure for packing.
    
    Returns:
        List of error messages (empty if valid)
    """
    errors = []
    source_dir = Path(source_dir).resolve()
    
    manifest_path = source_dir / "manifest.json"
    if not manifest_path.exists():
        errors.append(f"Missing manifest.json in {source_dir}")
        return errors
    
    try:
        manifest = Manifest.load(manifest_path)
    except Exception as e:
        errors.append(f"Invalid manifest.json: {e}")
        return errors
    
    # Check all node files exist
    for node_id, entry in manifest.nodes.items():
        node_path = source_dir / entry.file
        if not node_path.exists():
            errors.append(f"Missing node file: {entry.file}")
            continue
        
        # Validate JSON
        try:
            with open(node_path, "r", encoding="utf-8") as f:
                file_data = json.load(f)
            
            # Handle clipboard format vs legacy raw format
            if "nodes" in file_data and isinstance(file_data["nodes"], list):
                # Clipboard format - extract node from nodes array
                if len(file_data["nodes"]) == 0:
                    errors.append(f"Empty nodes array in {entry.file}")
                    continue
                node_data = file_data["nodes"][0]
            else:
                # Legacy raw format
                node_data = file_data
            
            # Check required fields
            if "id" not in node_data:
                errors.append(f"Missing 'id' in {entry.file}")
            elif node_data["id"] != node_id:
                errors.append(f"Node ID mismatch in {entry.file}: expected {node_id}, got {node_data['id']}")
            
            if "name" not in node_data:
                errors.append(f"Missing 'name' in {entry.file}")
            if "type" not in node_data:
                errors.append(f"Missing 'type' in {entry.file}")
                
        except json.JSONDecodeError as e:
            errors.append(f"Invalid JSON in {entry.file}: {e}")
    
    # Check connection targets exist
    all_node_ids = set(manifest.nodes.keys())
    for source_id, outputs in manifest.connections.items():
        if source_id not in all_node_ids:
            errors.append(f"Connection source not found: {source_id}")
        
        for output_type, branches in outputs.items():
            for branch in branches:
                for target in branch:
                    target_id = target.get("node_id")
                    if target_id and target_id not in all_node_ids:
                        errors.append(f"Connection target not found: {target_id}")
    
    return errors
