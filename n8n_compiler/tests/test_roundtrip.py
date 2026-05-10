"""Round-trip tests for unpack and pack operations."""

import json
from pathlib import Path
import tempfile
import shutil

import pytest

from n8n_compiler.core.models import Workflow, Manifest
from n8n_compiler.operations.unpack import unpack_workflow
from n8n_compiler.operations.pack import pack_workflow, validate_directory


# Get the test fixtures directory (project root)
FIXTURES_DIR = Path(__file__).parent.parent.parent


def normalize_workflow(data: dict) -> dict:
    """Normalize workflow for comparison (sort nodes, etc.)."""
    normalized = data.copy()
    
    # Sort nodes by ID for consistent comparison
    if "nodes" in normalized:
        normalized["nodes"] = sorted(normalized["nodes"], key=lambda n: n.get("id", ""))
    
    return normalized


class TestRoundTrip:
    """Test that unpack -> pack produces equivalent JSON."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for tests."""
        temp = tempfile.mkdtemp()
        yield Path(temp)
        shutil.rmtree(temp)
    
    @pytest.fixture
    def sample_workflow_path(self):
        """Get path to sample workflow."""
        path = FIXTURES_DIR / "lifeos_ai_agent_v2.json"
        if not path.exists():
            pytest.skip(f"Sample workflow not found: {path}")
        return path
    
    def test_unpack_creates_directory(self, sample_workflow_path, temp_dir):
        """Test that unpack creates the expected directory structure."""
        output_dir = temp_dir / "test_workflow"
        
        result = unpack_workflow(sample_workflow_path, output_dir)
        
        assert result.exists()
        assert (result / "manifest.json").exists()
        assert (result / "nodes").exists()
        assert (result / "graph.mmd").exists()
    
    def test_unpack_creates_node_categories(self, sample_workflow_path, temp_dir):
        """Test that nodes are categorized correctly."""
        output_dir = temp_dir / "test_workflow"
        
        unpack_workflow(sample_workflow_path, output_dir)
        
        nodes_dir = output_dir / "nodes"
        assert (nodes_dir / "triggers").exists()
        assert (nodes_dir / "processors").exists()
        assert (nodes_dir / "integrations").exists()
        assert (nodes_dir / "ai").exists()
        assert (nodes_dir / "routing").exists()
    
    def test_pack_restores_workflow(self, sample_workflow_path, temp_dir):
        """Test that pack restores the original workflow."""
        output_dir = temp_dir / "test_workflow"
        output_json = temp_dir / "restored.json"
        
        # Unpack
        unpack_workflow(sample_workflow_path, output_dir)
        
        # Pack
        pack_workflow(output_dir, output_json)
        
        # Compare
        with open(sample_workflow_path) as f:
            original = json.load(f)
        with open(output_json) as f:
            restored = json.load(f)
        
        original_normalized = normalize_workflow(original)
        restored_normalized = normalize_workflow(restored)
        
        # Compare node count
        assert len(original_normalized["nodes"]) == len(restored_normalized["nodes"])
        
        # Compare node IDs
        original_ids = {n["id"] for n in original_normalized["nodes"]}
        restored_ids = {n["id"] for n in restored_normalized["nodes"]}
        assert original_ids == restored_ids
    
    def test_validate_directory(self, sample_workflow_path, temp_dir):
        """Test directory validation."""
        output_dir = temp_dir / "test_workflow"
        
        unpack_workflow(sample_workflow_path, output_dir)
        
        errors = validate_directory(output_dir)
        assert len(errors) == 0
    
    def test_manifest_contains_all_nodes(self, sample_workflow_path, temp_dir):
        """Test that manifest contains all nodes."""
        output_dir = temp_dir / "test_workflow"
        
        unpack_workflow(sample_workflow_path, output_dir)
        
        # Load original
        workflow = Workflow.load(sample_workflow_path)
        
        # Load manifest
        manifest = Manifest.load(output_dir / "manifest.json")
        
        assert len(manifest.nodes) == len(workflow.nodes)
        
        original_ids = {n.id for n in workflow.nodes}
        manifest_ids = set(manifest.nodes.keys())
        assert original_ids == manifest_ids


class TestNodeCategorization:
    """Test node categorization logic."""
    
    def test_trigger_categorization(self):
        """Test that trigger nodes are categorized correctly."""
        from n8n_compiler.core.models import Node, NodeCategory
        
        node = Node(
            id="test",
            name="Test Trigger",
            type="n8n-nodes-base.telegramTrigger",
            typeVersion=1,
            position=[0, 0],
        )
        
        assert node.get_category() == NodeCategory.TRIGGERS
    
    def test_ai_categorization(self):
        """Test that AI nodes are categorized correctly."""
        from n8n_compiler.core.models import Node, NodeCategory
        
        node = Node(
            id="test",
            name="Test LLM",
            type="@n8n/n8n-nodes-langchain.lmChatGoogleGemini",
            typeVersion=1,
            position=[0, 0],
        )
        
        assert node.get_category() == NodeCategory.AI
    
    def test_routing_categorization(self):
        """Test that routing nodes are categorized correctly."""
        from n8n_compiler.core.models import Node, NodeCategory
        
        node = Node(
            id="test",
            name="Test Switch",
            type="n8n-nodes-base.switch",
            typeVersion=1,
            position=[0, 0],
        )
        
        assert node.get_category() == NodeCategory.ROUTING
    
    def test_processor_default(self):
        """Test that unknown nodes default to processors."""
        from n8n_compiler.core.models import Node, NodeCategory
        
        node = Node(
            id="test",
            name="Test Code",
            type="n8n-nodes-base.code",
            typeVersion=1,
            position=[0, 0],
        )
        
        assert node.get_category() == NodeCategory.PROCESSORS
