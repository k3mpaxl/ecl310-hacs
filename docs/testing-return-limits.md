# Testing the return-limit settings (issue 47)

This is a **test branch**, not a HACS release. It adds the return-limit curve
(X1/Y1/X2/Y2), maximum and minimum influence, and adaptation time. It covers
A237.1 V04, A266.10 V03, A337.2 V02 and A367.1 V01–V04. It does not yet add
all other installation settings, alarm handling, or limiter-status flags.

## Install the branch manually

1. Back up the existing `config/custom_components/ecl310` folder somewhere
   outside `custom_components`, and keep the backup until testing is finished.
2. Download the branch as a ZIP from
   [test/issue-47-return-limits](https://github.com/k3mpaxl/ecl310-hacs/archive/refs/heads/test/issue-47-return-limits.zip)
   and extract it. Inside it, find `custom_components/ecl310`.
3. Replace the existing `config/custom_components/ecl310` folder with that
   extracted `ecl310` folder, keeping the backup from step 1. Do not merge the
   folders: a clean replacement prevents obsolete files from remaining.
4. Restart Home Assistant. Check the ECL integration has loaded and the
   expected application is selected under its configuration.

To return to the previous version, replace the test folder with your backup
and restart Home Assistant. HACS may replace manual files on a later update.

## What to check

The new entities are **disabled by default**. On the ECL heating or hot water
circuit's device page, show disabled entities and enable the return-limit
settings available for that circuit. They appear under Configuration; the
entity attributes show the PNU and ECL menu name. Not every application or
circuit has every parameter. A266.10 V03 has seven on heating circuit 1 and
three influence/adaptation settings on hot water circuit 2.

First compare the displayed values and PNU numbers with the ECL display,
including negative values. Existing climate, water heater and pump entities
should continue to work. If you choose to test writing, note the original value,
change one suitable setting, verify it on the ECL and restore the original.
Only adjust a setting if you understand its effect on your installation.

Please report the application and version, controller software version, Home
Assistant version, PNUs and displayed values you compared, and any errors or
unexpected behaviour. Review diagnostics and logs for information you do not
want to publish before attaching them to GitHub.
