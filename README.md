# GitHub Actions Auto Check-in

This repository contains a GitHub Actions workflow for bilibili live check-in
and the V2EX daily mission reward.

## Usage

1. Push these files to a GitHub repository.
2. Open `Settings` -> `Secrets and variables` -> `Actions`.
3. Add these Repository secrets:
   - `BILIBILI_COOKIE`: the full Cookie header from a logged-in bilibili request.
   - `V2EX_COOKIE`: the full Cookie header from a logged-in V2EX request.
4. Open `Actions` -> `Auto Check-in` to run it manually, or wait for the schedule.

The default schedule runs at 01:15 UTC every day, which is 09:15 in Beijing
time. Edit the cron expression in `.github/workflows/auto-checkin.yml` if you
want a different time.

## Notes

- Cookies are login credentials. Store them only in GitHub Secrets.
- The script does not bypass captcha, two-factor checks, or anti-abuse systems.
- If either website changes its API or page structure, the script may need an
  update.
