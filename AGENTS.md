# AGENTS.md

## Layout

- `opensquare-reference/` — git submodule pointing at https://github.com/NYULibraries/KA-opensquare-research-project. Use it as a guide for this project; don't edit it.

## Setup

- Clone with `git clone --recurse-submodules <url>`, or after a plain clone run `git submodule update --init`. Otherwise `opensquare-reference/` is empty.
- To pull upstream updates to the reference repo: `git submodule update --remote opensquare-reference`, then commit the changed submodule pointer.
