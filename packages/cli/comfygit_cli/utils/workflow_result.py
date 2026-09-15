"""JSON boundary for the CLI's post-resolution completion check."""
from __future__ import annotations

from collections.abc import Sequence

from comfygit_core.models import ManifestWorkflowModel, ResolutionResult


def resolution_report(
    result: ResolutionResult,
    uninstalled: Sequence[str],
    failed_downloads: Sequence[ManifestWorkflowModel],
) -> dict:
    mismatches = [m.name for m in result.models_resolved if m.has_category_mismatch]
    pending = [m.name for m in result.models_resolved
               if m.match_type in {"download_intent", "property_download_intent"}
               and m.resolved_model is None]
    return {
        "schema_version": 1,
        "workflow": result.workflow_name,
        "complete": not (result.has_issues or uninstalled or failed_downloads or mismatches or pending),
        "nodes": {
            "resolved": [{"node_type": n.node_type, "package_id": n.package_id}
                         for n in result.nodes_resolved],
            "unresolved": sorted({n.type for n in result.nodes_unresolved}),
            "ambiguous": [[n.package_id for n in group] for group in result.nodes_ambiguous],
            "version_gated": sorted({n.type for n in result.nodes_version_gated}),
            "uninstallable": [n.node_type for n in result.nodes_uninstallable],
            "uninstalled_packages": sorted(uninstalled),
        },
        "models": {
            "resolved": [m.name for m in result.models_resolved if m.resolved_model is not None],
            "unresolved": [m.widget_value for m in result.models_unresolved],
            "ambiguous": [[m.name for m in group] for group in result.models_ambiguous],
            "category_mismatches": mismatches,
            "pending_downloads": pending,
            "failed_downloads": [m.filename for m in failed_downloads],
        },
        "guidance": result.node_guidance,
    }
