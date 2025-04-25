# Mastodon Psychologist Bot (Local Development Setup - macOS)

This guide outlines the steps to set up a local Mastodon development instance and run the Psychologist Bot on macOS.

## Prerequisites

- **macOS**
- **Docker Desktop:** Install from [Docker's website](https://www.docker.com/products/docker-desktop/). Ensure it's running.
- **Git:** Usually pre-installed on macOS. Verify with `git --version`.
- **Python & uv:** Install Python (e.g., from [python.org](https://www.python.org/) or using Homebrew) and then install `uv`: `pip install uv`.
- **Gemini API Key:** Obtain from [Google AI Studio](https://aistudio.google.com/app/apikey).

## Setup Steps

1.  **Clone Repositories:**
    Open your terminal and navigate to your desired development directory. Clone the Mastodon server and this bot repository:

    ```bash
    git clone https://github.com/mastodon/mastodon.git
    git clone https://github.com/hibukki/mastodon-llm-bot.git psychologist_bot
    # Navigate into the main directory containing both clones
    cd .. # Or navigate to the directory containing 'mastodon' and 'psychologist_bot'
    ```

2.  **Start Mastodon Development Environment:**
    The Mastodon repository includes a Docker-based development environment.

    ```bash
    # Navigate into the Mastodon directory
    cd mastodon

    # Start the required services (database, redis, etc.) in the background
    docker compose -f .devcontainer/compose.yaml up -d

    # Run the initial setup script (installs dependencies, prepares database)
    # This also creates a default 'admin' user, but we'll configure it later.
    docker compose -f .devcontainer/compose.yaml exec app bin/setup

    # Start the Mastodon development processes (web, streaming, sidekiq)
    # Run this in a separate terminal window or using a terminal multiplexer (like tmux)
    # as it occupies the foreground.
    docker compose -f .devcontainer/compose.yaml exec app bin/dev
    ```

    Wait for the services in the `bin/dev` terminal to finish starting up.

3.  **Configure Admin User:**
    The `bin/setup` script creates an `admin` user, but we need to set its password and email.

    _Execute these commands from the main project directory (the one containing `mastodon` and `psychologist_bot`)._

    ```bash
    # Reset the admin password (copy the output password!)
    docker compose -f mastodon/.devcontainer/compose.yaml exec app bin/tootctl accounts modify admin --reset-password

    # Set the admin email (replace with your actual email)
    docker compose -f mastodon/.devcontainer/compose.yaml exec app bin/tootctl accounts modify admin --email YOUR_ADMIN_EMAIL@example.com --confirm
    ```

    You should now be able to log in to `http://localhost:3000` with `YOUR_ADMIN_EMAIL@example.com` and the password you just copied.

4.  **Configure Bot User (`psychologist_bot`):**

    - **Create User:** Log in to `http://localhost:3000` as the `admin` user. Use the UI (Administration -> Users -> Invite people or similar) to create the `psychologist_bot` user. Use a unique email (e.g., `YOUR_EMAIL+pb@example.com`).
    - **Confirm via CLI:** The local instance can't send confirmation emails. Run these commands _from the main project directory_:

      ```bash
      # Reset the bot's password (copy the output password!)
      docker compose -f mastodon/.devcontainer/compose.yaml exec app bin/tootctl accounts modify psychologist_bot --reset-password

      # Approve the bot account
      docker compose -f mastodon/.devcontainer/compose.yaml exec app bin/tootctl accounts modify psychologist_bot --approve

      # Confirm the bot's email
      docker compose -f mastodon/.devcontainer/compose.yaml exec app bin/tootctl accounts modify psychologist_bot --confirm
      ```

    - **Log in as Bot:** Log out from admin and log in to `http://localhost:3000` as `psychologist_bot` using its email and the password you just copied.
    - **Set Discoverable:** Go to Preferences -> Profile -> Appearance. Check the box for **"Suggest account to others"** (or similar wording for discoverability) and save.
    - **Generate Access Token:**
      - Go to Preferences -> Development -> New Application.
      - Application Name: `psychologist_bot_app` (or similar).
      - Redirect URI: Leave as default (`urn:ietf:wg:oauth:2.0:oob`).
      - Scopes: Check **`read:statuses`**, **`read:notifications`**, and **`write:statuses`**.
      - Submit.
      - **Copy the generated Access Token.**

5.  **Configure Bot Environment:**

    ```bash
    # Navigate to the bot directory
    cd ../psychologist_bot # Or just `cd psychologist_bot` from the main dir

    # Create/sync the Python virtual environment and install dependencies
    uv sync
    ```

    - Create a file named `.env` in the `psychologist_bot` directory.
    - Add the following content, replacing placeholders with your actual keys:

      ```dotenv
      # .env
      GEMINI_API_KEY=YOUR_GEMINI_API_KEY_HERE
      MASTODON_ACCESS_TOKEN=YOUR_MASTODON_ACCESS_TOKEN_HERE
      MASTODON_API_BASE_URL=http://localhost:3000
      BOT_USERNAME=psychologist_bot
      ```

## Running the Bot

1.  Ensure the Mastodon development environment is running (`docker compose ... exec app bin/dev` in its own terminal).
2.  Open a _new_ terminal window.
3.  Navigate to the bot directory (`psychologist_bot`).
4.  Run the bot script:

    ```bash
    uv run python bot.py
    ```

The bot will connect to the local Mastodon stream and start listening for public posts to potentially reply to.
