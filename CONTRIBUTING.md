# Contributing

Contributions are welcome. This repository is the **custom integration**; most
changes belong somewhere else, so it is worth knowing which of the three parts
you are actually changing.

## Where does my change go?

| Change | Repository |
| :----- | :--------- |
| A new datapoint, a decoding fix, a register range | [`ecl310-modbus`](https://github.com/k3mpaxl/ecl310-modbus) - the device library |
| A new entity, an entity naming or icon change, config flow | here, in `custom_components/ecl310` |
| Anything to do with getting the integration into Home Assistant core | the core integration folder |

The `custom_components/ecl310/ecl310_modbus` directory is a **vendored copy** of
the library, not the place to edit it. Fix the library upstream, then run:

```bash
scripts/vendor-library
```

A workflow compares the vendored copy against upstream and fails the build if
they have drifted apart.

## Getting set up

The repository ships a devcontainer. Open it in VS Code, or set things up by
hand:

```bash
scripts/setup     # install Home Assistant and the tooling
scripts/develop   # run Home Assistant with this integration loaded
scripts/lint      # format and lint
scripts/test      # run the integration inside a real Home Assistant
```

`scripts/develop` starts a throwaway Home Assistant on
<http://localhost:8123> with `custom_components` on the path, so the
integration appears in *Add integration* straight away.

## Before opening a pull request

- `scripts/lint` and `scripts/test` pass.
- The integration still loads with `scripts/develop`.
- If you touched the config flow or the entity set, say in the PR what a user
  has to do to their existing entry, if anything.
- If you changed how a value decodes, attach the diagnostics download that
  shows it - the raw register map is what proves the change is right.
