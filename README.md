# StandX Market Maker Uptime Bot

A Python bot designed to participate in the **StandX Market Maker Uptime Program**. It automatically places limit orders (Bid/Ask) around the mark price to farm uptime points while maintaining delta neutrality.

> **Note**: This project was inspired by logic found in [DD-PERP-Strategy](https://github.com/Dazmon88/DD-PERP-Strategy).

## Features

*   **Dual Authentication Support**:
    *   **Private Key Wallet**: Connects using a standard EVM Private Key (e.g., from MetaMask/Rabby).
    *   **Keyless Wallet (API Token)**: Connects using a StandX API Token and Signing Key (e.g., for Binance Web3 Wallet).
*   **Market Maker Uptime Strategy**:
    *   Places orders within a configurable spread (default 8 bps) of the Mark Price.
    *   Automatically refreshes orders every 30 seconds.
    *   **Graceful Shutdown**:
        *   On stop (Ctrl+C), attempts to cancel all open orders to leave no exposure.
*   **Delta Neutrality**:
    *   Automatically detects filled orders.
    *   Immediately closes open positions via Market Order to remain delta neutral.
*   **Dynamic Configuration**:
    *   CLI prompts for Order Size at startup.
    *   Configurable target spread and refresh rate.

## Prerequisites

*   Python 3.8+
*   A StandX account (on BSC)

## Installation

1.  Clone the repository:
    ```bash
    git clone https://github.com/your-repo/bot_standx.git
    cd bot_standx
    ```

2.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```

## Configuration

1.  Create a `.env` file in the root directory:
    ```bash
    cp .env.example .env  # If you have an example, otherwise create new
    ```

2.  Add your credentials to `.env`. You only need to populate the variables for the mode you intend to use.

    ```ini
    # MODE 1: Private Key Wallet (EVM)
    WALLET_PRIVATE_KEY=your_private_key_here

    # MODE 2: Keyless / API Token (e.g., Binance Wallet)
    STANDX_API_TOKEN=your_long_jwt_token_here
    STANDX_API_KEY=your_signing_private_key_here  
    
    # TRADING CONFIG
    SYMBOL=BTC  # Options: BTC, ETH (Will be converted to BTC-USD, ETH-USD)
    
    # Optional Overrides
    # STANDX_API_URL=https://perps.standx.com
    ```

## Usage

:warning:

Before using the bot, clean-up your order book or positions (the bot will do it). 

It is highly recommended to **monitor the StandX GUI** while the bot is running to verify that orders are correctly placed in the order book and that positions are managed as expected. 

Run the bot:

```bash
python3 main.py
```

Follow the CLI prompts:

1.  **Select Authentication Mode**:
    *   Type `1` for standard Private Key.
    *   Type `2` for API Token (Keyless).
2.  **Order Size**:
    *   Enter the desired Order Size in BTC (e.g., `0.005`).
    *   Press Enter to use the default (`0.0015` BTC).

The bot will start logging its activity: fetching prices, cancelling old orders, closing positions (if any), and placing new orders.

## Important Notes

*   **Risk**: Trading bots involve financial risk. Use at your own risk. The "Market Maker" strategy intends to be neutral but slippage or execution failures can occur.
*   **Security**: Never share your `.env` file or private keys. This file is added to `.gitignore` by default.

## Disclaimer

The software is provided "as is", without warranty of any kind, express or implied. In no event shall the authors or copyright holders be liable for any claim, damages or other liability, whether in an action of contract, tort or otherwise, arising from, out of or in connection with the software or the use or other dealings in the software. **You are solely responsible for your private keys and your funds.**

## License

MIT
