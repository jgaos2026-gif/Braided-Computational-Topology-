# Braided-Computational-Topology-

This project is my small, curious corner for thinking about how braided structures, motion, and topology can inform computation. I want it to feel less like a dry notebook and more like an invitation to explore patterns that twist, loop, and interact in surprising ways.

## Why braided computational topology?

At a high level, braided computational topology studies how strands can move around one another without tearing, and how those motions preserve deeper structure. In mathematical terms, the project is interested in braid groups, isotopy classes, and invariants that help describe when two tangled processes are meaningfully the same.

That makes the subject exciting to me: a braid is not just a picture, but a record of interaction. It turns motion into algebra, and algebra back into geometry.

## Research note

The broader mathematical direction of this repository is still being studied. The current code is practical and usable, while the larger research story around braided computational topology is still evolving.

## Repo launcher

This repository now includes a small cross-platform launcher at `/home/runner/work/Braided-Computational-Topology-/Braided-Computational-Topology-/launcher.py`.

It can:
- discover sibling Git repositories
- open a repo folder in the system file browser
- run common app entry commands when they can be inferred
- generate a desktop helper script
- generate one desktop launcher per discovered repo

### Quick start

List nearby repos:

```bash
python /home/runner/work/Braided-Computational-Topology-/Braided-Computational-Topology-/launcher.py list
```

Launch a repo by name:

```bash
python /home/runner/work/Braided-Computational-Topology-/Braided-Computational-Topology-/launcher.py launch REPO_NAME
```

Create a desktop helper script:

```bash
python /home/runner/work/Braided-Computational-Topology-/Braided-Computational-Topology-/launcher.py create-desktop-script
```

Create desktop launchers for every discovered repo:

```bash
python /home/runner/work/Braided-Computational-Topology-/Braided-Computational-Topology-/launcher.py create-desktop-launchers
```

That command writes runnable `.sh` or `.cmd` files to your desktop so you can launch each repo directly from there.

## Current test results

The launcher is currently covered by automated unit tests, and the latest local run completed successfully:

- `python -m unittest discover -s tests -v`
- Result: **7 tests passed**
- Runtime: **0.004s** on the latest verification run

These tests focus on repository discovery, command inference, config overrides, and desktop launcher generation.

### Optional config

Copy `/home/runner/work/Braided-Computational-Topology-/Braided-Computational-Topology-/repo-launcher.example.json` to `repo-launcher.json` and customize repo paths or commands if a project needs a specific startup command.
