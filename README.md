# LinkedIn Job Agent

[![Ask DeepWiki](https://devin.ai/assets/askdeepwiki.png)](https://deepwiki.com/Samarth622/Linkedin-Job-Agent)

A Discord bot that automates scraping for LinkedIn job postings based on personalized criteria and delivers them directly to your email.

## Features

-   **Discord Bot Interface**: Configure and run the job agent using simple slash commands in Discord.
-   **Personalized Job Search**: Define specific job roles and locations you are interested in.
-   **Experience Level Filtering**: Automatically filters jobs based on your specified years of experience.
-   **Email Notifications**: Receives a `.csv` file with new job listings directly in your inbox.
-   **Prevents Duplicates**: Keeps track of previously scraped and sent jobs to ensure you only receive new listings.
-   **Secure Cookie Handling**: Upload your LinkedIn authentication cookies through a secure Discord modal.

## Prerequisites

-   Python 3.8+
-   A Discord Bot Token
-   A Gmail account (or another email provider) to send notifications.
-   Google Chrome installed

## Setup

1.  **Clone the Repository**

    ```bash
    git clone https://github.com/Samarth622/Linkedin-Job-Agent.git
    cd Linkedin-Job-Agent
    ```

2.  **Install Dependencies**

    ```bash
    pip install -r requirements.txt
    ```

3.  **Create an Environment File**

    Create a file named `.env` in the root directory of the project and add the following environment variables:

    ```env
    # Your Discord bot's token
    DISCORD_BOT_TOKEN="your_discord_bot_token_here"

    # The email address that will send the job notifications
    EMAIL_SENDER="your_email@gmail.com"

    # The password for the sender email account (see note below)
    EMAIL_PASSWORD="your_email_app_password_here"
    ```

    **Note on `EMAIL_PASSWORD`**: If you are using Gmail with 2-Factor Authentication, you must generate an "App Password" for this script. You can create one here: [Google App Passwords](https://myaccount.google.com/apppasswords).

4.  **Run the Bot**

    ```bash
    python job_agent.py
    ```

    Once running, you will see a confirmation message in your console, e.g., `YourBotName#1234 online`. You can now interact with the bot in any Discord server it has been invited to.

## Usage

The agent is operated through a series of slash commands in Discord.

1.  ### `/cookies`
    This command opens a modal where you can paste your LinkedIn cookies in JSON format. This is required for the agent to authenticate with LinkedIn on your behalf.

    **How to get your LinkedIn cookies as JSON:**
    a. Install a browser extension like [Cookie-Editor](https://cookie-editor.com/) for Chrome or Firefox.
    b. Log in to your LinkedIn account.
    c. Open the Cookie-Editor extension.
    d. Click the "Export" button, select "JSON" format, and click "Copy to Clipboard".
    e. Paste the copied JSON into the modal in Discord.

2.  ### `/setup`
    This command opens a configuration modal to set up your job search preferences.

    -   **Email**: The email address where you want to receive job notifications.
    -   **Roles**: A comma-separated list of job titles you are looking for (e.g., `Software Engineer, Data Scientist`).
    -   **Locations**: A comma-separated list of locations (currently hardcoded to `India` in the search query).

3.  ### Select Experience
    After submitting the `/setup` form, a dropdown menu will appear allowing you to select your years of experience. This selection determines the experience level filters used on LinkedIn.

4.  ### `/start`
    Run this command to start the scraping process. The bot will:
    -   Use your saved configuration and cookies.
    -   Scrape LinkedIn for new job postings that match your criteria.
    -   If new jobs are found, it will compile them into a `.csv` file.
    -   Email the `.csv` file to the address you configured.
    -   Send a confirmation message in Discord indicating the number of jobs found and whether the email was sent successfully.
