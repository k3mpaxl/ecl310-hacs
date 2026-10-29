# Issue 47: profile and verification matrix

Status as of 2026-10-29. Availability below comes from the supported XML profile
reports. A listed family contains only the parameters actually present for that
circuit; it does not imply that every PNU in the family exists. Automated tests
use simulated Modbus registers and, where noted in the repository tests, captured
register images; neither proves that a new setting was written to hardware.

| Profile | Circuits | Family differences / XML availability | Real-device confirmation of this build |
|---|---|---|---|
| A237.1 V04 | 1 heating, 2 hot water | Heating: return, optimisation, valve, pump, seasonal and alarm-difference settings | Not yet tested on Gregor's A237.1 |
| A266.10 V03 | 1 heating, 2 hot water | Both circuits have return influence, valve and pump settings; only heating has return curve, optimisation, seasonal and alarm input x079/x080/x636/x637 | Original return-limit values and writes confirmed by Obelixed in [issue 47](https://github.com/k3mpaxl/ecl310-hacs/issues/47); 11085 and this larger build not yet confirmed |
| A337.2 V02 | 1 heating, 2 hot water | Heating: return, optimisation, valve, pump and alarm-difference settings; seasonal x392–x399 absent | No physical test; captured read image and simulation |
| A367.1 V01 | 1–2 heating, 3 hot water | Both heating circuits have return, optimisation, valve, pump and alarm-difference settings; actuator type x024 and seasonal x392–x399 absent | Simulation only |
| A367.1 V02 | 1–2 heating, 3 hot water | As V01, with actuator type x024 on both heating circuits | Simulation only |
| A367.1 V03 | 1–2 heating, 3 hot water | As V02, seasonal settings on heating 1 and a subset on heating 2 | Simulation only |
| A367.1 V04 | 1–2 heating, 3 hot water | As V03; heating 2 has no parallel-operation PNU 12043 | Simulation only |

In A367, PNU prefixes for heating circuits 1 and 2 are 11 and 12; hot water is
circuit 3. A266 hot-water settings use prefix 12. Availability is decided from
the selected profile, including domain and raw range; generic mode is excluded.
An entity's PNU attribute is the authoritative identification for comparison.

| Function | Automated verification | Remaining limitation |
|---|---|---|
| Existing flow, disinfection and climate | Existing integration regression suite | No new physical confirmation |
| Return limit, influence and priority | Profile presence, addresses, validation, writes and refusal paths | PNU 11085/12085 not confirmed on hardware |
| Optimisation and OFF sentinels | Seven profiles, boundaries, special values and restore behaviour | New controls await physical comparison |
| Valve, pump and seasonal settings | Profile domains/circuit offsets and representative writes; A367 circuit 2 | Actuator 0/1 mapping inferred from XML and guide defaults; not confirmed on device |
| Alarm settings | Profile availability and A266 input polarity/seconds | x617 absent from all seven XML profiles; no entity |
| Alarm masks and contexts | Simulated ID 1 and ID 18, context 1057, zero masks, partial refusal | Alarm meaning application-specific; clearing 1032/1033 unavailable because write semantics are undocumented |
| Limiter status | Simulated bit pairs, circuit addresses, firmware gates and refusal | Later firmware flags can remain unknown; no device validation |

Sources: local Danfoss ECL Tool XML reports for the seven profile versions;
[Danfoss communication description AQ074886472234de-000601](https://assets.danfoss.com/documents/latest/206109/AQ074886472234de-000602.pdf),
§6.10 and §6.17; [A266 guide](https://assets.danfoss.com/documents/latest/223951/AQ156586461753de-000602.pdf),
pp. 119–120. The test branch is not a release and no physical test is implied
by a passing automated test.
