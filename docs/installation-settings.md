# Installer settings

The ECL's *Settings* menu holds values an installer sets once. This integration offers them on the device of their circuit, under *Configuration*, **disabled until you enable them**. Each shows its PNU and its ECL menu name in its attributes, and only the settings your application actually has exist – a controller without a given setting simply does not get the entity.

> **Risk of damage / Schadensgefahr:** Wrong installer settings can damage the controller or the connected equipment. Home Assistant accepts every value inside the controller's range, which is not the same as a safe value for *your* system. Have changes assessed by a qualified heating professional, and note the old value before you change one. / Falsche Anlageneinstellungen können Regler oder Anlage beschädigen. Home Assistant nimmt jeden Wert im Bereich des Reglers an – das heißt nicht, dass er für Ihre Anlage sicher ist. Änderungen von einer Fachkraft beurteilen lassen und den alten Wert notieren.

In the PNU column, `x` is the circuit: `1x031` is `11031` on the first circuit and `12031` on the second.

## Switch and number

Many settings can be *off*. The controller then stores a special value in place of the setting, so those settings come as two entities: a **switch** that turns the setting on and off, and a **number** that sets its value. While the switch is off, the number shows the value the setting will start with – the one it last had, or Danfoss' factory default – so the card always shows a sensible number. Setting the number writes it to the controller and so switches the setting on.

## Return temperature limit

Chapter *Begrenzung der Rücklauftemperatur* in the operating guide.

| Entity (English / Deutsch) | PNU | What it does |
| :-- | :-- | :-- |
| Return limit X1 high outdoor temperature<br>Rücklaufbegrenzung X1 hohe Außentemperatur | `1x031` | Outdoor temperature (the high one) at which the return limit is Y1. The limit runs along a line from (X1, Y1) to (X2, Y2). |
| Return limit Y1 low limit<br>Rücklaufbegrenzung Y1 untere Grenze | `1x032` | Return limit at the high outdoor temperature X1: the lower limit. |
| Return limit X2 low outdoor temperature<br>Rücklaufbegrenzung X2 tiefe Außentemperatur | `1x033` | Outdoor temperature (the low one) at which the return limit is Y2. |
| Return limit Y2 high limit<br>Rücklaufbegrenzung Y2 obere Grenze | `1x034` | Return limit at the low outdoor temperature X2: the higher limit. |
| Return limit maximum influence<br>Rücklaufbegrenzung Einfluss max. | `1x035` | How strongly the desired flow temperature is corrected while the return temperature is *above* the limit: the excess in K times this factor. |
| Return limit minimum influence<br>Rücklaufbegrenzung Einfluss min. | `1x036` | The same while the return temperature is *below* the limit. District heating usually keeps this at 0, because a lower return temperature is welcome; boiler systems use a value above 0 so the return does not get too cold. |
| Return limit adaptation time<br>Rücklaufbegrenzung Anpassungszeit | `1x037` | How quickly the return limit corrects the flow temperature (by at most 8 K). 0 = off, a low value adapts fast, a high value slowly. |
| Return limit overrides minimum flow temperature<br>Rücklaufbegrenzung Vorrang vor minimalem Vorlauf | `1x085` | Whether the return limit may override the minimum flow temperature. Off: the minimum always holds. |

## Optimisation

Chapter *Optimierung*.

| Entity (English / Deutsch) | PNU | What it does |
| :-- | :-- | :-- |
| Automatic saving outdoor threshold<br>Automatisches Sparen Außentemperatur | `1x011` | For district heating: makes the setback shallower the colder it gets outside, so the flow temperature does not jump after a setback. At 10 °C outdoors the full setback applies, at this threshold there is none. Switch off for a setback that never depends on the outdoor temperature. |
| Automatic saving outdoor threshold enabled<br>Automatisches Sparen Außentemperatur aktiviert | `1x011` | Turns the setting above on and off. |
| Heat-up boost<br>Schnellaufheizen | `1x012` | Shortens the heat-up after a setback by raising the desired flow temperature by this percentage, for one hour at most. Ends earlier when a room sensor reports the target reached. |
| Heat-up boost enabled<br>Schnellaufheizen aktiviert | `1x012` | Turns the setting above on and off. |
| Ramp time<br>Rampenfunktion | `1x013` | Minutes over which the desired flow temperature rises step by step after a setback, to avoid load peaks in the supply network. |
| Ramp time enabled<br>Rampenfunktion aktiviert | `1x013` | Turns the setting above on and off. |
| Building factor<br>Gebäudefaktor | `1x014` | Optimised start and stop of the comfort periods: the lowest energy use at full comfort. Two digits describe the building – the first its heat storage together with the heating system (1 small radiator system … 5 large floor heating), the second the design outdoor temperature (0 = −50 °C … 9 = −5 °C, in 5 K steps). Example: 25 = medium storage and −25 °C. Off: no optimisation, the heating starts and stops exactly as scheduled. |
| Optimisation enabled<br>Optimierung aktiviert | `1x014` | Turns the setting above on and off. |
| Optimisation based on<br>Optimierung nach | `1x020` | Whether the optimisation follows the outdoor temperature (choose this if no room temperature is measured) or the room temperature (only where the controller measures it). |
| Optimised stop<br>Optimierter Stopp | `1x026` | The end of each comfort period is optimised as well: the milder it is, the earlier the heating switches off. Off: it runs to the scheduled end. |
| Parallel operation mode<br>Parallelbetrieb Betriebsart | `1x043` | Whether the heating pump runs while the hot water tank charges. *Off*: hot water has priority and the heating pump stops. *Conditional*: it runs as long as the charging temperature is less than the set number of K above the desired flow temperature. *On*: it always runs (where the application offers it). |
| Parallel operation<br>Parallelbetrieb | `1x043` | The K value for *conditional* parallel operation (1–99 K). |

## Control valve

Chapter *Regelparameter*. The controller moves a motor control valve either with short open and close pulses (gear motor, 3-point control) or, for a thermal actuator, with a pulse-width signal. **The actuator type decides which of the other settings count.**

| Entity (English / Deutsch) | PNU | What it does |
| :-- | :-- | :-- |
| Control valve actuator<br>Regelventil Stellantrieb | `1x024` | Which actuator the valve has: *thermal actuator (M-ABV)* or *gear motor (3-point)*. With the thermal actuator the controller ignores motor protection, Xp, Tn, running time, neutral zone and minimum pulse. A wrong choice detunes the control – leave it as your installer set it. |
| Control valve proportional band Xp<br>Regelventil Proportionalband Xp | `1x184` | Xp, the proportional band. A higher value gives a stable but slow control of the flow temperature. |
| Control valve integral time Tn<br>Regelventil Nachstellzeit Tn | `1x185` | Tn, the integral time in seconds. High: slow but stable reaction to deviations. Low: fast but less stable. |
| Control valve running time<br>Regelventil Laufzeit | `1x186` | Seconds the valve needs from fully closed to fully open: stroke in mm × seconds per mm (a 5 mm stroke at 15 s/mm = 75 s), or turning angle × seconds per degree. Check your actuator's type plate. |
| Control valve neutral zone<br>Regelventil neutrale Zone | `1x187` | Nz: how far the flow temperature may be off the desired value before the controller moves the valve. The zone is centred on the desired value, so 5 K means ±2.5 K. |
| Control valve minimum pulse<br>Regelventil Mindeststellimpuls | `1x189` | The shortest pulse the gear motor gets, shown in milliseconds. The controller's display counts it in steps of 20 ms (3 there is 60 ms here), from 40 ms to 1000 ms. A higher value is easier on the actuator. |
| Control valve motor protection<br>Regelventil Motorschutz | `1x174` | Prevents a hunting actuator, which can happen at very low load, and so makes the parts last longer. Off: not active. Otherwise it takes effect after this many minutes of delay. |
| Control valve motor protection enabled<br>Regelventil Motorschutz aktiviert | `1x174` | Turns the setting above on and off. |
| Control valve exercise<br>Regelventil Blockierschutz | `1x023` | While there is no heat demand the valve is moved briefly every third day (at 12:00, for seven minutes) so it does not seize. |

## Pump

Chapter *Applikation*.

| Entity (English / Deutsch) | PNU | What it does |
| :-- | :-- | :-- |
| Pump exercise<br>Pumpenblockierschutz | `1x022` | While there is no heat demand the pump is switched on briefly every third day (at 12:14, for one minute) so it does not seize. |
| Pump frost protection outdoor threshold<br>Pumpenfrostschutz Außentemperatur | `1x077` | The circulation pump runs when the outdoor temperature falls below this value, to protect the system from frost. Off: no frost protection by outdoor temperature. 2 °C is recommended for systems with water. |
| Pump frost protection outdoor threshold enabled<br>Pumpenfrostschutz Außentemperatur aktiviert | `1x077` | Turns the setting above on and off. |
| Pump start flow threshold<br>Pumpe Einschalten ab Vorlauf-Sollwert | `1x078` | The circulation pump starts when the desired flow temperature is above this value. Below it the pump is off and the valve fully closed. |

## Heating off

Chapter *Heizung aus*. Newer controllers know a summer and a winter period, each with a start date, an outdoor temperature threshold and a filter; the existing *Summer cut-off* temperature (1x179) belongs to the summer period. What the filter values count in is stated in your application's operating guide.

| Entity (English / Deutsch) | PNU | What it does |
| :-- | :-- | :-- |
| Summer cut-off start month<br>Sommerabschaltung Startmonat | `1x392` | Month in which the summer period starts (1–12). |
| Summer cut-off start day<br>Sommerabschaltung Starttag | `1x393` | Day of that month (1–31). |
| Summer cut-off filter<br>Sommerabschaltung Filter | `1x395` | Damping of the outdoor temperature the summer cut-off decides by: the higher, the slower it reacts. Off: no damping. |
| Summer cut-off filter enabled<br>Sommerabschaltung Filter aktiviert | `1x395` | Turns the setting above on and off. |
| Winter cut-off start month<br>Winterabschaltung Startmonat | `1x396` | Month in which the winter period starts (1–12). |
| Winter cut-off start day<br>Winterabschaltung Starttag | `1x397` | Day of that month (1–31). |
| Winter cut-off threshold<br>Winterabschaltung Grenzwert | `1x398` | The outdoor temperature threshold of the winter period. Off: no winter cut-off. |
| Winter cut-off threshold enabled<br>Winterabschaltung Grenzwert aktiviert | `1x398` | Turns the setting above on and off. |
| Winter cut-off filter<br>Winterabschaltung Filter | `1x399` | Damping of the outdoor temperature the winter cut-off decides by. Off: no damping. |
| Winter cut-off filter enabled<br>Winterabschaltung Filter aktiviert | `1x399` | Turns the setting above on and off. |

The hot water circuit has its own control valve, pump and return-limit settings under the same names, on the hot water device.

## Disinfection start

Disinfection start / Desinfektionsbeginn (`1x122`, hot water circuit) is a dropdown of the 48 half hours of the day: the controller counts the start of the anti-bacteria run in half-hour slots, so nothing in between can be chosen. Earlier versions offered a time field here; it was replaced by this dropdown, so an automation or dashboard that used the old `time` entity needs the new `select` entity (`select.select_option` with an option such as `22:30`).

## Limiter status

The diagnostic sensor *Limiter status / Begrenzerstatus* of each circuit says what currently pushes the desired flow temperature up or down – the return limit, a holiday program, the hot water priority and so on. Its state is *no influence*, *influenced* or *partly known* (some influences are unknown to the controller's firmware). Every influence that is active is an attribute of its own, named in your language, with its direction: *raises*, *lowers* or *changes* the setpoint. It needs controller software 1.32 or newer; some influences need newer software.
