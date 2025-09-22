# Model Resolution Final Implementation Plan

## Overview
Implement model resolution with simplified metadata format (no substitutions) and smart resolution strategies for ambiguous cases.

## Core Principles
1. **No widget value modification** - Only update metadata
2. **Multi-strategy resolution** - Try exact → case-insensitive → filename-only
3. **User disambiguation** - Prompt when multiple matches found
4. **Leverage existing code** - Build on ModelIndexManager and WorkflowDependencyParser

## Architecture Changes

### 1. Enhanced Data Models

**File**: `packages/core/src/comfydock_core/models/workflow.py`

Add new model resolution classes:

```python
@dataclass
class ModelReference:
    """Single model reference with full context"""
    node_id: str
    node_type: str
    widget_index: int
    widget_value: str  # Original value from workflow
    resolved_model: ModelWithLocation | None = None
    resolution_confidence: float = 0.0  # 1.0 = exact, 0.5 = fuzzy

    @property
    def is_resolved(self) -> bool:
        return self.resolved_model is not None

@dataclass
class ModelResolutionResult:
    """Result of attempting to resolve a model reference"""
    reference: ModelReference
    candidates: list[ModelWithLocation]  # All possible matches
    resolution_type: str  # "exact", "case_insensitive", "filename", "ambiguous", "not_found"
```

### 2. Workflow Metadata Manager

**New File**: `packages/core/src/comfydock_core/managers/workflow_metadata_manager.py`

```python
class WorkflowMetadataManager:
    """Manages simplified metadata format"""

    METADATA_KEY = "_comfydock_metadata"
    CURRENT_VERSION = "0.1.0"

    def inject_metadata(self, workflow: dict, references: list[ModelReference]) -> dict:
        """Inject metadata into workflow['extra']['_comfydock_metadata']"""
        if "extra" not in workflow:
            workflow["extra"] = {}

        metadata = {
            "version": self.CURRENT_VERSION,
            "last_updated": datetime.now().isoformat() + "Z",
            "models": {}
        }

        # Group by node
        for ref in references:
            node_key = str(ref.node_id)
            if node_key not in metadata["models"]:
                metadata["models"][node_key] = {
                    "node_type": ref.node_type,
                    "refs": []
                }

            model_data = {
                "widget_index": ref.widget_index,
                "path": ref.widget_value,
                "hash": ref.resolved_model.hash if ref.resolved_model else None,
                "sha256": ref.resolved_model.sha256_hash if ref.resolved_model else None,
                "blake3": ref.resolved_model.blake3_hash if ref.resolved_model else None,
                "sources": self._get_sources(ref.resolved_model) if ref.resolved_model else []
            }

            metadata["models"][node_key]["refs"].append(model_data)

        workflow["extra"][self.METADATA_KEY] = metadata
        return workflow

    def extract_metadata(self, workflow: dict) -> dict | None:
        """Extract existing metadata if present"""
        return workflow.get("extra", {}).get(self.METADATA_KEY)

    def _get_sources(self, model: ModelWithLocation) -> list[str]:
        """Get source URLs for model if available"""
        # Check model_sources table via index manager
        sources = []
        if hasattr(model, 'metadata') and model.metadata:
            if 'civitai_id' in model.metadata:
                sources.append(f"civitai:{model.metadata['civitai_id']}")
            if 'huggingface_url' in model.metadata:
                sources.append(f"huggingface:{model.metadata['huggingface_url']}")
        return sources
```

### 3. Enhanced Model Resolution

**Update**: `packages/core/src/comfydock_core/utils/workflow_dependency_parser.py`

Add smart resolution with multiple strategies:

```python
class WorkflowDependencyParser:

    def analyze_models_enhanced(self) -> list[ModelResolutionResult]:
        """Analyze models with enhanced resolution strategies"""
        results = []
        nodes_data = self.workflow.nodes

        for node_id, node_info in nodes_data.items():
            refs = self._extract_model_refs(node_id, node_info)
            for ref in refs:
                result = self._resolve_with_strategies(ref)
                results.append(result)

        return results

    def _extract_model_refs(self, node_id: str, node_info: WorkflowNode) -> list[ModelReference]:
        """Extract model references from node"""
        refs = []

        # Handle multi-model nodes specially
        if node_info.type == "CheckpointLoader":
            # Index 0: checkpoint, Index 1: config
            widgets = node_info.widgets_values or []
            if len(widgets) > 0 and widgets[0]:
                refs.append(ModelReference(
                    node_id=node_id,
                    node_type=node_info.type,
                    widget_index=0,
                    widget_value=widgets[0]
                ))
            if len(widgets) > 1 and widgets[1]:
                refs.append(ModelReference(
                    node_id=node_id,
                    node_type=node_info.type,
                    widget_index=1,
                    widget_value=widgets[1]
                ))

        # Standard single-model loaders
        elif self.model_config.is_model_loader_node(node_info.type):
            widget_idx = self.model_config.get_widget_index_for_node(node_info.type)
            widgets = node_info.widgets_values or []
            if widget_idx < len(widgets) and widgets[widget_idx]:
                refs.append(ModelReference(
                    node_id=node_id,
                    node_type=node_info.type,
                    widget_index=widget_idx,
                    widget_value=widgets[widget_idx]
                ))

        # Pattern match all widgets for custom nodes
        else:
            widgets = node_info.widgets_values or []
            for idx, value in enumerate(widgets):
                if self._looks_like_model(value):
                    refs.append(ModelReference(
                        node_id=node_id,
                        node_type=node_info.type,
                        widget_index=idx,
                        widget_value=value
                    ))

        return refs

    def _resolve_with_strategies(self, ref: ModelReference) -> ModelResolutionResult:
        """Try multiple resolution strategies"""
        widget_value = ref.widget_value

        # Strategy 1: Exact path match
        candidates = self._try_exact_match(widget_value)
        if len(candidates) == 1:
            ref.resolved_model = candidates[0]
            ref.resolution_confidence = 1.0
            return ModelResolutionResult(ref, candidates, "exact")

        # Strategy 2: Reconstruct paths for native loaders
        if self.model_config.is_model_loader_node(ref.node_type):
            paths = self.model_config.reconstruct_model_path(ref.node_type, widget_value)
            for path in paths:
                candidates = self._try_exact_match(path)
                if len(candidates) == 1:
                    ref.resolved_model = candidates[0]
                    ref.resolution_confidence = 0.9
                    return ModelResolutionResult(ref, candidates, "reconstructed")

        # Strategy 3: Case-insensitive match
        candidates = self._try_case_insensitive_match(widget_value)
        if len(candidates) == 1:
            ref.resolved_model = candidates[0]
            ref.resolution_confidence = 0.8
            return ModelResolutionResult(ref, candidates, "case_insensitive")

        # Strategy 4: Filename-only match
        filename = Path(widget_value).name
        candidates = self.model_index.find_by_filename(filename)
        if len(candidates) == 1:
            ref.resolved_model = candidates[0]
            ref.resolution_confidence = 0.7
            return ModelResolutionResult(ref, candidates, "filename")
        elif len(candidates) > 1:
            # Multiple matches - need disambiguation
            return ModelResolutionResult(ref, candidates, "ambiguous")

        # No matches found
        return ModelResolutionResult(ref, [], "not_found")

    def _try_exact_match(self, path: str) -> list[ModelWithLocation]:
        """Try exact path match"""
        all_models = self.model_index.get_all_models()
        return [m for m in all_models if m.relative_path == path]

    def _try_case_insensitive_match(self, path: str) -> list[ModelWithLocation]:
        """Try case-insensitive path match"""
        all_models = self.model_index.get_all_models()
        path_lower = path.lower()
        return [m for m in all_models if m.relative_path.lower() == path_lower]

    def _looks_like_model(self, value: Any) -> bool:
        """Check if value looks like a model path"""
        if not isinstance(value, str):
            return False
        extensions = ModelConfig.load().default_extensions
        return any(value.endswith(ext) for ext in extensions)
```

### 4. Enhanced Workflow Manager

**Update**: `packages/core/src/comfydock_core/managers/workflow_manager.py`

```python
class WorkflowManager:

    def __init__(self, ...):
        # ... existing init ...
        self.metadata_manager = WorkflowMetadataManager()

    def analyze_workflow_models(self, name: str) -> tuple[list[ModelResolutionResult], dict | None]:
        """Analyze workflow models and return resolution results"""
        workflow_file = self.comfyui_workflows / f"{name}.json"

        # Load workflow
        with open(workflow_file) as f:
            workflow_data = json.load(f)

        # Extract existing metadata if present
        existing_metadata = self.metadata_manager.extract_metadata(workflow_data)

        # Parse and analyze
        parser = WorkflowDependencyParser(
            workflow_file,
            self.model_index_manager,
            ModelConfig.load()
        )
        results = parser.analyze_models_enhanced()

        return results, existing_metadata

    def track_workflow_with_resolutions(
        self,
        name: str,
        resolutions: dict[tuple[str, int], ModelWithLocation] | None = None
    ) -> tuple[int, int]:
        """Track workflow with user-selected resolutions for ambiguous models

        Args:
            name: Workflow name
            resolutions: {(node_id, widget_index): chosen_model} for ambiguous cases

        Returns:
            (resolved_count, unresolved_count)
        """
        workflow_file = self.comfyui_workflows / f"{name}.json"

        # Load workflow
        with open(workflow_file) as f:
            workflow_data = json.load(f)

        # Get analysis
        results, _ = self.analyze_workflow_models(name)

        # Apply resolutions to ambiguous cases
        all_refs = []
        for result in results:
            ref = result.reference
            if result.resolution_type == "ambiguous" and resolutions:
                key = (ref.node_id, ref.widget_index)
                if key in resolutions:
                    ref.resolved_model = resolutions[key]
                    ref.resolution_confidence = 0.9

            all_refs.append(ref)

        # Inject metadata
        workflow_data = self.metadata_manager.inject_metadata(workflow_data, all_refs)

        # Save to both locations
        tracked_file = self.tracked_workflows / f"{name}.json"
        for path in [tracked_file, workflow_file]:
            with open(path, 'w') as f:
                json.dump(workflow_data, f, indent=2)

        # Add resolved models to manifest
        for ref in all_refs:
            if ref.resolved_model:
                self.model_manifest_manager.ensure_model_in_manifest(
                    ref.resolved_model,
                    category="required"
                )

        # Update pyproject
        resolved_hashes = [ref.resolved_model.hash for ref in all_refs if ref.resolved_model]
        workflow_config = {
            "file": f"workflows/{name}.json",
            "requires": {
                "models": resolved_hashes,
                "nodes": []  # Keep existing
            }
        }
        self.pyproject.workflows.add(name, workflow_config)

        # Return counts
        resolved = sum(1 for ref in all_refs if ref.resolved_model)
        unresolved = len(all_refs) - resolved

        return resolved, unresolved
```

### 5. CLI Model Disambiguator

**New File**: `packages/cli/comfydock_cli/interactive/model_disambiguator.py`

```python
class ModelDisambiguator:
    """Handle user disambiguation for ambiguous models"""

    def resolve_ambiguous_models(
        self,
        results: list[ModelResolutionResult]
    ) -> dict[tuple[str, int], ModelWithLocation]:
        """Prompt user to resolve ambiguous models"""
        resolutions = {}

        # Filter to ambiguous cases only
        ambiguous = [r for r in results if r.resolution_type == "ambiguous"]

        if not ambiguous:
            return resolutions

        print(f"\n⚠️  Found {len(ambiguous)} ambiguous model reference(s)")
        print("Please select the correct model for each:\n")

        for result in ambiguous:
            ref = result.reference
            print(f"Node #{ref.node_id} ({ref.node_type})")
            print(f"  Looking for: {ref.widget_value}")
            print("  Found multiple matches:")

            for i, model in enumerate(result.candidates[:10], 1):
                size_mb = model.file_size / (1024 * 1024)
                print(f"    {i}. {model.relative_path} ({size_mb:.1f} MB)")

            print("    s. Skip (leave unresolved)")

            while True:
                choice = input("  Choice [1-10/s]: ").strip().lower()

                if choice == 's':
                    print("  → Skipped\n")
                    break
                elif choice.isdigit():
                    idx = int(choice) - 1
                    if 0 <= idx < len(result.candidates):
                        chosen = result.candidates[idx]
                        resolutions[(ref.node_id, ref.widget_index)] = chosen
                        print(f"  → Selected: {chosen.relative_path}\n")
                        break

                print("  Invalid choice")

        return resolutions

    def show_resolution_summary(self, results: list[ModelResolutionResult]) -> None:
        """Show summary of resolution results"""
        by_type = {}
        for result in results:
            type_key = result.resolution_type
            if type_key not in by_type:
                by_type[type_key] = []
            by_type[type_key].append(result)

        print("\nModel Resolution Summary:")
        if "exact" in by_type:
            print(f"  ✅ {len(by_type['exact'])} exact matches")
        if "reconstructed" in by_type:
            print(f"  ✅ {len(by_type['reconstructed'])} reconstructed paths")
        if "case_insensitive" in by_type:
            print(f"  ✅ {len(by_type['case_insensitive'])} case-insensitive matches")
        if "filename" in by_type:
            print(f"  ✅ {len(by_type['filename'])} filename matches")
        if "ambiguous" in by_type:
            print(f"  ⚠️  {len(by_type['ambiguous'])} ambiguous (need selection)")
        if "not_found" in by_type:
            print(f"  ❌ {len(by_type['not_found'])} not found")

        # Show unresolved details
        if "not_found" in by_type:
            print("\nUnresolved models:")
            for result in by_type["not_found"][:5]:  # Show first 5
                ref = result.reference
                print(f"  - Node #{ref.node_id}: {ref.widget_value}")
            if len(by_type["not_found"]) > 5:
                print(f"  ... and {len(by_type['not_found']) - 5} more")
```

### 6. Updated CLI Commands

**Update**: `packages/cli/comfydock_cli/env_commands.py`

```python
def workflow_track(self, args):
    """Track workflow with smart model resolution"""
    name = args.name
    env = self._get_environment()

    # Analyze workflow
    print(f"Analyzing workflow '{name}'...")
    results, existing_metadata = env.workflow_manager.analyze_workflow_models(name)

    # Show resolution summary
    from comfydock_cli.interactive.model_disambiguator import ModelDisambiguator
    disambiguator = ModelDisambiguator()
    disambiguator.show_resolution_summary(results)

    # Handle ambiguous models
    resolutions = None
    ambiguous = [r for r in results if r.resolution_type == "ambiguous"]
    if ambiguous and not args.skip_disambiguation:
        resolutions = disambiguator.resolve_ambiguous_models(results)

    # Track with resolutions
    resolved_count, unresolved_count = env.workflow_manager.track_workflow_with_resolutions(
        name,
        resolutions
    )

    print(f"\n✅ Workflow '{name}' tracked")
    print(f"   {resolved_count} models resolved")
    if unresolved_count > 0:
        print(f"   ⚠️  {unresolved_count} models unresolved")
        print("   Update paths in ComfyUI to resolve")

    return 0

def workflow_sync(self, args):
    """Sync workflows and update metadata"""
    env = self._get_environment()

    # Sync files first
    results = env.workflow_manager.sync_workflows()

    for name, action in results.items():
        if action != "in_sync":
            print(f"Syncing '{name}': {action}")

            # Re-analyze after sync
            results, _ = env.workflow_manager.analyze_workflow_models(name)

            # Check for new ambiguous models
            ambiguous = [r for r in results if r.resolution_type == "ambiguous"]
            if ambiguous:
                print(f"  ⚠️  Found {len(ambiguous)} ambiguous models after sync")
                from comfydock_cli.interactive.model_disambiguator import ModelDisambiguator
                disambiguator = ModelDisambiguator()
                resolutions = disambiguator.resolve_ambiguous_models(results)

                # Update with resolutions
                env.workflow_manager.track_workflow_with_resolutions(name, resolutions)

    return 0
```

## Implementation Timeline

### Day 1: Core Components (6 hours)
1. **Hour 1-2**: Create ModelReference and ModelResolutionResult models
2. **Hour 3-4**: Implement WorkflowMetadataManager
3. **Hour 5-6**: Enhance WorkflowDependencyParser with resolution strategies

### Day 2: Integration (6 hours)
4. **Hour 1-3**: Update WorkflowManager with new resolution flow
5. **Hour 4-5**: Create ModelDisambiguator CLI component
6. **Hour 6**: Update CLI commands

### Day 3: Testing & Polish (4 hours)
7. **Hour 1-2**: Test resolution strategies with edge cases
8. **Hour 3-4**: Documentation and error handling

## Key Features

1. **Multi-strategy resolution**:
   - Exact match
   - Reconstructed paths (for native loaders)
   - Case-insensitive
   - Filename-only

2. **Smart disambiguation**:
   - Shows all candidates with file sizes
   - User selects correct one
   - Updates metadata only (no widget changes)

3. **No substitution complexity**:
   - Widget values remain unchanged
   - Metadata reflects resolution state
   - User fixes missing models in ComfyUI

4. **Leverages existing code**:
   - Uses ModelIndexManager.find_by_filename()
   - Builds on ModelConfig.reconstruct_model_path()
   - Extends WorkflowDependencyParser

## Testing Checklist

- [ ] Exact path models resolve automatically
- [ ] Case mismatch models resolve correctly
- [ ] Filename-only references prompt for disambiguation
- [ ] Multiple same-name models show selection list
- [ ] Metadata persists through ComfyUI save/reload
- [ ] Unresolved models shown clearly to user
- [ ] CheckpointLoader handles both checkpoint and config