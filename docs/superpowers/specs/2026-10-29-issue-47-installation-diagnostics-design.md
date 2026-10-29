# Issue 47: Installation settings and diagnostics

## Intent and agreed scope

Obelixed wants the requested ECL installation settings and diagnostics in Home Assistant, attached to the relevant control circuit and understandable alongside the ECL menus. Gregor wants the complete requested scope in one larger test build, initially limited to applications already supported by the integration. His A237.1 and Obelixed's A266.10 are the only installations available for real-device tests. A337.2 and A367.1 remain in scope with automated tests, without a claim of real-device verification.

Supported profiles are A237.1 V04, A266.10 V03, A337.2 V02 and A367.1 V01–V04. The current `test/issue-47-return-limits` branch already implements the return-limit parameters, including priority. Obelixed has confirmed the original return-limit values and writes on A266.10; PNU 11085 was added afterwards and has not yet been confirmed on a real device.

The result is a single test branch/build for the whole issue. Keep existing entity IDs and behavior. New installer settings are disabled by default. No merge to `main`, tag, release, or external comment is part of this design; discuss those separately after test feedback.

## Approaches and decision

1. **Explicitly model the requested functions**, using common helpers and application profiles for presence, circuits and verified domains. Special values, selectable states and meaning are reviewed against Danfoss documentation. This is the approach Gregor selected.
2. Generate arbitrary Home Assistant entities for all XML parameters. This might later cover more applications, but the reports do not consistently define OFF values, descriptions of selections, circuit roles or alarm meaning. It is not the chosen approach.

The implementation may refactor common data structures, but must not expose arbitrary parameters merely because they occur in an XML report. The vendor library is copied into HACS; preserve an upstream-compatible separation and document any work required to reconcile `ecl310-modbus` before future vendoring can overwrite the branch's changes. No upstream release is required for this test build.

## Functional scope and acceptance

Numbers below are ECL PNUs, not zero-based Modbus addresses. `1x` denotes the circuit where applicable; include additional circuit instances only when the particular supported profile and circuit supply them. Existing settings must not be recreated under new IDs.

- **5.2 flow and 5.12 disinfection:** retain existing functionality; the issue calls these already implemented. Regression tests protect them.
- **5.4 return limit:** retain the existing curve, influence, adaptation, priority and the existing return limit. Include priority 11085/12085 only where the profile has it. Document which parts have real-device confirmation.
- **5.6 optimisation:** add x011 automatic saving, x012 heat-up boost, x013 ramp, x014 building factor, x026 optimised stop and x043 parallel operation. x021 pump off during setback already exists. Honour special OFF values and their proper representation, including x014; verify their behavior in the relevant application guides, not by assuming an XML minimum is a normal number.
- **5.7 control parameters:** add x024 actuator type, x174 motor protection, x184 proportional band, x185 integral time, x186 motor running time, x187 neutral zone and x189 minimum pulse. Support every eligible heating and hot-water circuit in the supported profiles, not just A266. Ensure any select's raw values and labels are verified before exposing writes.
- **5.8 application and pump:** add x022 pump exercise, x023 valve exercise, x077 pump frost protection and x078 pump start threshold. x040 pump post-run and x093 frost protection already exist and retain identity.
- **5.9 heating off:** add x392–x393 summer start month/day, x395 summer filter, x396–x397 winter start month/day, x398 winter off and x399 winter filter, where supported. x179 summer off already exists. Verify special values and ranges; do not infer that every application has all fields.
- **5.10 alarm settings:** add x079, x080, x147–x150, x636 and x637 wherever present and meaning is verified. The issue also asks for x617; this PNU is absent from the seven existing profiles checked. Record it as unavailable for these profiles rather than inventing a register or declaring it implemented. Review A266-specific options and units against the applicable manual.
- **5.11 alarms:** read PNU 1024/1025 to expose whether an alarm is active and the active alarm IDs; expose available context from PNU 1040–1071 and identify meanings only when supported by reliable application-specific documentation. Include the requested alarm clearing using PNU 1032/1033 **only once** the applicable Danfoss documentation establishes the exact write semantics; never guess an acknowledgement value or claim that a request cleared the controller's alarms before reading back. A missing or refused alarm register is unavailable, not an all-clear. Expose clearing as an explicit, disabled-by-default action; report any unsupported/undocumented reset as a remaining limitation for that controller.
- **Limiter status:** decode the four two-bit-field words per circuit from the communication description §6.17; show active influences and direction on the associated circuit. For circuits 1–3 use the documented addresses, and do not calculate a simple linear address for circuits 5/6. Respect firmware support (base feature from 1.32; later word-4 fields have their own minimum versions) and preserve unknown/reserved values rather than presenting them as no influence. Treat refused words as unavailable; never synthesize zero. Include raw flags in diagnostics where feasible.
- **Grouping:** assign entities to their existing circuit devices and to configuration/diagnostic categories, with descriptive names and ECL menu name/PNU attributes. Assess current Home Assistant capabilities before promising section-level grouping. If the normal device page cannot group by ECL menu, document that limitation and provide an optional example dashboard with sections; do not create artificial duplicate devices or change existing IDs just to mimic a menu.
- **Outside scope:** room-temperature limitation (§5.3) and volume/heat-power limitation (§5.5), which the issue explicitly says are not needed; support for additional application profiles; other unrelated ECL functions.

## Data and safety rules

- For every setting, verify PNU, circuit, register address (`PNU - 1`), type, signedness, scale, raw and displayed limits, step, units, writable flag, options and OFF/sentinel values. The XML gives candidate metadata; individual documented semantics and exceptions take precedence. Do not write unsupported or unexplained settings.
- Retain the existing generic fallback behavior: newly added profile-dependent settings are absent there until their domains and semantics can be established. Missing fields in a known profile are not created. Profile version matters; no unsupported profile may be treated as validated by a similar version.
- Writes must be validated before reaching the device and read back through the ordinary refresh path. Failed writes and unavailable readings must surface accurately. Never set a value during setup or tests against a real device.
- Avoid unsafe block reads across unavailable gaps. A single refused optional field must not make the climate entity or entire circuit unavailable. Assess the incremental Modbus request count and polling cadence against the current coordinator; disabled Home Assistant entities alone do not guarantee that the underlying component stops polling. Limit overhead and document the chosen strategy.
- Alarm clearing is an explicit user action and its semantics must be established from a primary source. No reset or acknowledgement occurs automatically.

## Validation and test delivery

- Automated Home Assistant and Modbus tests cover all seven profiles and all available requested functions: presence/absence, device association and unchanged existing IDs, register address and circuit offset, signedness, scale, boundaries, OFF and selectable states, writes and refusal paths. At least the A367 second heating circuit and hot water on circuit 3 must be exercised. Existing real diagnostic register images are useful fixtures but do not prove new writes happened on a physical controller.
- Test alarm field ordering (1–16 versus 17–32), active IDs and context, unavailable/partial data, reset writes and readback when supported. Test limiter values 0–3, independent fields, partial failure, firmware gates and appropriate circuit mapping. Never treat an untested/unknown field as inactive.
- Run the complete repository tests, lint, formatting and translation checks. Track coverage in a concise matrix with `automated`, `real-device confirmed`, and `not applicable/not verified`; include the version and date of any real test.
- Update the test-build instructions to cover installation, enabled-by-default state, reversible replacement, settings to compare on-device, and existing behavior checks. Before an optional physical write, the tester notes the original value and verifies/restores it. Do not request or perform physical writes on Gregor's plant without a concrete test plan and his authorization.
- Real tests: A237.1 on Gregor's installation and A266.10 by Obelixed, subject to their participation. A337.2 and A367.1 remain explicitly marked simulated until an owner confirms them. Requests to Obelixed are separate communications requiring Gregor's instruction.

## Definition of the larger test build

Every feature listed above is either implemented for a profile where supported, or explicitly documented as unavailable and why (including x617 or any undocumented alarm reset). The complete automated checks pass. Test instructions and a profile/function test matrix are available on the branch. A tester can install the build without a release, activate the desired new entities, and return to the previous integration. No physical test is represented as completed until its actual outcome is recorded.
