import argparse
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from comfygit_cli.cli import create_parser
from comfygit_cli.env_commands import EnvironmentCommands
from comfygit_core.models import NodeInfo, ResolutionResult


def test_json_strict_reports_final_unresolved_state(capsys):
    args = create_parser().parse_args([
        'workflow', 'resolve', 'sample', '--auto', '--no-install', '--json', '--strict',
    ])
    handler = EnvironmentCommands()
    handler._workflow_resolve = Mock(side_effect=lambda _: print('progress'))
    env = Mock()
    env.analyze_workflow_dependencies.return_value = (None, ResolutionResult(
        workflow_name='sample', nodes_unresolved=[SimpleNamespace(type='Local')],
    ))
    env.get_uninstalled_nodes.return_value = []
    env.get_workflow_failed_downloads.return_value = []
    handler._get_env = Mock(return_value=env)
    with pytest.raises(SystemExit) as exc:
        handler.workflow_resolve(args)
    assert exc.value.code == 1
    output = capsys.readouterr()
    result = json.loads(output.out)
    assert result['complete'] is False
    assert result['nodes']['unresolved'] == ['Local']
    assert 'progress' in output.err


def test_strict_uses_fresh_status_after_install(capsys):
    args = create_parser().parse_args([
        'workflow', 'resolve', 'sample', '--auto', '--install', '--json', '--strict',
    ])
    handler = EnvironmentCommands()
    handler._workflow_resolve = Mock()
    env = Mock()
    env.analyze_workflow_dependencies.return_value = (None, ResolutionResult(workflow_name='sample'))
    env.get_uninstalled_nodes.return_value = []
    env.get_workflow_failed_downloads.return_value = []
    handler._get_env = Mock(return_value=env)
    handler.workflow_resolve(args)
    assert json.loads(capsys.readouterr().out)['complete'] is True
    env.analyze_workflow_dependencies.assert_called_once_with('sample')


def test_json_requires_noninteractive_install_choice():
    args = create_parser().parse_args(['workflow', 'resolve', 'sample', '--auto', '--json'])
    with pytest.raises(SystemExit) as exc:
        EnvironmentCommands().workflow_resolve(args)
    assert exc.value.code == 2


def test_mapping_persists_and_unmaps_without_internal_api(test_env, capsys):
    path = test_env.get_workflow_path('sample')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'nodes': [{'id': 1, 'type': 'Local'}]}))
    handler = EnvironmentCommands()
    handler._get_env = Mock(return_value=test_env)
    # Node tracking itself is covered by node dev-link tests.
    test_env.get_manifest_node = Mock(return_value=NodeInfo(name='local', version='dev', source='development'))
    args = argparse.Namespace(name='sample', node_type='Local', package='local', json=True, mapping_command='map')
    handler.workflow_node_mapping(args)
    assert json.loads(capsys.readouterr().out)['custom_node_map']['Local'] == 'local'
    args.mapping_command = 'unmap'
    handler.workflow_node_mapping(args)
    assert json.loads(capsys.readouterr().out)['custom_node_map'] == {}


def test_mapping_rejects_untracked_package(test_env):
    path = test_env.get_workflow_path('sample')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"nodes": []}')
    handler = EnvironmentCommands()
    handler._get_env = Mock(return_value=test_env)
    args = argparse.Namespace(name='sample', node_type='Local', package='typo', json=True, mapping_command='map')
    with pytest.raises(ValueError, match='not tracked'):
        handler.workflow_node_mapping(args)
    assert not test_env.get_workflow_custom_node_map('sample')
