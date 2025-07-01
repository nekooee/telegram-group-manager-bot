# Telegram Group Manager Bot

A versatile Telegram bot to help manage groups and channels with various useful features.

Currently, the bot supports:

* Scheduling automatic deletion of messages with customizable timers.
* Converting various image formats (like HEIC, AVIF) to JPG, with options to upload as photo or file.
* And many more features planned to be added soon!

---

## Features

### Scheduled Message Deletion

Add the bot to your group or channel, then you can set messages to be deleted automatically after a specific time.

**How to use:**

* Reply to the message you want to delete and send:

  ```
  /del
  ```

  This will delete the message after 24 hours by default (configurable in the `config.py` file).

* To specify a custom time, use the format:

  ```
  /del 1h
  /del 30m
  /del 7d
  ```

  where
  `d` = days
  `h` = hours
  `m` = minutes

The maximum allowed time for scheduling message deletion is **10 days (240 hours)**. If the specified time exceeds this limit, the default `DELETE_AFTER_HOURS` value from the config will be used instead.

---

### Image Conversion to JPG

The bot supports converting certain image formats specified in the config file.

**How to use:**

* Reply to the message containing the image you want to convert and send:

  ```
  /tojpg
  ```

  This will convert the image and upload it as a **file**.

* If you want the converted image to be uploaded as a **regular photo**, send:

  ```
  /tojpg photo
  ```

The conversion quality is set to 90% by default, balancing image quality and file size.

---

## Running the Bot on Ubuntu or AlmaLinux

Before starting the bot for the first time:

1. **Move the bot files to a folder on your server and navigate to that folder**:

   ```bash
   mkdir ~/telegram-bot
   mv /path/to/your/files/* ~/telegram-bot/
   cd ~/telegram-bot
   ```

2. **Rename the `.env.example` file to `.env` and update the contents** with your desired environment variables:

   ```bash
   cp .env.example .env
   nano .env
   ```

   > Make sure to set values such as your bot token and other required configurations.

3. Create and activate the virtual environment:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

4. Install required dependencies:

   ```bash
   pip install -r requirements.txt
   ```

Then, to run the bot and keep it running even after closing the terminal, you can use either `screen` or `nohup`.

---

### Using `screen`

1. Install screen if not installed:

   ```bash
   sudo apt install screen    # Ubuntu
   sudo dnf install screen    # AlmaLinux
   ```

2. Start a new screen session:

   ```bash
   screen -S telegrambot
   ```

3. Activate your virtual environment and start the bot:

   ```bash
   source .venv/bin/activate
   python group_manager_bot.py
   ```

4. To detach from the screen session (leave it running):

   Press `Ctrl + A` then `D`

5. To resume the screen session later:

   ```bash
   screen -r telegrambot
   ```

---

### Using `nohup`

1. Activate your virtual environment:

   ```bash
   source .venv/bin/activate
   ```

2. Start the bot in the background:

   ```bash
   nohup python group_manager_bot.py > bot.log 2>&1 &
   ```

   This will keep the bot running after you close the terminal. Logs will be written to `bot.log`.

3. To check if it’s running:

   ```bash
   ps aux | grep group_manager_bot.py
   ```

4. To stop the bot later, find the PID and kill it:

   ```bash
   kill <PID>
   ```

---

## Getting Started

1. Add the bot to your Telegram group or channel.
2. Grant the bot admin rights to enable message deletion and media handling.
3. Use the commands above to manage your messages and images.

---

## Configuration

You can customize default timers, allowed image formats, and other settings in the `config.py` file.

---

## Future Plans

* Adding more moderation tools.
* Support for more media formats.
* Custom commands and automations.

Stay tuned!

---

## License

Creative Commons Attribution-NonCommercial 4.0 International Public License (CC BY-NC 4.0)

---

If you find this bot useful or have suggestions, feel free to contribute or open issues.
