# ComfyUI Source Materialization Proof

Date: 2026-08-30  
Host: `akatzfeyserver`  
Scope: private scratch validation; no workflow or public environment repository published

## Contract under test

The portable environment declared:

- ComfyUI repository `https://github.com/kijai/ComfyUI.git`
- version intent `vsa`
- immutable commit `10febb01d7be73d1491cf5e5347b5ab8b6c2c09e`
- Python 3.11 and CUDA 13.0 PyTorch
- three required Git custom nodes at exact commits
- five opaque-loader H3 models with explicit source URLs, paths, sizes, and
  ComfyGit content hashes

The scratch node repositories and smoke prompt were intentionally excluded from
the ComfyGit source tree. They stand in for the public H3 Relay/VSA assets that
will be pinned after those repositories are ready.

## Container boundary

The proof used a clean image based on
`nvidia/cuda:13.0.2-base-ubuntu24.04`. The image installed only Git, curl,
FFmpeg, OpenGL runtime libraries, `build-essential`, and uv. It mounted the
dedicated scratch workspace/model directory and used NVIDIA Container Runtime
against the RTX 4090.

The first runtime attempt exposed a real clean-host prerequisite: Triton's
first-run helper compilation failed when no C compiler was installed. Adding
`build-essential` fixed the runtime without changing the environment manifest.
Public installer guidance must retain this OS prerequisite unless the selected
PyTorch/Triton distribution removes it.

## Materialization results

`cg materialize` was run first with `--models skip`, then from the same portable
source with `--models required` and a fresh model directory.

Verified results:

- restored/cloned ComfyUI origin exactly matched the declared fork;
- checkout HEAD exactly matched the 40-character manifest commit;
- ComfyUI cache identity was isolated by repository and immutable commit;
- all three required node repositories were installed at their declared commits;
- PyTorch resolved to `2.13.0+cu130` and CUDA was available in the container;
- the pinned comfy-kitchen wheel exposed CUDA `sol_attn`;
- all five required models downloaded successfully and were indexed at the
  declared paths and ComfyGit hashes;
- inventory reported one environment with the fork, commit, five model
  dependencies, and three node dependencies;
- live ComfyUI registered H3 Relay FastH3, H3 Ultimate, MMH3 Ultimate, learned
  latent-upscale, and `SolAttnMiniMax` node types.

The initial skip-model pass also exposed that sync could report success while
required nodes remained absent. Materialization now performs a post-sync
filesystem/manifest comparison and fails when a required custom node is still
missing. Optional nodes remain non-blocking.

## GPU smoke result

A private six-node API prompt generated one FastH3 raw shot and passed its
accepted AV latent through H3 Ultimate 2x enhancement:

- prompt id: `e35b69af-025d-4f90-96bb-42879e74e874`
- wall time reported by ComfyUI: 29.00 seconds
- raw output: 416x256, 24 fps, 39 frames / 1.625 seconds, H.264 + AAC
- Ultimate output: 832x512, 24 fps, 39 frames / 1.625 seconds, H.264 + AAC
- queue result: success, no node validation errors

Evidence remains under the dedicated scratch root:

`/scratch/akatz-labs/COMFYGIT-H3-VSA-MATERIALIZE-TEST`

The GPU container and temporary HTTP Git source were stopped after the proof.
The downloaded model directory, materialized environment, inventory, prompt
receipt, history, and generated cache artifacts remain available for review.

## Public-release follow-ups

Before publishing a user-facing environment:

1. Replace private scratch node sources with public immutable Git commits.
2. Use a released comfy-kitchen wheel containing the merged VSA kernel instead
   of the private test wheel path.
3. Add the final public workflow and reference assets from their owning repo.
4. Repeat cold materialization from the public URLs without scratch mounts.
5. Publish a ComfyGit release containing the repository/commit source contract.
