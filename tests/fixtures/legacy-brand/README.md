# Legacy brand fixture

Two brand specs written before feature settings existed, and the profile `main` wrote for
each. `skills/setup-brand/tests/test_legacy_profile_output.py` compares today's output with
these files, so a change to what an existing brand receives fails a test.

- `full.spec.json` uses every channel behavior, onboarding enabled, and the optional keys.
- `minimal.spec.json` has only the required keys.
- `main/<spec>/` holds `SOUL.md`, `cronjobs.yaml`, `config.yaml`, and `brand.json` as
  `setup.write_profile` wrote them at commit `e3e9b89d069d8a812e5a6b7c5f9263eece5a76c5`
  (`main` on 29 Sep 2026), into an empty profile directory with `HERMES_HOME` and
  `ACE_DEFAULT_SLACK_CHANNEL` unset.

Two paths are replaced so the files do not depend on the machine: `<REPO>` is the
repository root and `<PROFILE>` is the profile directory.

Do not regenerate these files from a feature branch. They record what existing brands had.
Regenerate them only from `main`, and only when a change to existing brands is intended.
