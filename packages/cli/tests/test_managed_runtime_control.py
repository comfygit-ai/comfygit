import json
import os
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import requests
from comfygit_cli.utils.runtime_client import RuntimeClient
from comfygit_core.runtime import (
    RUNTIME_RESTART_ROUTE,
    ManagedRuntimeController,
    SwitchObserverServer,
    read_runtime_advertisement,
    resolve_comfyui_endpoint,
)


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


@pytest.fixture
def runtime(tmp_path):
    state = {'running': [], 'pending': [], 'posts': 0, 'owner': 'sample', 'restart': False}
    port = free_port()
    controller = ManagedRuntimeController('sample', resolve_comfyui_endpoint(['--port', str(port)]), tmp_path)

    class FakeComfyUI(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def send_json(self, payload):
            data = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == '/system_stats':
                self.send_json({'system': {}})
            elif self.path == '/queue':
                self.send_json({'queue_running': state['running'], 'queue_pending': state['pending']})
            elif self.path == '/v2/comfygit/environments':
                self.send_json({'current': state['owner'], 'orchestrator_active': state.get('legacy', False), 'runtime_context': {
                    'bound_workspace': str(tmp_path), 'capabilities': {'can_restart_current': True},
                }})
            else:
                self.send_error(404)

        def do_POST(self):
            assert self.path == '/v2/comfygit/orchestrator/restart'
            state['posts'] += 1
            self.send_json({'status': 'restarting'})
            if state['restart']:
                # Stand in for cg run receiving exit 42, syncing and launching again.
                def relaunch():
                    time.sleep(0.05)
                    controller.exited()
                    controller.configure('sample', controller.endpoint)
                    controller.launching()
                threading.Thread(target=relaunch, daemon=True).start()

    comfy = ThreadingHTTPServer(('127.0.0.1', port), FakeComfyUI)
    threading.Thread(target=comfy.serve_forever, daemon=True).start()
    observer = SwitchObserverServer(tmp_path, '127.0.0.1', free_port(), runtime_controller=controller)
    observer.start()
    controller.launching()
    client = RuntimeClient(tmp_path, 'sample')
    try:
        yield controller, client, state
    finally:
        observer.stop()
        comfy.shutdown()
        comfy.server_close()
    assert read_runtime_advertisement(tmp_path, 'sample') is None


def test_status_and_restart_wait_for_new_generation(runtime):
    controller, client, state = runtime
    before = client.status()
    assert before['ready'] is True
    assert before['queue_running'] == 0
    state['restart'] = True
    after = client.restart(wait=True, timeout=3)
    assert after['generation'] == before['generation'] + 1
    assert after['status'] == 'ready'
    assert state['posts'] == 1


@pytest.mark.parametrize('queue', ['running', 'pending'])
def test_restart_refuses_busy_queue(runtime, queue):
    _, client, state = runtime
    state[queue] = ['job']
    with pytest.raises(ValueError, match='running or pending'):
        client.restart(wait=False, timeout=1)
    assert state['posts'] == 0


def test_restart_refuses_unknown_queue(runtime):
    _, client, state = runtime
    state['running'] = None
    with pytest.raises(ValueError, match='Cannot verify'):
        client.restart(wait=False, timeout=1)
    assert state['posts'] == 0


def test_restart_refuses_another_environment_at_same_port(runtime):
    _, client, state = runtime
    state['owner'] = 'another-environment'
    with pytest.raises(ValueError, match='ownership'):
        client.restart(wait=False, timeout=1)
    assert state['posts'] == 0


def test_restart_refuses_manager_proxy_to_a_legacy_owner(runtime):
    _, client, state = runtime
    state['legacy'] = True
    with pytest.raises(ValueError, match='legacy orchestrator'):
        client.restart(wait=False, timeout=1)
    assert state['posts'] == 0


def test_unchanged_generation_never_counts_as_completed_restart(runtime):
    _, client, state = runtime
    with pytest.raises(TimeoutError, match='not verified'):
        client.restart(wait=True, timeout=0.1)
    assert state['posts'] == 1
    with pytest.raises(ValueError, match='already requested'):
        client.restart(wait=False, timeout=1)
    assert state['posts'] == 1


def test_restart_refuses_stale_identity_and_browser_requests(runtime):
    controller, client, state = runtime
    stale = client.status()
    controller.launching()
    response = requests.post(client.url + RUNTIME_RESTART_ROUTE, json=stale, timeout=2)
    assert response.status_code == 409
    response = requests.post(client.url + RUNTIME_RESTART_ROUTE, json=client.status(),
                             headers={'Origin': 'https://example.com'}, timeout=2)
    assert response.status_code == 403
    assert state['posts'] == 0


def test_real_run_loop_restarts_child_after_exit_42(test_env, tmp_path):
    """Exercise the real run loop/Environment.run against disposable HTTP children.

    Skip dependency sync/backend probing; no GPU, downloads or live environment.
    """
    port = free_port()
    observer_port = free_port()
    subprocess.run([sys.executable, '-m', 'venv', '--without-pip', str(test_env.path / '.venv')], check=True)
    workspace = test_env.workspace.path
    script = '''
import json, os, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def reply(self, payload):
        data=json.dumps(payload).encode()
        self.send_response(200); self.send_header('Content-Length', str(len(data)))
        self.end_headers(); self.wfile.write(data)
    def do_GET(self):
        if self.path == '/system_stats': self.reply({'system': {'pid': os.getpid()}})
        elif self.path == '/queue': self.reply({'queue_running': [], 'queue_pending': []})
        elif self.path == '/v2/comfygit/environments':
            self.reply({'current': os.environ['COMFYGIT_ENV_NAME'], 'runtime_context': {
                'bound_workspace': WORKSPACE, 'capabilities': {'can_restart_current': True}}})
        else: self.send_error(404)
    def do_POST(self):
        if self.path not in ('/v2/comfygit/orchestrator/restart', '/test/stop'):
            self.send_error(404); return
        code=42 if self.path.endswith('/restart') else 0
        self.reply({'status': 'restarting'})
        def stop(): time.sleep(.05); os._exit(code)
        threading.Thread(target=stop, daemon=True).start()
ThreadingHTTPServer(('127.0.0.1', PORT), Handler).serve_forever()
'''
    (test_env.comfyui_path / 'main.py').write_text(
        f'WORKSPACE={str(workspace)!r}\nPORT={port}\n' + script,
    )
    runner = f'''
from pathlib import Path
from argparse import Namespace
from comfygit_core import Workspace
from comfygit_cli.env_commands import EnvironmentCommands
workspace=Workspace.open(Path({str(workspace)!r}))
env=workspace.get_environment('test-env', auto_sync=False)
env.sync=lambda **kwargs: None
command=EnvironmentCommands()
command.workspace=workspace
command._get_env=lambda args: env
command._get_or_probe_backend=lambda *args: ('cpu', False)
command.run(Namespace(target_env='test-env', no_sync=True, args=['--port', '{port}'], torch_backend=None))
'''
    process = subprocess.Popen([sys.executable, '-c', runner], stdout=subprocess.DEVNULL,
                               stderr=subprocess.PIPE, text=True, env={
                                   **os.environ, 'COMFYGIT_SUPERVISOR_CONTROL_HOST': '127.0.0.1',
                                   'COMFYGIT_SUPERVISOR_CONTROL_PORT': str(observer_port),
                               })
    try:
        deadline = time.monotonic() + 10
        client = None
        while time.monotonic() < deadline:
            if process.poll() is not None:
                pytest.fail(process.communicate()[1])
            try:
                client = RuntimeClient(workspace, 'test-env')
                if client.status()['ready']:
                    break
            except (ValueError, requests.RequestException):
                pass
            time.sleep(.1)
        assert client is not None and client.status()['ready']
        url = f'http://127.0.0.1:{port}'
        before_pid = requests.get(url + '/system_stats', timeout=2).json()['system']['pid']
        completed = client.restart(wait=True, timeout=10)
        after_pid = requests.get(url + '/system_stats', timeout=2).json()['system']['pid']
        assert completed['generation'] == 2
        assert after_pid != before_pid
        requests.post(url + '/test/stop', timeout=2)
        _, stderr = process.communicate(timeout=5)
        assert process.returncode == 0, stderr
    finally:
        # Always stop the disposable HTTP child before its supervisor.
        try:
            requests.post(f'http://127.0.0.1:{port}/test/stop', timeout=1)
        except requests.RequestException:
            pass
        if process.poll() is None:
            process.terminate()
            process.communicate(timeout=5)
