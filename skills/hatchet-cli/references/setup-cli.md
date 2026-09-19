# Install and Set Up the Hatchet CLI

These are instructions for an AI agent to install the Hatchet CLI and configure a profile. Follow each step in order.

> ## This project: read this first
>
> This repo publishes the Hatchet dashboard on **8080** with a **committed token**, so two
> steps below need adjusting. Everything else applies as written.
>
> **1. `HATCHET_CLIENT_SERVER_URL` must be exported for every CLI command.**
>
> ```bash
> export HATCHET_CLIENT_SERVER_URL=http://localhost:8080
> ```
>
> The token has `localhost:8888` baked into its `aud`, `iss`, and `server_url`
> claims, and `hatchet profile add` has no `--address` flag — so the profile stores
> `8888` and every request 403s without this override. Setting it only when creating
> the profile is not enough; the stored address stays wrong.
>
> **2. Don't ask the user for a token.** It's in `workflows/.env`, committed on
> purpose — the auth-disabled dev image ships one fixed non-expiring token, so it
> isn't a secret.
>
> Full setup from a clean checkout:
>
> ```bash
> docker compose up -d          # wait for `docker compose ps` to show hatchet healthy
> export HATCHET_CLIENT_SERVER_URL=http://localhost:8080
> hatchet profile add --name chp99 \
>   --token "$(grep '^HATCHET_CLIENT_TOKEN=' workflows/.env | cut -d= -f2-)"
> hatchet runs list -p chp99 --since 1h -o json
> ```
>
> Ports: `3000` app, `5432` Postgres, `8080` Hatchet UI/API, `7077` Hatchet gRPC.
> The dashboard at http://localhost:8080 needs no login.

## Step 1: Check if Already Installed

```bash
hatchet --version
```

If this prints a version number, the CLI is already installed. Skip to Step 3 (profile setup).

If the command is not found, proceed to Step 2.

## Step 2: Install the CLI

On macOS, Linux, or WSL:

```bash
curl -fsSL https://install.hatchet.run/install.sh | bash
```

Alternatively, on macOS via Homebrew:

```bash
brew install hatchet-dev/hatchet/hatchet --cask
```

After installation, verify it worked:

```bash
hatchet --version
```

## Step 3: Check for Existing Profiles

```bash
hatchet profile list
```

If a profile already exists that connects to the correct Hatchet instance, note its name and use it as the `-p` flag in all subsequent commands. You are done.

If no profiles exist or the correct one is missing, proceed to Step 4.

## Step 4: Create a Profile

You need a Hatchet API token. In this repo it's already in `workflows/.env` — see the box at the top. Elsewhere, ask the user for one if you do not have it. Then create a profile:

```bash
hatchet profile add --name HATCHET_PROFILE --token <API_TOKEN>
```

Replace `HATCHET_PROFILE` with a descriptive name (e.g. `local`, `staging`, `production`) and `<API_TOKEN>` with the actual token.

To set it as the default profile (so `-p` is optional in future commands):

```bash
hatchet profile set-default --name HATCHET_PROFILE
```

## Step 5: Verify Connectivity

Test that the profile works by listing workflows:

```bash
hatchet runs list -o json -p HATCHET_PROFILE --since 1h --limit 1
```

If this returns a JSON response (even with an empty rows list), the profile is correctly configured and connected.

## Troubleshooting

- **"command not found"** after install: The CLI binary may not be on your PATH. Check `~/.local/bin/hatchet` or re-run the install script.
- **403 / "Please provide valid credentials"** in this repo: `HATCHET_CLIENT_SERVER_URL` isn't exported. It's needed on every command, not just `profile add`. See the box at the top.
- **Authentication error** elsewhere: The API token may be invalid or expired. Ask the user for a new token and run `hatchet profile update`.
- **Connection refused**: The Hatchet server may not be running. In this repo, `docker compose up -d`; elsewhere, `hatchet server start`.
