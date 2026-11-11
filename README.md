# cds-capstone

## Getting started

This repo includes [KA-opensquare-research-project](https://github.com/NYULibraries/KA-opensquare-research-project) as a git submodule in `opensquare-reference/`, which we use as a reference for our work. Clone with submodules so that folder isn't empty:

```sh
git clone --recurse-submodules <repo-url>
```

If you already cloned without that flag, run:

```sh
git submodule update --init
```

## Updating the reference repo

To pull the latest upstream changes into `opensquare-reference/`:

```sh
git submodule update --remote opensquare-reference
```

Then commit the updated submodule pointer so everyone gets the same version.
