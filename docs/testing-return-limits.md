# Testing the issue 47 installation and diagnostics build

This is a **test branch**, not a HACS release. It adds profile-specific return
limit, optimisation, control valve, pump, seasonal and alarm settings, plus
read-only alarm and limiter diagnostics. See the
[profile and verification matrix](issue-47-test-matrix.md) for availability and
what has actually been tested. The build supports A237.1 V04, A266.10 V03,
A337.2 V02 and A367.1 V01–V04 only; the generic fallback does not expose these
new settings or diagnostics.

## Important safety information

> **Risk of damage:** Some settings directly affect the heating system and its
> connected equipment. Incorrect valve, actuator, pump, frost-protection,
> temperature-limit or alarm settings can lead to unsafe operation and may
> damage the controller or other system components. A value accepted by the
> ECL or shown as valid in Home Assistant is not necessarily safe for your
> installation. Only a qualified person who understands the specific system
> should change these settings; when in doubt, consult the installer or service
> technician. Compare values read-only first, record the original settings and
> use the ECL application manual before making any change.
>
> **Schadensgefahr:** Einige Einstellungen beeinflussen die Heizungsanlage und
> angeschlossene Komponenten unmittelbar. Falsche Einstellungen für Ventil,
> Stellantrieb, Pumpe, Frostschutz, Temperaturbegrenzung oder Alarme können zu
> unsicherem Betrieb und Schäden am Regler oder an der Anlage führen. Ein vom
> ECL oder von Home Assistant zugelassener Wert ist nicht automatisch für die
> eigene Anlage sicher. Änderungen nur durch eine fachkundige Person vornehmen
> lassen; im Zweifel den Heizungsfachbetrieb kontaktieren. Zuerst Werte nur
> ablesen, Originalwerte dokumentieren und das passende ECL-Handbuch beachten.

## Install and restore

1. Back up the existing `config/custom_components/ecl310` folder outside
   `custom_components` and keep the backup until testing is finished.
2. Download the [test branch ZIP](https://github.com/k3mpaxl/ecl310-hacs/archive/refs/heads/test/issue-47-return-limits.zip)
   and extract it. Find `custom_components/ecl310` inside the archive.
3. Replace the entire existing `config/custom_components/ecl310` folder with
   the extracted folder; do not merge them.
4. Restart Home Assistant and check the integration loads and identifies the
   expected application and version.
5. To roll back, replace the test folder with the backup and restart Home
   Assistant. HACS may overwrite manually installed files during an update.

## Enable and compare

New writable installation entities are disabled by default. On the ECL heating
or hot-water circuit device page, open the disabled entities list and enable
only the controls you need. They appear in Configuration; their attributes
include the ECL PNU and, where available, the menu name. Some settings use an
additional enable switch to represent the ECL's special OFF value. A number
may show `unknown` while its corresponding switch is off. Parallel operation
uses a mode selector and a threshold only in conditional mode.

Alarm count is a diagnostic on the controller; its `alarm_ids` and `contexts`
attributes show active IDs and available raw context words. Meanings depend on
the application. There is no alarm acknowledgement or clearing action: the
Danfoss communication description names PNU 1032/1033 but does not specify the
write protocol sufficiently to implement it safely. Further reliable technical
details from the issue could allow this to be revisited.

Each circuit also has a diagnostic limiter status. Its `influences` attribute
shows `none`, `higher`, `lower`, or `changed` for documented bit pairs and
`null` for fields unavailable on that firmware; `raw_words` preserves the
four original words. `partial` means some influences are unknown or reserved bits are set. Unknown
firmware, unsupported versions or missing registers must not be read as no
influence. A refused word makes that circuit's diagnostic unavailable.

Home Assistant groups entities into Configuration and Diagnostic sections on a
device page, but those categories do not reproduce the ECL menu hierarchy.
The optional [dashboard example](issue-47-dashboard-example.yaml) uses separate
sections and requires your actual entity IDs. See the official documentation
for [entity categories](https://contributors.home-assistant.io/core/quality-scale/entity-category/)
and the [entities card](https://www.home-assistant.io/dashboards/entities/).

On A237.1 V04 or A266.10 V03, compare values and PNU attributes with the ECL
display first, including negative values, OFF states, the active alarms and
limiter status. Check that existing climate, water heater and pump entities
still work. For A266.10, compare the heating and hot-water circuits separately.
For A367.1, the two heating circuits and circuit 3 hot water are distinct.
The actuator type is shown only as a disabled-by-default raw diagnostic. Its
0/1 labels are inferred from documented defaults but not verified for every
profile, so changing this setting through the integration is not offered.

Any write test must be assessed for the particular system by a qualified person.
Record the original value and operating condition, change only an appropriate
setting, check it on the controller, then restore and verify the original if
doing so is safe. Never change a setting whose effect on the plant is unclear.
No device write is performed automatically by this test procedure. Report the application and profile version, firmware,
Home Assistant version, compared PNUs, any changed/restored values and any
unexpected behaviour. Review diagnostics and logs for private information
before sharing them.

## Polling and integration maintenance

Ordinary operating values and diagnostics are read every 30 seconds. Installer
settings are read initially, every tenth cycle (about five minutes), and after
an integration write. External changes can therefore take up to five minutes
to appear. Disabling an entity does not stop its Modbus register from being
polled. Optional refused registers are isolated and may remain unavailable. In a simulated
A266.10 with the full test build, one routine update made 28 read requests and
one installer update made 48, excluding weekly schedules and recovery retries.
The earlier return-limit-only test branch made 27 per ordinary update; real
controllers and refused registers can change these numbers.

The `ecl310_modbus` library is vendored in this repository. This branch changes
its profile binding, polling and diagnostic components; reconcile those changes
with the upstream `ecl310-modbus` project before any future re-vendoring. The
operating-only planner uses an internal `modbus-connection` API, so compatibility
must be checked when updating that dependency.
