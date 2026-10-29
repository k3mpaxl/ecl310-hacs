# Issue 47 Installation Settings and Diagnostics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax.

**Goal:** Implement all applicable Issue 47 installation and diagnostic functions for the seven supported application profiles in one test build.

**Architecture:** Explicitly declare known functions and their ECL semantics, with profile-specific availability and domains. Extend existing circuit components and Home Assistant entities, and add isolated alarm/limiter diagnostics; preserve stable identities and the generic fallback. Use a single test branch and real-device testing only when authorized.

**Tech Stack:** Python 3.14, Home Assistant custom component, vendored ecl310_modbus, modbus-connection, pytest-homeassistant-custom-component, Ruff.

**Spec:** `docs/superpowers/specs/2026-10-29-issue-47-installation-diagnostics-design.md`.

## Global Constraints

- Scope: A237.1 V04, A266.10 V03, A337.2 V02, A367.1 V01–V04; do not expose new installer fields in generic mode.
- PNU is Modbus register address + 1; profile membership and circuit determine entity creation.
- New installer settings and explicit alarm clearing are disabled by default; preserve existing entity IDs, settings and behavior.
- Verify semantics, especially OFF values and write commands, against Danfoss manuals; never guess when data is insufficient. Do not perform writes to a physical controller during implementation.
- Do not merge main, create a tag, release or post externally. Publish only the test branch when ready.
- Do not confuse simulated or captured register fixtures with physical write validation. A237.1 and A266.10 are the available physical test targets.

## Review Focus

- A single refused optional parameter must leave the remaining climate circuit operational: Task 1 and each owning setting task.
- OFF/sentinel value outside the editable numerical domain must remain readable and restorable: Task 2.
- A read failure or partially supported alarm/limiter set must not produce a false all-clear or inactive status: Tasks 5–6.
- A367.1 second heating circuit and third hot-water circuit must address the right registers with no duplicate entity IDs: Tasks 1–6.
- Profile-specific raw limits, signedness, scaling, enum choices and rejected writes must match the real profile, including 11043 A266.10 max 99 versus A237.1 max 100: Tasks 1–4.

## File map

- `custom_components/ecl310/ecl310_modbus/subsystems/heating_circuit.py`, `hot_water.py`, new focused setting modules: explicit circuit datapoints and metadata.
- `custom_components/ecl310/ecl310_modbus/subsystems/circuits.py`, `data_model.py`, `ecl310.py`, `configurations/address_ranges.py`: profile-aware domain validation, offsets, field selection and safe read planning.
- `custom_components/ecl310/number.py`, `switch.py`, `select.py`, translations: HA control entities, stable IDs and clear labels.
- New alarm and limiter subsystem files and appropriate HA sensor/binary_sensor/button platforms; `coordinator.py` and `diagnostics.py`: truthful diagnostics and availability.
- `tests/test_return_limits.py`, new `tests/test_installation_settings.py`, `tests/test_ecl_alarms.py`, `tests/test_limiter_status.py`, plus existing fixture and regression tests.
- `docs/testing-return-limits.md`, new test matrix and optional dashboard example: actual scope and verification state.

## Task 1: Profile-specific domains and poll isolation

**Files:** Modify `ecl310_modbus/data_model.py`, `subsystems/circuits.py`, `ecl310.py`, `configurations/address_ranges.py`; test `tests/test_installation_settings.py`.

**Interfaces:** Existing `Ecl310.supports(component, field)`, `Ecl310Component.metadata_for(field)`, and `component.write(field, value)` remain stable. New declared setting fields must be restricted by selected profile and carry the selected profile's min, max, scale, signedness and writability. Unknown profile must expose none of the new fields.

- [ ] Add tests for A266.10 PNU 11043 max 99 and A237.1 max 100; assert 100 rejected on A266 before I/O and accepted on A237, and A367 circuit 2 uses PNU 12043 where present.
- [ ] Run `PYTHONPATH=/private/tmp/ecl310-issue47-py:$PWD python3 -m pytest tests/test_installation_settings.py -q`; verify failures show the missing behavior.
- [ ] Implement explicit per-profile validation and metadata binding, retaining field semantics and current IDs. Never mutate shared descriptor state between controllers.
- [ ] Add a simulated refused-field test and measure read blocks for adding a contiguous group versus the baseline. Isolate optional reads so a refusal does not disable climate; explicitly document any added polling.
- [ ] Run the targeted tests and `tests/test_applications.py` and `tests/test_return_limits.py`; commit only passing changes.

## Task 2: Optimisation and special OFF values

**Files:** Modify heating circuit model, `number.py`, `switch.py`, translations; add focused helpers as needed; test `tests/test_installation_settings.py`.

**Interfaces:** Declare unique field names for 1x011–014, 1x026 and 1x043; use existing `per_circuit`, number and switch APIs. Preserve x021.

- [ ] Test profile-specific creation, circuit offsets, disabled defaults, `11011` signed read/write, `11043` domain difference, and x014 OFF 9 and normal range 10–59, including round-trip off/on after HA restart. Test rejected values leave the register unchanged.
- [ ] Confirm Danfoss application guide behavior and OFF domains for every new field; encode only verified options; write failing tests for them.
- [ ] Implement numeric/switch entities with readable OFF behavior and a path back to OFF; use the same unit and ECL menu attributes as the actual profile.
- [ ] Run targeted tests for all seven profiles, translations check and existing integration suite; commit.

## Task 3: Control valve, pump and seasonal settings

**Files:** Modify heating and hot-water model, number/switch/select platforms, translations, read ranges; test `tests/test_installation_settings.py`.

**Interfaces:** Per-circuit fields for 1x024, 1x174, 1x184–187, 1x189, 1x022–023, 1x077–078, 1x392–393, 1x395–399. Use existing HA device and `ecl_name`/PNU attributes.

- [ ] For each parameter enumerate the seven profile/circuit combinations and compare type/range/scale/writable to XML; verify option labels, special values and units against the relevant manual before exposing a write.
- [ ] Write tests for A266 valve PNU 12024/12186, A367 heating 12024/12186, absent A337 seasonal entries, correct min/max at month/day edges, 16-bit filter 300, invalid actuator options, OFF values and rejected gaps.
- [ ] Implement explicitly named settings, with supported-circuit detection, disabled defaults and English/German translations; keep x040, x093, x179 untouched.
- [ ] Run targeted tests, existing A266/A367/return limit regressions, lint and translation check; commit.

## Task 4: Alarm settings

**Files:** Modify circuit models, number/switch/select platforms and translations; test `tests/test_installation_settings.py`.

**Interfaces:** Known fields for 1x079–080, 1x147–150, 1x636–637 where profile permits and manual establishes semantics; x617 absent in all supported XMLs and recorded as unavailable.

- [ ] Compare XML and applicable guides, including the A266 manual, for units, options, OFF and ranges. Do not use another application's interpretation for undocumented A266 options.
- [ ] Add tests verifying A266 x079/080 and x636/637 behavior and absence of x147–150, A237 x147–150 behavior and absence of x079/080, and x617 absence. Verify rejected writes and profile-gated creation.
- [ ] Implement verified controls, reusing common helpers and preserving IDs; document any unverified function explicitly as unavailable, rather than guessing.
- [ ] Run targeted tests and translations; commit.

## Task 5: Read and clear alarms

**Files:** Create `ecl310_modbus/subsystems/alarms.py` and HA diagnostic entities; update component registration, coordinator and diagnostics; add `tests/test_ecl_alarms.py`.

**Interfaces:** Expose alarm status and active IDs from PNU 1025 bits 0–15 (IDs 1–16) and 1024 bits 0–15 (IDs 17–32). Map context ID n to PNU `1039+n`. Any missing necessary mask makes the aggregate unavailable, not off.

- [ ] Check the Danfoss communication guide and supported application guides for mask ordering, context semantics and exact clearing writes to 1032/1033. Record source/version. Do not expose a clear action if its semantics remain unverified.
- [ ] Add tests for masks 1025 bit 0 → ID 1 and 1024 bit 1 → ID 18, context PNU 1057 for ID 18, zero masks, partial refusal/connection failure and unknown application-specific alarm meanings.
- [ ] Implement isolated read-only diagnostics and HA entities, with refused/partial reads represented as unavailable and diagnostics preserving raw words.
- [ ] If reset semantics are documented, first add tests for the exact value/address, no automatic writes, disabled-by-default action, refused writes and observed readback; then implement explicit clearing. If not, record the limitation in docs instead.
- [ ] Run alarm tests plus the full integration regressions; commit.

## Task 6: Limiter status

**Files:** Create `ecl310_modbus/subsystems/limiter.py` and HA diagnostic entities, integrate coordinator and diagnostics; add `tests/test_limiter_status.py`.

**Interfaces:** PNU base per circle `{1: 4220, 2: 4224, 3: 4228, 4: 4232, 5: 4246, 6: 4250}`; four words per circuit. Two-bit values 0 = none, 1 = higher, 2 = lower, 3 = changed. Firmware <1.32 has no feature; later word-4 flags have individually documented version floors.

- [ ] Write tests for values 0–3 at independent bit positions, circuit 1/2/3 mapping, unknown/reserved bits, partial refusal, missing firmware and 1.32/1.54/1.56/1.58 version boundaries. Unsupported/missing data must not appear as no influence.
- [ ] Implement profile/circuit-aware read-only decoding and per-circuit diagnostic entities; preserve raw words for diagnostics and isolate optional failures from climate polling.
- [ ] Run limiter and integration tests, including A367 second heating and third hot water; commit.

## Task 7: Integration, coverage matrix and delivery

**Files:** Update `docs/testing-return-limits.md`, add `docs/issue-47-test-matrix.md`, optional dashboard example if HA device pages cannot provide menu groups; update relevant README and integration source notes.

- [ ] Create a profile/function matrix distinguishing automated coverage, actual hardware confirmation (source and date) and unavailable/not verified, including x617 and alarm reset if unresolved.
- [ ] Document real-device test procedure, entity activation, backup and restore, rollback, expected groups, safe optional writes and remaining limitations. Include guidance for the A237.1 and A266.10; never imply A337.2/A367.1 were physically tested.
- [ ] Verify live Home Assistant capabilities for grouping, and document the result; provide an optional non-invasive dashboard example if needed.
- [ ] Run `python3 -m ruff check .`, `python3 -m ruff format . --check`, `python3 scripts/translations --check`, and the full `PYTHONPATH=/private/tmp/ecl310-issue47-py:$PWD python3 -m pytest -q`; inspect every result. Run meaningful comparison of polling cost.
- [ ] Review complete diff, reconcile vendored library implications, commit, and push only `test/issue-47-return-limits`. Verify remote commit, clean local status, ZIP/test instructions and no main/tag/release changes. Do not post to the issue without an explicit message instruction.
