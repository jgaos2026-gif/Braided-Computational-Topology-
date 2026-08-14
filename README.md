# Braided-Computational-Topology-

Braided topology in computation.

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

### Optional config

Copy `/home/runner/work/Braided-Computational-Topology-/Braided-Computational-Topology-/repo-launcher.example.json` to `repo-launcher.json` and customize repo paths or commands if a project needs a specific startup command.
