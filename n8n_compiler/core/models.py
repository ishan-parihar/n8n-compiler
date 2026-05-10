"""Core data models for n8n workflow compiler."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field


class NodeCategory(str, Enum):
    """Categories for organizing nodes in directory structure."""
    TRIGGERS = "triggers"
    PROCESSORS = "processors"
    INTEGRATIONS = "integrations"
    AI = "ai"
    ROUTING = "routing"


# Node type patterns for auto-categorization
NODE_CATEGORY_PATTERNS = {
    NodeCategory.TRIGGERS: [
        "Trigger", "webhook", "schedule", "cron", "emailRead", "imap"
    ],
    NodeCategory.AI: [
        "agent", "lmChat", "langchain", "openAi", "anthropic", "googleGemini",
        "lmChatGoogleGemini", "lmChatOpenAi", "lmChatAnthropic"
    ],
    NodeCategory.ROUTING: [
        "if", "switch", "merge", "splitInBatches", "noOp", "filter",
        "removeDuplicates", "limit", "wait"
    ],
    NodeCategory.INTEGRATIONS: [
        "notion", "telegram", "slack", "discord", "gmail", "googleSheets",
        "airtable", "postgres", "mysql", "mongodb", "redis", "http",
        "httpRequest", "webhook", "ftp", "s3", "gcs"
    ],
    # PROCESSORS is the default category
}


class ConnectionTarget(BaseModel):
    """A single connection target."""
    node_id: str = Field(..., alias="node")
    type: str = "main"
    index: int = 0
    
    model_config = {"populate_by_name": True}


class Node(BaseModel):
    """Represents a single n8n node."""
    id: str
    name: str
    type: str
    typeVersion: float | int
    position: list[int]
    parameters: dict[str, Any] = Field(default_factory=dict)
    credentials: Optional[dict[str, Any]] = None
    webhookId: Optional[str] = None
    notes: Optional[str] = None
    disabled: bool = False
    notesInFlow: bool = False
    onError: Optional[str] = None
    alwaysOutputData: Optional[bool] = None
    executeOnce: Optional[bool] = None
    retryOnFail: Optional[bool] = None
    maxTries: Optional[int] = None
    waitBetweenTries: Optional[int] = None
    
    def get_category(self) -> NodeCategory:
        """Determine the category for this node using dynamic heuristics."""
        type_lower = self.type.lower()
        name_lower = self.name.lower()
        
        # 1. Explicit trigger detection
        if "trigger" in type_lower or self.webhookId:
            return NodeCategory.TRIGGERS
        
        # 2. AI/LLM nodes (check type for langchain patterns)
        ai_patterns = ["agent", "lmchat", "langchain", "openai", "anthropic", "gemini", "llm", "chat"]
        if any(p in type_lower for p in ai_patterns):
            return NodeCategory.AI
        
        # 3. Routing/control flow nodes
        routing_patterns = ["if", "switch", "merge", "split", "filter", "wait", "noop", "limit"]
        if any(p in type_lower for p in routing_patterns):
            return NodeCategory.ROUTING
        
        # 4. Integration detection (has credentials = likely external service)
        if self.credentials:
            return NodeCategory.INTEGRATIONS
        
        # 5. Known integration patterns (for nodes without credentials in def)
        integration_patterns = [
            "notion", "telegram", "slack", "discord", "gmail", "sheets",
            "airtable", "postgres", "mysql", "mongodb", "redis", "http",
            "webhook", "ftp", "s3", "supabase", "stripe", "twilio",
        ]
        if any(p in type_lower for p in integration_patterns):
            return NodeCategory.INTEGRATIONS
        
        # 6. Default to processors (code, set, function, etc.)
        return NodeCategory.PROCESSORS
    
    def get_safe_filename(self) -> str:
        """Generate a safe filename from node name."""
        # Replace spaces and special chars with underscores
        safe_name = self.name.lower()
        for char in [" ", "-", ".", "/", "\\", ":", "*", "?", '"', "<", ">", "|"]:
            safe_name = safe_name.replace(char, "_")
        # Remove consecutive underscores
        while "__" in safe_name:
            safe_name = safe_name.replace("__", "_")
        return safe_name.strip("_") + ".json"
    
    def to_file_dict(self) -> dict[str, Any]:
        """Convert to dictionary for saving to file (excludes None values)."""
        data = {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "typeVersion": self.typeVersion,
            "position": self.position,
            "parameters": self.parameters,
        }
        
        # Only include optional fields if they have values
        if self.credentials:
            data["credentials"] = self.credentials
        if self.webhookId:
            data["webhookId"] = self.webhookId
        if self.notes:
            data["notes"] = self.notes
        if self.disabled:
            data["disabled"] = self.disabled
        if self.notesInFlow:
            data["notesInFlow"] = self.notesInFlow
        if self.onError:
            data["onError"] = self.onError
        if self.alwaysOutputData is not None:
            data["alwaysOutputData"] = self.alwaysOutputData
        if self.executeOnce is not None:
            data["executeOnce"] = self.executeOnce
        if self.retryOnFail is not None:
            data["retryOnFail"] = self.retryOnFail
        if self.maxTries is not None:
            data["maxTries"] = self.maxTries
        if self.waitBetweenTries is not None:
            data["waitBetweenTries"] = self.waitBetweenTries
            
        return data


class NodeManifestEntry(BaseModel):
    """Manifest entry for a single node."""
    name: str
    file: str
    type: str
    category: NodeCategory
    hash: str
    execution_order: int


class SyncInfo(BaseModel):
    """Sync state information."""
    mode: str = "auto"
    direction: Optional[str] = None
    json_hash: Optional[str] = None
    json_mtime: Optional[str] = None
    dir_hash: Optional[str] = None
    dir_mtime: Optional[str] = None


class WorkflowMeta(BaseModel):
    """Workflow metadata."""
    name: str
    description: str = ""
    source_file: str
    created_at: str
    last_synced: str


class WorkflowSettings(BaseModel):
    """Original n8n workflow settings."""
    name: Optional[str] = None
    settings: dict[str, Any] = Field(default_factory=dict)
    staticData: Optional[Any] = None
    pinData: dict[str, Any] = Field(default_factory=dict)


class Manifest(BaseModel):
    """Complete manifest for a unpacked workflow."""
    version: str = "2.0.0"
    meta: WorkflowMeta
    sync: SyncInfo = Field(default_factory=SyncInfo)
    nodes: dict[str, NodeManifestEntry] = Field(default_factory=dict)
    connections: dict[str, dict[str, list[list[dict[str, Any]]]]] = Field(default_factory=dict)
    workflow_settings: WorkflowSettings = Field(default_factory=WorkflowSettings)
    
    def save(self, path: Path) -> None:
        """Save manifest to file."""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.model_dump(mode="json"), f, indent=2, ensure_ascii=False)
    
    @classmethod
    def load(cls, path: Path) -> "Manifest":
        """Load manifest from file."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.model_validate(data)


class Workflow(BaseModel):
    """Complete n8n workflow."""
    nodes: list[Node] = Field(default_factory=list)
    connections: dict[str, dict[str, list[list[dict[str, Any]]]]] = Field(default_factory=dict)
    name: Optional[str] = None
    settings: dict[str, Any] = Field(default_factory=dict)
    staticData: Optional[Any] = None
    pinData: dict[str, Any] = Field(default_factory=dict)
    
    @classmethod
    def load(cls, path: Path) -> "Workflow":
        """Load workflow from JSON file."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.model_validate(data)
    
    def save(self, path: Path) -> None:
        """Save workflow to JSON file."""
        data = {
            "nodes": [node.to_file_dict() for node in self.nodes],
            "connections": self.connections,
        }
        if self.name:
            data["name"] = self.name
        if self.settings:
            data["settings"] = self.settings
        if self.staticData is not None:
            data["staticData"] = self.staticData
        if self.pinData:
            data["pinData"] = self.pinData
            
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    
    def get_node_by_id(self, node_id: str) -> Optional[Node]:
        """Get a node by its ID."""
        for node in self.nodes:
            if node.id == node_id:
                return node
        return None
    
    def get_node_by_name(self, name: str) -> Optional[Node]:
        """Get a node by its name."""
        for node in self.nodes:
            if node.name == name:
                return node
        return None
    
    def topological_sort(self) -> list[Node]:
        """Sort nodes by execution order (topological sort)."""
        # Build adjacency list from connections
        # Connections are: source_node_name -> { output_type -> [[targets]] }
        adjacency: dict[str, set[str]] = {node.name: set() for node in self.nodes}
        in_degree: dict[str, int] = {node.name: 0 for node in self.nodes}
        
        for source_name, outputs in self.connections.items():
            for output_type, output_branches in outputs.items():
                for branch in output_branches:
                    for target in branch:
                        target_name = target.get("node")
                        if target_name and target_name in adjacency:
                            adjacency[source_name].add(target_name)
                            in_degree[target_name] += 1
        
        # Kahn's algorithm
        queue = [name for name, degree in in_degree.items() if degree == 0]
        result = []
        
        while queue:
            # Sort queue to ensure deterministic order
            queue.sort()
            current = queue.pop(0)
            result.append(current)
            
            for neighbor in sorted(adjacency[current]):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
        
        # Map names back to nodes
        name_to_node = {node.name: node for node in self.nodes}
        sorted_nodes = [name_to_node[name] for name in result if name in name_to_node]
        
        # Add any nodes not in the result (disconnected nodes)
        sorted_ids = {node.id for node in sorted_nodes}
        for node in self.nodes:
            if node.id not in sorted_ids:
                sorted_nodes.append(node)
        
        return sorted_nodes


class WorkspaceConfig(BaseModel):
    """Workspace configuration (.n8nc/config.json)."""
    version: str = "1.0.0"
    workflows: list[dict[str, str]] = Field(default_factory=list)
    settings: dict[str, Any] = Field(default_factory=lambda: {
        "auto_categorize": True,
        "generate_graph": True,
        "preserve_positions": True,
        "debounce_ms": 300
    })
    
    def save(self, path: Path) -> None:
        """Save config to file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.model_dump(), f, indent=2)
    
    @classmethod
    def load(cls, path: Path) -> "WorkspaceConfig":
        """Load config from file."""
        if not path.exists():
            return cls()
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.model_validate(data)


def compute_hash(content: str | bytes) -> str:
    """Compute SHA-256 hash of content."""
    if isinstance(content, str):
        content = content.encode("utf-8")
    return f"sha256:{hashlib.sha256(content).hexdigest()[:16]}"


def compute_file_hash(path: Path) -> str:
    """Compute hash of a file."""
    with open(path, "rb") as f:
        return compute_hash(f.read())


def compute_dir_hash(dir_path: Path, pattern: str = "**/*.json") -> str:
    """Compute combined hash of all JSON files in a directory."""
    hashes = []
    for file_path in sorted(dir_path.glob(pattern)):
        if file_path.is_file():
            hashes.append(compute_file_hash(file_path))
    combined = "|".join(hashes)
    return compute_hash(combined)
